"""Smoke-test canonical schemas, templates, and manifests from an installed distribution."""

import json
from importlib.resources import files

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.implementations import ImplementationRegistry
from tessellatum_foundry.validation.contracts import ContractRegistry


def main() -> None:
    contracts = ContractRegistry()
    implementations = ImplementationRegistry(contracts=contracts)
    capabilities = CapabilityRegistry(contracts=contracts)
    required_schemas = {
        "autonomy_policy.schema.json",
        "cartographic_specification.schema.json",
        "spatial_product_blueprint.schema.json",
    }
    missing_schemas = sorted(required_schemas - contracts.schemas.keys())
    if missing_schemas:
        raise SystemExit(
            "Installed distribution is missing required schemas: "
            + ", ".join(missing_schemas)
        )
    product_template = files("tessellatum_foundry").joinpath(
        "product_templates", "nairobi-site-coordinate-standardization.json"
    )
    if not product_template.is_file():
        raise SystemExit("Installed distribution is missing the Nairobi product template.")
    template = json.loads(product_template.read_text(encoding="utf-8"))
    if template.get("blueprint_id") != "nairobi-site-coordinate-standardization":
        raise SystemExit("Installed Nairobi product template has an unexpected identity.")
    capabilities.get("vector.buffer", "1.0.0")
    capabilities.get("raster.window", "1.0.0")
    raster_manifest = implementations.get("raster-window-python", "1.0.0")
    if raster_manifest["conformance"]["status"] != "passed":
        raise SystemExit(
            "Raster implementation must pass its conformance suite before distribution."
        )
    implementations.require_conformant(
        implementation_id="vector-buffer-shapely",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )
    implementations.require_conformant(
        implementation_id="vector-buffer-postgis",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )
    print(
        "Installed Foundry schemas, product templates, Capability contracts, "
        "and implementation manifests resolved successfully."
    )


if __name__ == "__main__":
    main()
