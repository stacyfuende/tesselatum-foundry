from __future__ import annotations

import json
from pathlib import Path

import pytest

from tessellatum_foundry.execution.external_runs import ExternalVectorBufferRunFactory
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.execution.service import ExecutionPreconditionError
from tessellatum_foundry.storage.artifacts import utc_timestamp


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"
MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def external_cell():
    cell = fixture("cell.valid.json")
    cell["inputs"]["features"] = {
        "source": "external",
        "reference": {
            "provider": "local-file",
            "dataset_id": "roads-2026",
            "uri": "file:///data/roads.geojson",
            "media_type": MEDIA_TYPE,
            "version": "2026-11-23",
        },
        "spatial": {
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 32737},
            "geometry_types": ["Point"],
        },
    }
    return cell


def make_factory(tmp_path):
    runs = RunRepository(tmp_path / "control")
    return runs, ExternalVectorBufferRunFactory(run_repository=runs)


def test_external_cell_binding_creates_source_only_queued_run(tmp_path):
    runs, factory = make_factory(tmp_path)
    run = factory.create_queued_run(
        cell=external_cell(),
        capability=fixture("capability.valid.json"),
    )

    assert run["status"] == "queued"
    assert run["input_snapshots"] == []
    assert run["source_references"] == [{
        "input_port": "features",
        "reference": {
            "provider": "local-file",
            "dataset_id": "roads-2026",
            "uri": "file:///data/roads.geojson",
            "media_type": MEDIA_TYPE,
            "version": "2026-11-23",
        },
    }]
    assert runs.get_run(run["run_id"]) == run


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:secret@example.test/roads",
        "https://example.test/roads?token=secret",
        "https://example.test/roads#secret",
    ],
)
def test_external_cell_rejects_credential_bearing_uri(tmp_path, uri):
    _, factory = make_factory(tmp_path)
    cell = external_cell()
    cell["inputs"]["features"]["reference"]["uri"] = uri

    with pytest.raises(ExecutionPreconditionError, match="must not embed credentials"):
        factory.create_queued_run(
            cell=cell,
            capability=fixture("capability.valid.json"),
        )


def test_external_cell_rejects_unsupported_selection_before_run_creation(tmp_path):
    runs, factory = make_factory(tmp_path)
    cell = external_cell()
    cell["inputs"]["features"]["reference"]["selection"] = {"bbox": [1, 2, 3, 4]}

    with pytest.raises(ExecutionPreconditionError, match="does not support source selection"):
        factory.create_queued_run(
            cell=cell,
            capability=fixture("capability.valid.json"),
        )

    assert not (runs.root / "runs").exists()


def test_external_run_retry_preserves_exact_source_reference(tmp_path):
    runs, factory = make_factory(tmp_path)
    cell = external_cell()
    capability = fixture("capability.valid.json")
    first = factory.create_queued_run(cell=cell, capability=capability)
    runs.transition(
        first["run_id"],
        expected_status="queued",
        new_status="failed",
        fields={
            "finished_at": utc_timestamp(),
            "error": {
                "code": "source.unavailable",
                "message": "Temporary source outage.",
                "retryable": True,
            },
        },
        event_type="source_unavailable",
    )

    retry = factory.create_queued_run(
        cell=cell,
        capability=capability,
        retry_of_run_id=first["run_id"],
    )

    assert retry["attempt"] == 2
    assert retry["retry_of_run_id"] == first["run_id"]
    assert retry["source_references"] == first["source_references"]


def test_external_run_retry_rejects_changed_source_identity(tmp_path):
    runs, factory = make_factory(tmp_path)
    cell = external_cell()
    capability = fixture("capability.valid.json")
    first = factory.create_queued_run(cell=cell, capability=capability)
    runs.transition(
        first["run_id"],
        expected_status="queued",
        new_status="failed",
        fields={
            "finished_at": utc_timestamp(),
            "error": {
                "code": "source.unavailable",
                "message": "Temporary source outage.",
                "retryable": True,
            },
        },
        event_type="source_unavailable",
    )
    changed = external_cell()
    changed["inputs"]["features"]["reference"]["version"] = "2026-11-24"

    with pytest.raises(ExecutionPreconditionError, match="preserve the exact external source"):
        factory.create_queued_run(
            cell=changed,
            capability=capability,
            retry_of_run_id=first["run_id"],
        )
