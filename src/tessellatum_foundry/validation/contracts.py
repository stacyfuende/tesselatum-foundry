"""Reusable JSON Schema validation for Foundry contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from tessellatum_foundry.data import foundry_data_dir


class ContractValidationError(ValueError):
    """Raised when a Foundry object does not satisfy its canonical schema."""

    def __init__(self, schema_name: str, errors: list[str]) -> None:
        self.schema_name = schema_name
        self.errors = tuple(errors)
        detail = "; ".join(errors)
        super().__init__(f"{schema_name} validation failed: {detail}")


class ContractRegistry:
    """Load and apply the repository's canonical Draft 2020-12 schemas."""

    def __init__(self, schema_dir: Path | None = None) -> None:
        self.schema_dir = schema_dir or foundry_data_dir("schema")
        self.schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        registry = Registry()
        for path in sorted(self.schema_dir.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.schemas[path.name] = schema
            registry = registry.with_resource(
                schema["$id"],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
        for name, schema in self.schemas.items():
            self._validators[name] = Draft202012Validator(
                schema,
                registry=registry,
                format_checker=FormatChecker(),
            )

    def validate(self, schema_name: str, value: Any) -> None:
        """Validate an object, reporting stable JSON-pointer locations."""
        validator = self._validators.get(schema_name)
        if validator is None:
            raise KeyError(f"Unknown Foundry schema: {schema_name}")
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            rendered = [
                f"/{'/'.join(str(part) for part in error.absolute_path)}: "
                f"{error.message}"
                for error in errors
            ]
            raise ContractValidationError(schema_name, rendered)

    def schema(self, schema_name: str) -> dict[str, Any]:
        """Return a loaded schema for operation-specific nested validation."""
        try:
            return self.schemas[schema_name]
        except KeyError as error:
            raise KeyError(f"Unknown Foundry schema: {schema_name}") from error
