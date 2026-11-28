from __future__ import annotations

import hashlib
import json

import pytest

from tessellatum_foundry.storage import FileSystemArtifactStore
from tessellatum_foundry.storage.artifacts import ArtifactIntegrityError
from tessellatum_foundry.storage.streaming import StreamingFeatureCollectionTransaction


def _batch(payload: bytes):
    class Batch:
        sequence = 0
        first_feature_offset = 0
        feature_count = 1
        output_checksum_sha256 = hashlib.sha256(payload).hexdigest()

        def __init__(self, data: bytes):
            self.payload = data

    return Batch(payload)


def _validated_transaction(root):
    transaction = StreamingFeatureCollectionTransaction(
        root, run_id="run:publish", attempt=1,
        max_output_bytes=100_000, max_batches=5,
    )
    payload = json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"id": 1}, "geometry": None}],
    }, separators=(",", ":"), sort_keys=True).encode()
    transaction.append(_batch(payload))
    transaction.seal_input({"eof_verified": True})
    transaction.seal_output()
    transaction.mark_validated({"passed": True, "validator": "test"})
    return transaction


def test_put_file_publishes_content_addressed_object_in_bounded_chunks(tmp_path):
    source = tmp_path / "large-output.geojson"
    source.write_bytes(b'{"features":[' + b' ' * 4096 + b"]}")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    store = FileSystemArtifactStore(tmp_path / "store")

    artifact = store.put_file(
        artifact_id="artifact:streamed",
        version="1.0.0",
        source_path=source,
        created_by="system:test",
        media_type="application/geo+json",
        format_name="geojson",
        expected_checksum_sha256=expected,
        chunk_size=31,
    )

    assert artifact["checksum"]["value"] == expected
    assert artifact["size_bytes"] == source.stat().st_size
    assert store.get_artifact("artifact:streamed", "1.0.0") == artifact
    assert store.read_bytes(artifact) == source.read_bytes()



def test_read_bytes_enforces_optional_hard_byte_limit(tmp_path):
    source = tmp_path / "bounded.geojson"
    source.write_bytes(b'{"type":"FeatureCollection","features":[]}')
    store = FileSystemArtifactStore(tmp_path / "store")
    artifact = store.put_file(
        artifact_id="artifact:bounded",
        version="1.0.0",
        source_path=source,
        created_by="system:test",
        media_type="application/geo+json",
        format_name="geojson",
    )

    with pytest.raises(ArtifactIntegrityError, match="byte limit"):
        store.read_bytes(artifact, max_bytes=1)
    assert store.read_bytes(artifact, max_bytes=source.stat().st_size) == source.read_bytes()


def test_put_file_rejects_checksum_mismatch_without_registering_metadata(tmp_path):
    source = tmp_path / "output.geojson"
    source.write_bytes(b'{"type":"FeatureCollection","features":[]}')
    store = FileSystemArtifactStore(tmp_path / "store")

    with pytest.raises(ArtifactIntegrityError, match="expected checksum"):
        store.put_file(
            artifact_id="artifact:bad",
            version="1.0.0",
            source_path=source,
            created_by="system:test",
            media_type="application/geo+json",
            format_name="geojson",
            expected_checksum_sha256="0" * 64,
        )

    with pytest.raises(FileNotFoundError):
        store.get_artifact("artifact:bad", "1.0.0")


def test_validated_stream_is_not_discoverable_until_artifact_publication(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "store")
    transaction = _validated_transaction(tmp_path / "transactions")

    with pytest.raises(FileNotFoundError):
        store.get_artifact("artifact:published", "1.0.0")

    artifact = transaction.publish_artifact(
        store,
        artifact_id="artifact:published",
        version="1.0.0",
        created_by="system:test",
        metadata={"producer_run_id": "run:publish"},
    )

    assert transaction.state == "committed"
    assert transaction.journal_path.exists()
    journal = json.loads(transaction.journal_path.read_text())
    assert journal["state"] == "committed"
    assert journal["published_artifact"] == {
        "artifact_id": "artifact:published",
        "version": "1.0.0",
    }
    assert store.get_artifact("artifact:published", "1.0.0") == artifact
    assert store.read_bytes(artifact) == transaction.payload_path.read_bytes()


def test_publication_retry_preserves_identity_and_reuses_existing_artifact(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "store")
    transaction = _validated_transaction(tmp_path / "transactions")
    original_put_file = store.put_file
    calls = 0

    def fail_after_metadata_commit(**kwargs):
        nonlocal calls
        calls += 1
        artifact = original_put_file(**kwargs)
        if calls == 1:
            raise OSError("simulated interruption after metadata commit")
        return artifact

    store.put_file = fail_after_metadata_commit
    arguments = {
        "artifact_id": "artifact:retry",
        "version": "1.0.0",
        "created_by": "system:test",
    }
    with pytest.raises(OSError, match="simulated interruption"):
        transaction.publish_artifact(store, **arguments)

    store.put_file = original_put_file
    published = transaction.publish_artifact(store, **arguments)
    assert transaction.state == "committed"
    assert store.get_artifact("artifact:retry", "1.0.0") == published


def test_recovery_reconciles_metadata_commit_after_journal_update_interruption(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "store")
    transaction = _validated_transaction(tmp_path / "transactions")
    original_persist = transaction._persist
    persist_calls = 0

    def interrupt_final_journal_write():
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 2:
            raise OSError("simulated process interruption after Artifact commit")
        original_persist()

    transaction._persist = interrupt_final_journal_write
    with pytest.raises(OSError, match="simulated process interruption"):
        transaction.publish_artifact(
            store,
            artifact_id="artifact:crash-recovery",
            version="1.0.0",
            created_by="system:test",
        )

    recovered = StreamingFeatureCollectionTransaction.recover(
        tmp_path / "transactions",
        transaction.transaction_id,
        store,
    )

    assert recovered.state == "committed"
    journal = json.loads(recovered.journal_path.read_text())
    assert journal["state"] == "committed"
    assert journal["published_artifact"] == {
        "artifact_id": "artifact:crash-recovery",
        "version": "1.0.0",
    }


def test_recovery_aborts_unpublished_nonterminal_transaction(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "store")
    transaction = _validated_transaction(tmp_path / "transactions")

    recovered = StreamingFeatureCollectionTransaction.recover(
        tmp_path / "transactions",
        transaction.transaction_id,
        store,
    )

    assert recovered.state == "aborted"
    assert json.loads(recovered.journal_path.read_text())["state"] == "aborted"
    with pytest.raises(FileNotFoundError):
        store.get_artifact("artifact:never-published", "1.0.0")


def test_recovery_refuses_committed_journal_when_object_bytes_are_corrupt(tmp_path):
    store = FileSystemArtifactStore(tmp_path / "store")
    transaction = _validated_transaction(tmp_path / "transactions")
    artifact = transaction.publish_artifact(
        store,
        artifact_id="artifact:corrupt-after-commit",
        version="1.0.0",
        created_by="system:test",
    )
    object_path = store.root / artifact["storage"]["object_key"]
    object_path.chmod(0o600)
    object_path.write_bytes(b"corrupt")

    with pytest.raises(ArtifactIntegrityError, match="failed checksum"):
        StreamingFeatureCollectionTransaction.recover(
            tmp_path / "transactions",
            transaction.transaction_id,
            store,
        )
