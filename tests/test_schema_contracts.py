from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schema"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "valid"

SCHEMA_FIXTURES = {
    "artifact.schema.json": "artifact.valid.json",
    "capability.schema.json": "capability.valid.json",
    "capability-implementation.schema.json": "capability-implementation.valid.json",
    "cell.schema.json": "cell.valid.json",
    "recipe.schema.json": "recipe.valid.json",
    "run.schema.json": "run.valid.json",
    "validation-report.schema.json": "validation-report.valid.json",
}


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_DIR.glob("*.schema.json")
    }
    schemas["_common.schema.json"] = json.loads(
        (SCHEMA_DIR / "_common.schema.json").read_text(encoding="utf-8")
    )

    registry = Registry()
    for schema in schemas.values():
        resource = Resource.from_contents(
            schema, default_specification=DRAFT202012
        )
        registry = registry.with_resource(schema["$id"], resource)
    return schemas, registry


@pytest.fixture(scope="module")
def schema_context() -> tuple[dict[str, dict], Registry]:
    return load_schemas()


def test_all_schemas_are_valid_draft_2020_12(schema_context):
    schemas, _ = schema_context
    assert len(schemas) == 8
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", name
        assert schema["$id"].startswith("urn:tessellatum-foundry:schema:"), name


@pytest.mark.parametrize("schema_name,fixture_name", SCHEMA_FIXTURES.items())
def test_valid_contract_fixtures(schema_context, schema_name, fixture_name):
    schemas, registry = schema_context
    schema = schemas[schema_name]
    instance = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker()
    )
    validator.validate(instance)


def test_cell_requires_a_capability_reference(schema_context):
    schemas, registry = schema_context
    instance = json.loads((FIXTURE_DIR / "cell.valid.json").read_text(encoding="utf-8"))
    del instance["capability"]
    validator = Draft202012Validator(
        schemas["cell.schema.json"], registry=registry, format_checker=FormatChecker()
    )
    with pytest.raises(Exception):
        validator.validate(instance)


def test_terminal_run_requires_finished_at(schema_context):
    schemas, registry = schema_context
    instance = json.loads((FIXTURE_DIR / "run.valid.json").read_text(encoding="utf-8"))
    del instance["finished_at"]
    validator = Draft202012Validator(
        schemas["run.schema.json"], registry=registry, format_checker=FormatChecker()
    )
    with pytest.raises(Exception):
        validator.validate(instance)
