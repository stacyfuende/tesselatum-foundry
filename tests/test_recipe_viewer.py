from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "viewer" / "index.html"


def test_recipe_viewer_is_standalone_and_read_only():
    source = VIEWER.read_text(encoding="utf-8")

    assert 'id="recipe-file" type="file"' in source
    assert 'id="recipe-json"' in source
    assert "recipe.nodes" in source
    assert "recipe.edges" in source
    assert "declared_outputs" in source
    assert "dependency cycle" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "eval(" not in source
    assert "read-only" in source.lower()
