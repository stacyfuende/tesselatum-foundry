"""Immutable versioned storage for Geo-Cell and Recipe definitions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from tessellatum_foundry.storage.artifacts import utc_timestamp
from tessellatum_foundry.validation.contracts import ContractRegistry

DefinitionKind = Literal["cell", "recipe"]


class ImmutableDefinitionError(RuntimeError):
    """Raised when an existing definition ID/version is assigned new content."""


class DefinitionIntegrityError(RuntimeError):
    """Raised when a stored definition record or checksum is invalid."""


class VersionedDefinitionStore:
    """Persist immutable, schema-validated Cell and Recipe versions."""

    def __init__(
        self,
        root: Path,
        contracts: ContractRegistry | None = None,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.contracts = contracts or ContractRegistry()

    def put_cell(
        self, cell: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        return self.put("cell", cell, created_by=created_by)

    def put_recipe(
        self, recipe: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        return self.put("recipe", recipe, created_by=created_by)

    def put(
        self,
        kind: DefinitionKind,
        definition: dict[str, Any],
        *,
        created_by: str,
    ) -> dict[str, Any]:
        schema_name = self._schema_name(kind)
        self.contracts.validate(schema_name, definition)
        _, definition_id = self._identity(kind, definition)
        payload = {
            "kind": kind,
            "definition_ref": {
                "definition_id": definition_id,
                "version": definition["version"],
            },
            "created_at": utc_timestamp(),
            "created_by": created_by,
            "definition": definition,
        }
        checksum = hashlib.sha256(self._canonical_json(payload)).hexdigest()
        record = {
            **payload,
            "checksum": {"algorithm": "sha256", "value": checksum},
        }
        self.contracts.validate("definition-record.schema.json", record)
        path = self._record_path(kind, definition_id, definition["version"])
        serialized = self._canonical_json(record, indent=2)
        try:
            self._write_once(path, serialized)
        except FileExistsError:
            existing = self.get(kind, definition_id, definition["version"])
            if (
                existing["definition"] != definition
                or existing["created_by"] != created_by
            ):
                raise ImmutableDefinitionError(
                    f"{kind} {definition_id}@{definition['version']} already exists "
                    "with different content or creator."
                )
            return existing
        return record

    def get_cell(self, cell_id: str, version: str) -> dict[str, Any]:
        return self.get("cell", cell_id, version)["definition"]

    def get_recipe(self, recipe_id: str, version: str) -> dict[str, Any]:
        return self.get("recipe", recipe_id, version)["definition"]

    def get(
        self, kind: DefinitionKind, definition_id: str, version: str
    ) -> dict[str, Any]:
        path = self._record_path(kind, definition_id, version)
        if not path.is_file():
            raise FileNotFoundError(
                f"{kind} {definition_id}@{version} was not found."
            )
        record = json.loads(path.read_text(encoding="utf-8"))
        self.contracts.validate("definition-record.schema.json", record)
        schema_name = self._schema_name(kind)
        self.contracts.validate(schema_name, record["definition"])
        _, actual_id = self._identity(kind, record["definition"])
        if (
            record["kind"] != kind
            or actual_id != definition_id
            or record["definition"]["version"] != version
            or record["definition_ref"]
            != {"definition_id": definition_id, "version": version}
        ):
            raise DefinitionIntegrityError(
                "Stored definition identity does not match its registry path."
            )
        integrity_payload = {
            key: record[key]
            for key in ("kind", "definition_ref", "created_at", "created_by", "definition")
        }
        actual_checksum = hashlib.sha256(
            self._canonical_json(integrity_payload)
        ).hexdigest()
        if actual_checksum != record["checksum"]["value"]:
            raise DefinitionIntegrityError(
                f"{kind} {definition_id}@{version} failed checksum verification."
            )
        return record

    def list_records(self, kind: DefinitionKind) -> list[dict[str, Any]]:
        if kind not in {"cell", "recipe"}:
            raise ValueError(f"Unsupported definition kind: {kind!r}.")
        records = []
        directory = self.root / "definitions" / kind
        if not directory.is_dir():
            return []
        for path in directory.rglob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            self.contracts.validate("definition-record.schema.json", record)
            definition_id = record["definition_ref"]["definition_id"]
            version = record["definition_ref"]["version"]
            records.append(self.get(kind, definition_id, version))
        return sorted(
            records,
            key=lambda item: (
                item["definition_ref"]["definition_id"],
                item["definition_ref"]["version"],
            ),
        )

    @staticmethod
    def _schema_name(kind: DefinitionKind) -> str:
        if kind == "cell":
            return "cell.schema.json"
        if kind == "recipe":
            return "recipe.schema.json"
        raise ValueError(f"Unsupported definition kind: {kind!r}.")

    @staticmethod
    def _identity(
        kind: DefinitionKind, definition: dict[str, Any]
    ) -> tuple[str, str]:
        if kind == "cell":
            return "cell.schema.json", definition["cell_id"]
        if kind == "recipe":
            return "recipe.schema.json", definition["recipe_id"]
        raise ValueError(f"Unsupported definition kind: {kind!r}.")

    def _record_path(self, kind: DefinitionKind, definition_id: str, version: str) -> Path:
        key = hashlib.sha256(
            f"{kind}\0{definition_id}\0{version}".encode()
        ).hexdigest()
        return self.root / "definitions" / kind / key[:2] / f"{key}.json"

    @staticmethod
    def _canonical_json(value: dict[str, Any], *, indent: int | None = None) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=None if indent else (",", ":"),
            indent=indent,
        ).encode("utf-8")

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".definition-", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise
            path.chmod(0o444)
        finally:
            temporary.unlink(missing_ok=True)
