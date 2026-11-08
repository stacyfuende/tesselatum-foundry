from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tessellatum_foundry.execution.docker_worker import (
    DockerWorker,
    WorkerExecutionError,
    WorkerTimeoutError,
)


_IMAGE_ID = "sha256:" + "b" * 64


class StubDigestDockerWorker(DockerWorker):
    def image_digest(self) -> str:
        return _IMAGE_ID


def _worker(**kwargs) -> DockerWorker:
    return StubDigestDockerWorker(**kwargs)


def test_docker_worker_applies_isolation_limits_and_pins_image(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        if command[1] == "run":
            captured["command"] = command
            output_mount = next(
                item
                for item in command
                if item.startswith("type=bind,") and "dst=/run/output" in item
            )
            output_dir = Path(output_mount.split("src=", 1)[1].split(",dst=", 1)[0])
            payload = {
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [],
                },
                "crs": {"authority": "EPSG", "code": 32737},
                "geometry_types": [],
            }
            output = output_dir / "result.json"
            output.write_text(json.dumps(payload), encoding="utf-8")
            output.chmod(0o644)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "tessellatum_foundry.execution.docker_worker.subprocess.run", fake_run
    )
    worker = _worker(timeout_seconds=45, memory_mib=256, cpu_count=1.5)

    result = worker.execute(
        input_bytes=b'{"type":"FeatureCollection","features":[]}',
        capability_version="1.0.0",
        input_crs={"authority": "EPSG", "code": 32737},
        measurement_crs={"authority": "EPSG", "code": 32737},
        parameters={"distance": 10, "unit": "metre"},
        runtime_image_digest=_IMAGE_ID,
    )

    command = captured["command"]
    assert _IMAGE_ID in command
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--pids-limit=128" in command
    assert "--memory=256m" in command
    assert "--memory-swap=256m" in command
    assert "--cpus=1.5" in command
    assert "--user=10001:10001" in command
    assert "--ulimit=core=0" in command
    assert "--tmpfs=/tmp:rw,noexec,nosuid,size=64m" in command
    assert f"--env=FOUNDRY_MAX_OUTPUT_BYTES={128 * 1024 * 1024}" in command
    assert result.runtime_image_digest == _IMAGE_ID
    assert result.feature_collection["type"] == "FeatureCollection"


def test_docker_worker_rejects_input_over_limit_before_launching(monkeypatch):
    def unexpected_run(*args, **kwargs):
        raise AssertionError("Docker must not be invoked for oversized input.")

    monkeypatch.setattr(
        "tessellatum_foundry.execution.docker_worker.subprocess.run", unexpected_run
    )
    worker = _worker(max_input_bytes=1)

    with pytest.raises(WorkerExecutionError, match="input byte limit"):
        worker.execute(
            input_bytes=b"too large",
            capability_version="1.0.0",
            input_crs={"authority": "EPSG", "code": 32737},
            measurement_crs={"authority": "EPSG", "code": 32737},
            parameters={"distance": 10, "unit": "metre"},
            runtime_image_digest=_IMAGE_ID,
        )


def test_docker_worker_removes_container_after_timeout(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, timeout=1)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(
        "tessellatum_foundry.execution.docker_worker.subprocess.run", fake_run
    )
    worker = _worker(timeout_seconds=1)

    with pytest.raises(WorkerTimeoutError, match="timeout"):
        worker.execute(
            input_bytes=b"{}",
            capability_version="1.0.0",
            input_crs={"authority": "EPSG", "code": 32737},
            measurement_crs={"authority": "EPSG", "code": 32737},
            parameters={"distance": 10, "unit": "metre"},
            runtime_image_digest=_IMAGE_ID,
        )

    assert any(command[:3] == ["docker", "rm", "--force"] for command in calls)
