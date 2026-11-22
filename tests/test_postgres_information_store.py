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
