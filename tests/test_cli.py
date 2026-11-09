from __future__ import annotations

import json
from pathlib import Path

from tessellatum_foundry.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_cli_initializes_workspace_and_lists_registries(tmp_path, capsys):
    status = main(["--data-dir", str(tmp_path), "init"])

    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert payload["status"] == "ready"
    assert Path(payload["workspace"]) == tmp_path.resolve()
    assert payload["capabilities"] >= 2
    assert payload["implementations"] >= 2


def test_cli_registers_immutable_cell_and_recipe_definitions(tmp_path, capsys):
    workspace = str(tmp_path / "workspace")
    cell_path = FIXTURES / "cell.valid.json"
    recipe_path = FIXTURES / "recipe.valid.json"

    assert main(
        [
            "--data-dir",
            workspace,
            "cell",
            "register",
            "--file",
            str(cell_path),
            "--created-by",
            "cli-test",
        ]
    ) == 0
    cell_record = json.loads(capsys.readouterr().out)
    assert cell_record["definition_ref"]["definition_id"] == json.loads(
        cell_path.read_text(encoding="utf-8")
    )["cell_id"]

    assert main(
        [
            "--data-dir",
            workspace,
            "recipe",
            "register",
            "--file",
            str(recipe_path),
            "--created-by",
            "cli-test",
        ]
    ) == 0
    recipe_record = json.loads(capsys.readouterr().out)
    assert recipe_record["definition_ref"]["definition_id"] == json.loads(
        recipe_path.read_text(encoding="utf-8")
    )["recipe_id"]


def test_cli_ingests_inspects_and_exports_checksum_verified_artifact(
    tmp_path, capsys
):
    workspace = str(tmp_path / "workspace")
    source = tmp_path / "input.geojson"
    source.write_text(
        '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
    )
    spatial_path = _write_json(
        tmp_path / "spatial.json",
        {
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 32737},
            "geometry_types": ["Point"],
        },
    )

    assert main(
        [
            "--data-dir",
            workspace,
            "artifact",
            "put",
            "--id",
            "sites",
            "--version",
            "1.0.0",
            "--file",
            str(source),
            "--created-by",
            "cli-test",
            "--media-type",
            "application/geo+json",
            "--format",
            "GeoJSON",
            "--spatial-json",
            str(spatial_path),
        ]
    ) == 0
    stored = json.loads(capsys.readouterr().out)
    assert stored["artifact_id"] == "sites"

    assert main(
        [
            "--data-dir",
            workspace,
            "artifact",
            "show",
            "--id",
            "sites",
            "--version",
            "1.0.0",
        ]
    ) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["checksum"] == stored["checksum"]

    exported = tmp_path / "exports" / "sites.geojson"
    assert main(
        [
            "--data-dir",
            workspace,
            "artifact",
            "export",
            "--id",
            "sites",
            "--version",
            "1.0.0",
            "--output",
            str(exported),
        ]
    ) == 0
    export_result = json.loads(capsys.readouterr().out)
    assert export_result["checksum_verified"] is True
    assert exported.read_bytes() == source.read_bytes()


def test_cli_reports_invalid_artifact_metadata_without_traceback(tmp_path, capsys):
    status = main(
        [
            "--data-dir",
            str(tmp_path),
            "artifact",
            "show",
            "--id",
            "missing",
            "--version",
            "1.0.0",
        ]
    )

    captured = capsys.readouterr()
    assert status == 2
    assert "was not found" in captured.err
    assert captured.out == ""
