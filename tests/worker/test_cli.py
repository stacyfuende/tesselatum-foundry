from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tessellatum_foundry.worker.cli import _write_json_once_or_replace


def test_worker_stages_host_readable_json_output(tmp_path: Path):
    output = tmp_path / "output" / "result.json"

    _write_json_once_or_replace(output, {"result": {"count": 3}})

    assert json.loads(output.read_text(encoding="utf-8")) == {"result": {"count": 3}}
    assert stat.S_IMODE(output.stat().st_mode) == 0o644


def test_worker_does_not_publish_non_finite_json(tmp_path: Path):
    output = tmp_path / "output" / "result.json"

    with pytest.raises(ValueError, match="Out of range float"):
        _write_json_once_or_replace(output, {"value": float("nan")})

    assert not output.exists()
    assert not list(output.parent.glob(".result-*"))
