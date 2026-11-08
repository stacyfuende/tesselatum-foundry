from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from jsonschema import Draft202012Validator, SchemaError


DomainObject = Mapping[str, Any]
ObjectKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One machine-readable semantic validation finding."""

    code: str
    message: str
    severity: str = "error"
    json_pointer: str | None = None

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def _object_key(object_id: str, version: str) -> ObjectKey:
    return object_id, version


def _port_map(ports: list[DomainObject]) -> dict[str, DomainObject]:
    return {port["port_id"]: port for port in ports}


def _compatible_kind(source_kind: str, target_kind: str) -> bool:
    return source_kind == "any" or target_kind == "any" or source_kind == target_kind


def validate_recipe_graph(
    recipe: DomainObject,
    *,
    cells: Mapping[ObjectKey, DomainObject],
    capabilities: Mapping[ObjectKey, DomainObject],
    artifacts: set[ObjectKey] | None = None,
) -> list[ValidationFinding]:
    """Validate references, cell bindings, ports, and DAG structure for a Recipe.

    Supplied cells and capabilities are expected to have passed their JSON Schema checks.
    This validator does not inspect spatial data or establish methodological suitability.
    """
    findings: list[ValidationFinding] = []
    nodes_by_id: dict[str, DomainObject] = {}
    cells_by_node: dict[str, DomainObject] = {}
    node_by_cell_key: dict[ObjectKey, str] = {}

    for index, node in enumerate(recipe.get("nodes", [])):
        node_id = node["node_id"]
        cell_ref = node["cell"]
        cell_key = _object_key(cell_ref["cell_id"], cell_ref["version"])

        if node_id in nodes_by_id:
            findings.append(
                ValidationFinding(
                    "recipe.duplicate_node_id",
                    f"Recipe node ID {node_id!r} is declared more than once.",
                    json_pointer=f"/nodes/{index}/node_id",
                )
            )
            continue

        nodes_by_id[node_id] = node
        cell = cells.get(cell_key)
        if cell is None:
            findings.append(
                ValidationFinding(
                    "recipe.cell_not_found",
                    f"Cell {cell_key[0]} version {cell_key[1]} is not registered.",
                    json_pointer=f"/nodes/{index}/cell",
                )
            )
            continue

        if cell_key in node_by_cell_key:
            findings.append(
                ValidationFinding(
                    "recipe.duplicate_cell_reference",
                    "A Recipe may include a given Geo-Cell version only once. "
                    "Create a distinct cell declaration for a distinct computation.",
                    json_pointer=f"/nodes/{index}/cell",
                )
            )
        else:
            node_by_cell_key[cell_key] = node_id

        cells_by_node[node_id] = cell

    capability_by_node: dict[str, DomainObject] = {}
    for node_id, cell in cells_by_node.items():
        capability_ref = cell["capability"]
        capability_key = _object_key(
            capability_ref["capability_id"], capability_ref["version"]
        )
        capability = capabilities.get(capability_key)
        if capability is None:
            findings.append(
                ValidationFinding(
                    "cell.capability_not_found",
                    f"Capability {capability_key[0]} version {capability_key[1]} "
                    "is not registered.",
                    json_pointer=f"/cells/{cell['cell_id']}/capability",
                )
            )
            continue
        capability_by_node[node_id] = capability

        input_ports = _port_map(capability.get("input_ports", []))
        output_ports = _port_map(capability.get("output_ports", []))
        cell_inputs = cell.get("inputs", {})
        cell_outputs = cell.get("output_contracts", {})

        for port_id, port in input_ports.items():
            if port.get("required") and port_id not in cell_inputs:
                findings.append(
                    ValidationFinding(
                        "cell.required_input_unbound",
                        f"Required input port {port_id!r} is not bound.",
                        json_pointer=f"/cells/{cell['cell_id']}/inputs/{port_id}",
                    )
                )

        for port_id in cell_inputs:
            if port_id not in input_ports:
                findings.append(
                    ValidationFinding(
                        "cell.unknown_input_port",
                        f"Input port {port_id!r} is not declared by the capability.",
                        json_pointer=f"/cells/{cell['cell_id']}/inputs/{port_id}",
                    )
                )

        for port_id, port in output_ports.items():
            if port_id not in cell_outputs:
                findings.append(
                    ValidationFinding(
                        "cell.output_contract_missing",
                        f"Capability output port {port_id!r} has no cell output contract.",
                        json_pointer=f"/cells/{cell['cell_id']}/output_contracts/{port_id}",
                    )
                )
            elif not _compatible_kind(cell_outputs[port_id]["data_kind"], port["data_kind"]):
                findings.append(
                    ValidationFinding(
                        "cell.output_kind_mismatch",
                        f"Output contract kind for {port_id!r} does not match "
                        "the capability output kind.",
                        json_pointer=f"/cells/{cell['cell_id']}/output_contracts/{port_id}",
                    )
                )

        for port_id in cell_outputs:
            if port_id not in output_ports:
                findings.append(
                    ValidationFinding(
                        "cell.unknown_output_port",
                        f"Output port {port_id!r} is not declared by the capability.",
                        json_pointer=f"/cells/{cell['cell_id']}/output_contracts/{port_id}",
                    )
                )

        parameter_schema = capability.get("parameter_schema")
        if parameter_schema is not None:
            try:
                Draft202012Validator.check_schema(parameter_schema)
                parameter_validator = Draft202012Validator(parameter_schema)
                for error in parameter_validator.iter_errors(cell.get("parameters", {})):
                    findings.append(
                        ValidationFinding(
                            "cell.parameters_invalid",
                            error.message,
                            json_pointer=f"/cells/{cell['cell_id']}/parameters",
                        )
                    )
            except SchemaError as error:
                findings.append(
                    ValidationFinding(
                        "capability.parameter_schema_invalid",
                        str(error),
                        json_pointer=f"/capabilities/{capability['capability_id']}/parameter_schema",
                    )
                )

        if artifacts is not None:
            for input_port, binding in cell_inputs.items():
                if binding["source"] == "artifact":
                    artifact_ref = binding["artifact"]
                    artifact_key = _object_key(
                        artifact_ref["artifact_id"], artifact_ref["version"]
                    )
                    if artifact_key not in artifacts:
                        findings.append(
                            ValidationFinding(
                                "cell.artifact_not_found",
                                f"Artifact {artifact_key[0]} version {artifact_key[1]} "
                                "is not registered.",
                                json_pointer=(
                                    f"/cells/{cell['cell_id']}/inputs/{input_port}/artifact"
                                ),
                            )
                        )

    expected_edges: set[tuple[str, str, str, str]] = set()
    for target_node_id, cell in cells_by_node.items():
        for input_port, binding in cell.get("inputs", {}).items():
            if binding["source"] != "cell_output":
                continue
            source_key = _object_key(binding["cell_id"], binding["cell_version"])
            source_node_id = node_by_cell_key.get(source_key)
            if source_node_id is None:
                findings.append(
                    ValidationFinding(
                        "recipe.upstream_cell_not_in_recipe",
                        f"Upstream cell {source_key[0]} version {source_key[1]} "
                        "is not a unique node in this Recipe.",
                        json_pointer=f"/cells/{cell['cell_id']}/inputs/{input_port}",
                    )
                )
                continue
            expected_edges.add(
                (source_node_id, binding["output_port"], target_node_id, input_port)
            )
            source_cell = cells_by_node[source_node_id]
            if binding["output_port"] not in source_cell.get("output_contracts", {}):
                findings.append(
                    ValidationFinding(
                        "cell.upstream_output_port_not_found",
                        f"Upstream output port {binding['output_port']!r} is not declared.",
                        json_pointer=f"/cells/{cell['cell_id']}/inputs/{input_port}",
                    )
                )

    actual_edges: set[tuple[str, str, str, str]] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    indegree = {node_id: 0 for node_id in nodes_by_id}

    for index, edge in enumerate(recipe.get("edges", [])):
        source = edge["from"]
        target = edge["to"]
        edge_key = (
            source["node_id"],
            source["output_port"],
            target["node_id"],
            target["input_port"],
        )
        if edge_key in actual_edges:
            findings.append(
                ValidationFinding(
                    "recipe.duplicate_edge",
                    "The same dependency edge is declared more than once.",
                    json_pointer=f"/edges/{index}",
                )
            )
            continue
        actual_edges.add(edge_key)

        source_cell = cells_by_node.get(source["node_id"])
        target_cell = cells_by_node.get(target["node_id"])
        target_capability = capability_by_node.get(target["node_id"])
        if source_cell is None or target_cell is None:
            findings.append(
                ValidationFinding(
                    "recipe.edge_node_not_found",
                    "An edge references a node whose cell could not be resolved.",
                    json_pointer=f"/edges/{index}",
                )
            )
            continue

        source_contract = source_cell.get("output_contracts", {}).get(source["output_port"])
        target_port = (
            _port_map(target_capability.get("input_ports", [])).get(target["input_port"])
            if target_capability is not None
            else None
        )
        if source_contract is None:
            findings.append(
                ValidationFinding(
                    "recipe.edge_output_port_not_found",
                    f"Source output port {source['output_port']!r} is not declared.",
                    json_pointer=f"/edges/{index}/from/output_port",
                )
            )
        if target_port is None:
            findings.append(
                ValidationFinding(
                    "recipe.edge_input_port_not_found",
                    f"Target input port {target['input_port']!r} is not declared.",
                    json_pointer=f"/edges/{index}/to/input_port",
                )
            )
        if source_contract is not None and target_port is not None:
            if not _compatible_kind(source_contract["data_kind"], target_port["data_kind"]):
                findings.append(
                    ValidationFinding(
                        "recipe.edge_kind_mismatch",
                        "The source output kind is incompatible with the target input kind.",
                        json_pointer=f"/edges/{index}",
                    )
                )

        if source["node_id"] in indegree and target["node_id"] in indegree:
            if target["node_id"] not in adjacency[source["node_id"]]:
                adjacency[source["node_id"]].add(target["node_id"])
                indegree[target["node_id"]] += 1

    for missing in sorted(expected_edges - actual_edges):
        findings.append(
            ValidationFinding(
                "recipe.edge_missing",
                f"Cell input binding requires edge {missing!r}, but the Recipe omits it.",
                json_pointer="/edges",
            )
        )
    for extra in sorted(actual_edges - expected_edges):
        findings.append(
            ValidationFinding(
                "recipe.edge_without_binding",
                f"Recipe edge {extra!r} has no matching cell input binding.",
                json_pointer="/edges",
            )
        )

    ready = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node_id = ready.popleft()
        visited += 1
        for downstream in adjacency[node_id]:
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                ready.append(downstream)

    if visited != len(indegree):
        findings.append(
            ValidationFinding(
                "recipe.cycle_detected",
                "Recipe dependencies contain a directed cycle.",
                json_pointer="/edges",
            )
        )

    for index, output in enumerate(recipe.get("declared_outputs", [])):
        cell = cells_by_node.get(output["node_id"])
        if cell is None or output["output_port"] not in cell.get("output_contracts", {}):
            findings.append(
                ValidationFinding(
                    "recipe.declared_output_not_found",
                    "A declared Recipe output references an unknown node or output port.",
                    json_pointer=f"/declared_outputs/{index}",
                )
            )

    return findings
