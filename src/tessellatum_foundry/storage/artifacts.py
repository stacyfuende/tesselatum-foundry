"""Immutable content-addressed local Artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from tessellatum_foundry.validation.contracts import ContractRegistry


class ImmutableArtifactError(RuntimeError):
    """Raised when a caller attempts to change an existing Artifact version."""


class ArtifactIntegrityError(RuntimeError):
    """Raised when stored bytes do not match their immutable checksum."""


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _identity_key(artifact_id: str, version: str) -> str:
    return hashlib.sha256(f"{artifact_id}\0{version}".encode()).hexdigest()


class FileSystemArtifactStore:
    """A development/local store with immutable SHA-256-addressed object bytes.

    Artifact metadata is stored separately from object bytes. This is a local
    execution adapter, not a claim that file:// URIs are portable across hosts.
    """

    def __init__(self, root: Path, contracts: ContractRegistry | None = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.contracts = contracts or ContractRegistry()

    def put_bytes(
        self,
        *,
        artifact_id: str,
        version: str,
        content: bytes,
        created_by: str,
        media_type: str,
        format_name: str,
        spatial: dict[str, Any] | None = None,
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, bytes):
            raise TypeError("Artifact content must be bytes.")
        checksum = hashlib.sha256(content).hexdigest()
        object_key = f"objects/sha256/{checksum[:2]}/{checksum}"
        object_path = self.root / object_key
        try:
            self._write_once(object_path, content)
        except FileExistsError:
            existing_bytes = object_path.read_bytes()
            if hashlib.sha256(existing_bytes).hexdigest() != checksum:
                raise ArtifactIntegrityError(
                    f"Content-addressed object {checksum} is corrupted."
                )

        record: dict[str, Any] = {
            "artifact_id": artifact_id,
            "version": version,
            "created_at": utc_timestamp(),
            "created_by": created_by,
            "media_type": media_type,
            "format": format_name,
            "size_bytes": len(content),
            "checksum": {"algorithm": "sha256", "value": checksum},
            "storage": {
                "uri": object_path.resolve().as_uri(),
                "provider": "foundry-filesystem",
                "object_key": object_key,
            },
        }
        if spatial is not None:
            record["spatial"] = spatial
        if rights is not None:
            record["rights"] = rights
        if metadata:
            record["metadata"] = metadata
        self.contracts.validate("artifact.schema.json", record)

        metadata_path = self._metadata_path(artifact_id, version)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            record, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
        ).encode("utf-8")
        try:
            self._write_once(metadata_path, serialized)
        except FileExistsError:
            existing = self.get_artifact(artifact_id, version)
            stable_fields = (
                "media_type",
                "format",
                "created_by",
                "checksum",
                "size_bytes",
                "spatial",
                "rights",
                "metadata",
            )
            if any(existing.get(field) != record.get(field) for field in stable_fields):
                raise ImmutableArtifactError(
                    f"Artifact {artifact_id}@{version} already exists with "
                    "different content or metadata."
                )
            return existing
        return record

    def get_artifact(self, artifact_id: str, version: str) -> dict[str, Any]:
        path = self._metadata_path(artifact_id, version)
        if not path.is_file():
            raise FileNotFoundError(f"Artifact {artifact_id}@{version} was not found.")
        record = json.loads(path.read_text(encoding="utf-8"))
        self.contracts.validate("artifact.schema.json", record)
        return record

    def read_bytes(self, artifact: dict[str, Any]) -> bytes:
        """Read an Artifact only through a validated store-relative object key."""
        object_key = artifact["storage"].get("object_key")
        if not isinstance(object_key, str):
            raise ArtifactIntegrityError("Artifact storage record has no object key.")
        relative = PurePosixPath(object_key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactIntegrityError("Artifact object key escapes the store root.")
        path = (self.root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(self.root):
            raise ArtifactIntegrityError("Artifact object path escapes the store root.")
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        expected = artifact["checksum"]["value"]
        if actual != expected or len(content) != artifact.get("size_bytes"):
            raise ArtifactIntegrityError(
                f"Artifact {artifact['artifact_id']}@{artifact['version']} "
                "failed checksum verification."
            )
        return content

    def _metadata_path(self, artifact_id: str, version: str) -> Path:
        key = _identity_key(artifact_id, version)
        return self.root / "metadata" / "artifacts" / key[:2] / f"{key}.json"

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".foundry-", dir=path.parent)
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
