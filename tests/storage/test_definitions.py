from __future__ import annotations

import json
from pathlib import Path

import pytest

from tessellatum_foundry.storage.definitions import (
    DefinitionIntegrityError,
    ImmutableDefinitionError,
    VersionedDefinitionStore,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_cell_and_recipe_definitions_are_stored_as_immutable_versions(tmp_path):
    store = VersionedDefinitionStore(tmp_path)
    cell = load_fixture("cell.valid.json")
    recipe = load_fixture("recipe.valid.json")

    cell_record = store.put_cell(cell, created_by="definition-author")
    recipe_record = store.put_recipe(recipe, created_by="definition-author")

    assert store.get_cell(cell["cell_id"], cell["version"]) == cell
    assert store.get_recipe(recipe["recipe_id"], recipe["version"]) == recipe
    assert cell_record["checksum"]["algorithm"] == "sha256"
    assert recipe_record["checksum"]["algorithm"] == "sha256"
    assert len(store.list_records("cell")) == 1
    assert len(store.list_records("recipe")) == 1


def test_same_definition_version_is_idempotent_only_for_same_content_and_creator(tmp_path):
    store = VersionedDefinitionStore(tmp_path)
    cell = load_fixture("cell.valid.json")

    first = store.put_cell(cell, created_by="definition-author")
    repeated = store.put_cell(cell, created_by="definition-author")

    assert repeated == first

    modified = json.loads(json.dumps(cell))
    modified["parameters"]["distance"] = 250
    with pytest.raises(ImmutableDefinitionError, match="different content or creator"):
        store.put_cell(modified, created_by="definition-author")

    with pytest.raises(ImmutableDefinitionError, match="different content or creator"):
        store.put_cell(cell, created_by="another-author")


def test_definition_store_detects_checksum_tampering(tmp_path):
    store = VersionedDefinitionStore(tmp_path)
    cell = load_fixture("cell.valid.json")
    store.put_cell(cell, created_by="definition-author")
    record_path = next((tmp_path / "definitions" / "cell").rglob("*.json"))
    record_path.chmod(0o644)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["checksum"]["value"] = "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(DefinitionIntegrityError, match="checksum verification"):
        store.get_cell(cell["cell_id"], cell["version"])



def test_definition_store_checksum_covers_creator_provenance(tmp_path):
    store = VersionedDefinitionStore(tmp_path)
    cell = load_fixture("cell.valid.json")
    store.put_cell(cell, created_by="definition-author")
    record_path = next((tmp_path / "definitions" / "cell").rglob("*.json"))
    record_path.chmod(0o644)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["created_by"] = "another-author"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(DefinitionIntegrityError, match="checksum verification"):
        store.get_cell(cell["cell_id"], cell["version"])
