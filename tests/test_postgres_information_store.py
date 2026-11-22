"""Dependency-light checks for the optional PostGIS repository adapter."""

import pytest

from tessellatum_foundry.information import PostgresInformationStore


def test_adapter_can_be_imported_without_psycopg() -> None:
    """The optional database driver is loaded only when JSON adaptation is needed."""
    store = PostgresInformationStore(connection=object())
    assert store.connection is not None


@pytest.mark.parametrize(
    ("geometry_wkb", "srid", "error", "message"),
    [
        (b"", 4326, TypeError, "non-empty WKB"),
        ("not-bytes", 4326, TypeError, "non-empty WKB"),
        (b"wkb", 0, ValueError, "positive integer"),
        (b"wkb", -1, ValueError, "positive integer"),
        (b"wkb", True, ValueError, "positive integer"),
    ],
)
def test_representation_rejects_invalid_geometry_inputs(
    geometry_wkb: object,
    srid: int,
    error: type[Exception],
    message: str,
) -> None:
    store = PostgresInformationStore(connection=object())
    with pytest.raises(error, match=message):
        store.add_representation(
            entity_id="00000000-0000-0000-0000-000000000001",
            representation_version=1,
            geometry_wkb=geometry_wkb,  # type: ignore[arg-type]
            srid=srid,
            recorded_by="test",
        )


@pytest.mark.parametrize(
    ("payload", "payload_ref"),
    [
        (None, None),
        ({"name": "A"}, {"object_uri": "s3://bucket/data.parquet", "feature_id": "A"}),
    ],
)
def test_source_record_requires_exactly_one_payload_form(
    payload: dict[str, object] | None,
    payload_ref: dict[str, object] | None,
) -> None:
    store = PostgresInformationStore(connection=object())
    with pytest.raises(ValueError, match="exactly one"):
        store.insert_source_record(
            source_snapshot_id="00000000-0000-0000-0000-000000000001",
            source_record_key="record-1",
            payload=payload,
            payload_ref=payload_ref,
        )


def test_source_record_accepts_object_locator_before_database_access() -> None:
    store = PostgresInformationStore(connection=object())
    # Supplying both forms is rejected locally before driver or connection use.
    with pytest.raises(ValueError, match="exactly one"):
        store.insert_source_record(
            source_snapshot_id="00000000-0000-0000-0000-000000000001",
            source_record_key="record-1",
            payload={"id": "x"},
            payload_ref={"object_uri": "s3://bucket/source.parquet", "feature_id": "x"},
        )
