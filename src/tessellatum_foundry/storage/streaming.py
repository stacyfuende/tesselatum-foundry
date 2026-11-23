"""Private bounded staging and recoverable publication for streamed outputs."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any


class StreamingTransactionError(RuntimeError):
    """Raised when a streamed output transaction violates its state or bounds."""


_TERMINAL = {"committed", "aborted"}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    descriptor, name = tempfile.mkstemp(prefix=".journal-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class StreamingFeatureCollectionTransaction:
    """Append verified processed batches to a private, bounded staging file.

    The file is a provisional GeoJSON FeatureCollection, not a published
    Artifact. Only one writer is supported per transaction in this process.
    """

    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        attempt: int,
        max_output_bytes: int,
        max_batches: int,
    ) -> None:
        if not isinstance(run_id, str) or not run_id or isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("A Run ID and positive attempt are required.")
        if max_output_bytes < 1 or max_batches < 1:
            raise ValueError("Transaction limits must be positive.")
        self.root = root.resolve()
        self.transaction_id = str(uuid.uuid4())
        self.directory = self.root / "staging" / self.transaction_id
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.directory.chmod(0o700)
        self.payload_path = self.directory / "output.geojson"
        self.journal_path = self.directory / "journal.json"
        self._stream = self.payload_path.open("xb")
        self.payload_path.chmod(0o600)
        self._stream.write(b'{"type":"FeatureCollection","features":[')
        self._has_feature = False
        self._lock = threading.Lock()
        self._bytes = self.payload_path.stat().st_size
        self._feature_count = 0
        self._next_sequence = 0
        self._next_offset = 0
        self._max_output_bytes = max_output_bytes
        self._max_batches = max_batches
        self._state = "open"
        self._record = {
            "transaction_id": self.transaction_id,
            "run_id": run_id,
            "attempt": attempt,
            "state": self._state,
            "next_batch_sequence": 0,
            "next_feature_offset": 0,
            "batch_count": 0,
            "feature_count": 0,
            "staged_bytes": self._bytes,
            "max_output_bytes": max_output_bytes,
            "max_batches": max_batches,
            "source_completion": None,
            "output_checksum_sha256": None,
        }
        self._persist()

    @property
    def state(self) -> str:
        return self._state

    def append(self, batch: Any) -> None:
        with self._lock:
            self._require("open")
            sequence = getattr(batch, "sequence", None)
            offset = getattr(batch, "first_feature_offset", None)
            count = getattr(batch, "feature_count", None)
            payload = getattr(batch, "payload", None)
            expected_checksum = getattr(batch, "output_checksum_sha256", None)
            if sequence != self._next_sequence or offset != self._next_offset:
                raise StreamingTransactionError("Batch sequence or feature offset is not contiguous.")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise StreamingTransactionError("Batch feature count is invalid.")
            if self._record["batch_count"] >= self._max_batches:
                raise StreamingTransactionError("Transaction batch limit exceeded.")
            if not isinstance(payload, bytes) or not isinstance(expected_checksum, str):
                raise StreamingTransactionError("Batch payload and checksum are required.")
            actual = hashlib.sha256(payload).hexdigest()
            if actual != expected_checksum:
                raise StreamingTransactionError("Processed batch checksum verification failed.")
            try:
                collection = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StreamingTransactionError("Processed batch is not valid JSON.") from error
            features = collection.get("features") if isinstance(collection, dict) else None
            if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) != count:
                raise StreamingTransactionError("Batch payload does not match its feature count.")
            encoded = []
            for feature in features:
                try:
                    encoded.append(json.dumps(feature, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                except (TypeError, ValueError) as error:
                    raise StreamingTransactionError("Feature is not finite JSON.") from error
            addition = (b"," if self._has_feature else b"") + b",".join(encoded)
            projected = self._bytes + len(addition) + 2
            if projected > self._max_output_bytes:
                raise StreamingTransactionError("Transaction output byte limit exceeded.")
            self._stream.write(addition)
            self._bytes += len(addition)
            self._feature_count += count
            self._next_sequence += 1
            self._next_offset += count
            self._has_feature = True
            self._record.update({
                "next_batch_sequence": self._next_sequence,
                "next_feature_offset": self._next_offset,
                "batch_count": self._next_sequence,
                "feature_count": self._feature_count,
                "staged_bytes": self._bytes,
            })
            self._persist()

    def seal_input(self, source_completion: dict[str, Any]) -> None:
        with self._lock:
            self._require("open")
            if not isinstance(source_completion, dict) or source_completion.get("eof_verified") is not True:
                raise StreamingTransactionError("Source EOF and integrity verification are required.")
            self._record["source_completion"] = source_completion
            self._state = "input_sealed"
            self._record["state"] = self._state
            self._persist()

    def seal_output(self) -> dict[str, Any]:
        with self._lock:
            self._require("input_sealed")
            if self._feature_count < 1:
                raise StreamingTransactionError("Cannot seal an empty output FeatureCollection.")
            self._stream.write(b"]}")
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream.close()
            final_size = self.payload_path.stat().st_size
            if final_size > self._max_output_bytes:
                raise StreamingTransactionError("Final output exceeds transaction byte limit.")
            checksum = hashlib.sha256()
            with self.payload_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
            self._state = "output_sealed"
            self._record.update({
                "state": self._state,
                "staged_bytes": final_size,
                "output_checksum_sha256": checksum.hexdigest(),
            })
            self._persist()
            return dict(self._record)

    def mark_validated(self, validation_evidence: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._require("output_sealed")
            if not isinstance(validation_evidence, dict) or validation_evidence.get("passed") is not True:
                raise StreamingTransactionError("Passing whole-output validation evidence is required.")
            self._state = "validated"
            self._record["state"] = self._state
            self._record["validation_evidence"] = validation_evidence
            self._persist()
            return dict(self._record)

    def publish_artifact(
        self,
        artifact_store: Any,
        *,
        artifact_id: str,
        version: str,
        created_by: str,
        media_type: str = "application/geo+json",
        format_name: str = "geojson",
        spatial: dict[str, Any] | None = None,
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> dict[str, Any]:
        """Publish validated staging as an immutable Artifact.

        The publication intent is journaled before touching the Artifact
        store. Retrying the same identity is safe if metadata was committed
        but this transaction's final journal update was interrupted.
        """
        with self._lock:
            if self._state != "validated":
                raise StreamingTransactionError("Only validated output can be published once.")
            identity = {"artifact_id": artifact_id, "version": version}
            previous_intent = self._record.get("publication_intent")
            if previous_intent is not None and previous_intent != identity:
                raise StreamingTransactionError("Publication retry must preserve Artifact identity.")
            self._record["publication_intent"] = identity
            self._persist()

            artifact_metadata = dict(metadata or {})
            run_id = self._record["run_id"]
            if artifact_metadata.get("producer_run_id", run_id) != run_id:
                raise StreamingTransactionError("Artifact metadata cannot reference a different producer Run.")
            artifact_metadata["producer_run_id"] = run_id
            artifact_metadata["producer_run_attempt"] = self._record["attempt"]
            artifact = artifact_store.put_file(
                artifact_id=artifact_id,
                version=version,
                source_path=self.payload_path,
                created_by=created_by,
                media_type=media_type,
                format_name=format_name,
                expected_checksum_sha256=self._record["output_checksum_sha256"],
                spatial=spatial,
                rights=rights,
                metadata=artifact_metadata,
                chunk_size=chunk_size,
            )
            self._record.update({
                "state": "committed",
                "published_artifact": identity,
                "published_checksum_sha256": artifact["checksum"]["value"],
            })
            self._persist()
            self._state = "committed"
            return artifact

    @classmethod
    def recover(
        cls,
        root: Path,
        transaction_id: str,
        artifact_store: Any,
    ) -> "StreamingFeatureCollectionTransaction":
        """Reconcile a journal after process restart without guessing at resume.

        A durable matching Artifact metadata record proves publication committed,
        even if the process died before the final journal update. All other
        nonterminal states are aborted; batch-level resume is intentionally not
        attempted because the current journal is not a durable source checkpoint.
        """
        try:
            parsed_id = uuid.UUID(transaction_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise StreamingTransactionError("Transaction ID must be a canonical UUID.") from error
        if str(parsed_id) != transaction_id:
            raise StreamingTransactionError("Transaction ID must be a canonical UUID.")
        directory = Path(root).resolve() / "staging" / transaction_id
        journal_path = directory / "journal.json"
        payload_path = directory / "output.geojson"
        if not journal_path.is_file():
            raise FileNotFoundError("Streaming transaction journal was not found.")
        try:
            record = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StreamingTransactionError("Streaming transaction journal is unreadable.") from error
        if record.get("transaction_id") != transaction_id:
            raise StreamingTransactionError("Transaction journal identity does not match its directory.")

        transaction = cls.__new__(cls)
        transaction.root = Path(root).resolve()
        transaction.transaction_id = transaction_id
        transaction.directory = directory
        transaction.payload_path = payload_path
        transaction.journal_path = journal_path
        transaction._stream = None
        transaction._lock = threading.Lock()
        transaction._bytes = record.get("staged_bytes", 0)
        transaction._feature_count = record.get("feature_count", 0)
        transaction._next_sequence = record.get("next_batch_sequence", 0)
        transaction._next_offset = record.get("next_feature_offset", 0)
        transaction._max_output_bytes = record.get("max_output_bytes", 0)
        transaction._max_batches = record.get("max_batches", 0)
        transaction._has_feature = transaction._feature_count > 0
        transaction._record = record
        transaction._state = record.get("state")

        if transaction._state in _TERMINAL:
            if transaction._state == "committed":
                transaction._verify_committed_artifact(artifact_store)
            return transaction

        intent = record.get("publication_intent")
        if intent is not None:
            try:
                artifact = artifact_store.get_artifact(
                    intent["artifact_id"], intent["version"]
                )
            except FileNotFoundError:
                artifact = None
            if artifact is not None:
                expected = record.get("output_checksum_sha256")
                if (
                    artifact.get("checksum", {}).get("value") != expected
                    or artifact.get("size_bytes") != record.get("staged_bytes")
                    or artifact.get("metadata", {}).get("producer_run_id") != record.get("run_id")
                    or artifact.get("metadata", {}).get("producer_run_attempt") != record.get("attempt")
                ):
                    raise StreamingTransactionError(
                        "Published Artifact does not match the transaction journal."
                    )
                artifact_store.verify_artifact(artifact)
                transaction._record.update({
                    "state": "committed",
                    "published_artifact": intent,
                    "published_checksum_sha256": expected,
                })
                transaction._persist()
                transaction._state = "committed"
                return transaction

        transaction.abort("recovery.incomplete_or_unpublished")
        return transaction

    def _verify_committed_artifact(self, artifact_store: Any) -> None:
        identity = self._record.get("published_artifact") or self._record.get("publication_intent")
        if not isinstance(identity, dict):
            raise StreamingTransactionError("Committed transaction has no Artifact identity.")
        try:
            artifact = artifact_store.get_artifact(identity["artifact_id"], identity["version"])
        except FileNotFoundError as error:
            raise StreamingTransactionError("Committed transaction Artifact metadata is missing.") from error
        if (
            artifact.get("checksum", {}).get("value") != self._record.get("published_checksum_sha256")
            or artifact.get("checksum", {}).get("value") != self._record.get("output_checksum_sha256")
            or artifact.get("size_bytes") != self._record.get("staged_bytes")
            or artifact.get("metadata", {}).get("producer_run_id") != self._record.get("run_id")
            or artifact.get("metadata", {}).get("producer_run_attempt") != self._record.get("attempt")
        ):
            raise StreamingTransactionError("Committed Artifact metadata fails transaction reconciliation.")
        artifact_store.verify_artifact(artifact)

    def abort(self, reason_code: str) -> None:
        with self._lock:
            if self._state in _TERMINAL:
                raise StreamingTransactionError("Terminal transaction cannot be changed.")
            if self._stream and not self._stream.closed:
                self._stream.close()
            self._state = "aborted"
            self._record.update({"state": self._state, "abort_reason_code": reason_code})
            self._persist()

    def _require(self, expected: str) -> None:
        if self._state != expected:
            raise StreamingTransactionError(f"Transaction is {self._state!r}, expected {expected!r}.")

    def _persist(self) -> None:
        _atomic_json(self.journal_path, self._record)
