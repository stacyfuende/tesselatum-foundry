from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schema"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "valid"

FIXTURES = {
    "artifact.schema.json": "artifact.valid.json",
    "capability.schema.json": "capability.valid.json",
    "capability-implementation.schema.json": "capability-implementation.valid.json",
    "cell.schema.json": "cell.valid.json",
    "recipe.schema.json": "recipe.valid.json",
    "run.schema.json": "run.valid.json",
    "validation-report.schema.json": "validation-report.valid.json",
}


def main() -> int:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_DIR.glob("*.schema.json")
    }
    schemas["_common.schema.json"] = json.loads(
        (SCHEMA_DIR / "_common.schema.json").read_text(encoding="utf-8")
    )

    registry = Registry()
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        if not schema.get("$id", "").startswith("urn:tessellatum-foundry:schema:"):
            raise ValueError(f"{name} is missing a Foundry schema identifier")
        registry = registry.with_resource(
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )

    for schema_name, fixture_name in FIXTURES.items():
        validator = Draft202012Validator(
            schemas[schema_name], registry=registry, format_checker=FormatChecker()
        )
        fixture = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
        validator.validate(fixture)
        print(f"PASS {schema_name} <- {fixture_name}")

    print(f"Validated {len(schemas)} schemas and {len(FIXTURES)} fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
