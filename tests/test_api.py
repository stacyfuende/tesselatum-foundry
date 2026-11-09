from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tessellatum_foundry.api import create_app
from tessellatum_foundry.local import LocalFoundry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"
TOKEN = "foundry-api-test-token-with-at-least-32-chars"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(tmp_path, *, maximum: int = 8192) -> TestClient:
    app = create_app(
        LocalFoundry(tmp_path),
        api_token=TOKEN,
        max_request_bytes=maximum,
    )
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_api_requires_bearer_token_and_disables_schema_docs(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").headers["cache-control"] == "no-store"
        assert client.get("/v1/capabilities").status_code == 401
        assert client.get(
            "/v1/capabilities",
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code == 401
        response = client.get("/v1/capabilities", headers=_headers())
        assert response.status_code == 200
        assert any(item["capability_id"] == "vector.buffer" for item in response.json())
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404


def test_api_ingests_reads_and_checksum_verifies_artifact_bytes(tmp_path):
    content = b'{"type":"FeatureCollection","features":[]}'
    spatial = {
        "kind": "vector",
        "crs": {"authority": "EPSG", "code": 32737},
        "geometry_types": ["Point"],
    }
    payload = {
        "artifact_id": "api.sites",
        "version": "1.0.0",
        "content_base64": base64.b64encode(content).decode("ascii"),
        "created_by": "api-test",
        "media_type": "application/vnd.tessellatum.spatial-feature-collection+json",
        "format": "Foundry Spatial Feature Collection JSON",
        "spatial": spatial,
    }

    with _client(tmp_path) as client:
        created = client.post("/v1/artifacts", headers=_headers(), json=payload)
        assert created.status_code == 200
        metadata = created.json()
        assert metadata["checksum"]["algorithm"] == "sha256"

        fetched = client.get(
            "/v1/artifacts/api.sites/1.0.0",
            headers=_headers(),
        )
        assert fetched.status_code == 200
        assert fetched.json()["checksum"] == metadata["checksum"]

        downloaded = client.get(
            "/v1/artifacts/api.sites/1.0.0/content",
            headers=_headers(),
        )
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert downloaded.headers["x-content-sha256"] == metadata["checksum"]["value"]


def test_api_registers_canonical_cell_and_recipe_definitions(tmp_path):
    with _client(tmp_path) as client:
        cell = client.post(
            "/v1/cells",
            headers=_headers(),
            json={"created_by": "api-test", "definition": _fixture("cell.valid.json")},
        )
        assert cell.status_code == 200
        assert cell.json()["definition_ref"]["definition_id"] == "buffer-buildings"

        recipe = client.post(
            "/v1/recipes",
            headers=_headers(),
            json={
                "created_by": "api-test",
                "definition": _fixture("recipe.valid.json"),
            },
        )
        assert recipe.status_code == 200
        assert (
            recipe.json()["definition_ref"]["definition_id"]
            == "buildings-buffer-recipe"
        )

        listed_cells = client.get("/v1/cells", headers=_headers())
        assert listed_cells.status_code == 200
        assert listed_cells.json()[0]["definition_ref"]["definition_id"] == (
            "buffer-buildings"
        )
        fetched_cell = client.get(
            "/v1/cells/buffer-buildings/1.0.0",
            headers=_headers(),
        )
        assert fetched_cell.status_code == 200
        assert fetched_cell.json()["cell_id"] == "buffer-buildings"

        listed_recipes = client.get("/v1/recipes", headers=_headers())
        assert listed_recipes.status_code == 200
        fetched_recipe = client.get(
            "/v1/recipes/buildings-buffer-recipe/1.0.0",
            headers=_headers(),
        )
        assert fetched_recipe.status_code == 200
        assert fetched_recipe.json()["recipe_id"] == "buildings-buffer-recipe"


def test_api_rejects_oversized_and_malformed_artifact_requests(tmp_path):
    with _client(tmp_path, maximum=1024) as client:
        oversized = client.post(
            "/v1/artifacts",
            headers=_headers(),
            json={"content_base64": "A" * 2000},
        )
        assert oversized.status_code == 413

        malformed = client.post(
            "/v1/artifacts",
            headers=_headers(),
            json={
                "artifact_id": "bad",
                "version": "1.0.0",
                "content_base64": "not-base64!",
            },
        )
        assert malformed.status_code == 422


def test_api_rejects_immutable_definition_conflicts(tmp_path):
    cell = _fixture("cell.valid.json")
    with _client(tmp_path) as client:
        first = client.post(
            "/v1/cells",
            headers=_headers(),
            json={"created_by": "api-test", "definition": cell},
        )
        assert first.status_code == 200

        changed = {**cell, "parameters": {"distance": 900, "unit": "metre"}}
        conflict = client.post(
            "/v1/cells",
            headers=_headers(),
            json={"created_by": "api-test", "definition": changed},
        )
        assert conflict.status_code == 409
