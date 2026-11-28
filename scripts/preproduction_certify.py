from __future__ import annotations

"""Run Foundry's repeatable pre-production certification gates.

Local profile: no cloud account or Docker daemon required. Docker-backed tests
are skipped unless their worker image environment variables are supplied.
CI profile: builds the worker images and runs the same checks with the full
Docker/PostGIS integration suite enabled.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VECTOR_IMAGE = "tessellatum-foundry/vector-buffer-shapely:certification"
DEFAULT_REMOTE_IMAGE = "tessellatum-foundry/vector-buffer-remote:certification"


def _run_step(
    name: str,
    command: list[str],
    *,
    env: dict[str, str],
    cwd: Path = ROOT,
) -> dict[str, Any]:
    print(f"\n=== {name} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    started = time.monotonic()
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    result = {
        "name": name,
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "status": "passed" if completed.returncode == 0 else "failed",
    }
    print(f"=== {name}: {result['status'].upper()} ===", flush=True)
    return result


def _installed_distribution_check(env: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="foundry-certification-") as temporary:
        temporary_path = Path(temporary)
        venv_path = temporary_path / "venv"
        result = _run_step(
            "Create isolated installed-package environment",
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv_path)],
            env=env,
        )
        if result["exit_code"] != 0:
            return result

        python = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = _run_step(
            "Install Foundry distribution",
            [str(python), "-m", "pip", "install", "--no-deps", "."],
            env=env,
        )
        if install["exit_code"] != 0:
            return install

        return _run_step(
            "Verify installed schemas, templates and implementation manifests",
            [str(python), str(ROOT / "scripts" / "check_installed_data.py")],
            env=env,
            cwd=temporary_path,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("local", "ci"),
        default="local",
        help="local skips Docker image builds; ci requires Docker and enables worker integration tests",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "build" / "preproduction-certification.json",
        help="JSON report destination (default: build/preproduction-certification.json)",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    steps: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    def record(result: dict[str, Any]) -> bool:
        steps.append(result)
        return result["exit_code"] == 0

    if args.profile == "ci":
        if shutil.which("docker") is None:
            print("CI profile requires Docker, but the docker executable was not found.", file=sys.stderr)
            return 2
        env.setdefault("FOUNDRY_VECTOR_BUFFER_IMAGE", DEFAULT_VECTOR_IMAGE)
        env.setdefault("FOUNDRY_VECTOR_BUFFER_REMOTE_IMAGE", DEFAULT_REMOTE_IMAGE)
        if not env.get("FOUNDRY_POSTGIS_DSN"):
            print("CI profile requires FOUNDRY_POSTGIS_DSN for PostGIS integration tests.", file=sys.stderr)
            return 2
    else:
        if not env.get("FOUNDRY_VECTOR_BUFFER_IMAGE"):
            skipped.append({
                "name": "Docker-backed worker integration tests",
                "reason": "local profile: set FOUNDRY_VECTOR_BUFFER_IMAGE to enable these tests",
            })

    commands: list[tuple[str, list[str]]] = [
        ("Python lint", [sys.executable, "-m", "ruff", "check", "."]),
        ("Schema, fixture, Capability and implementation validation",
         [sys.executable, "scripts/validate_schemas.py"]),
    ]

    if args.profile == "ci":
        commands.extend([
            ("Build isolated Shapely worker image",
             ["docker", "build", "--file", "workers/vector_buffer/Dockerfile",
              "--tag", env["FOUNDRY_VECTOR_BUFFER_IMAGE"], "."]),
            ("Build authenticated remote worker image",
             ["docker", "build", "--file", "workers/vector_buffer/Dockerfile.remote",
              "--tag", env["FOUNDRY_VECTOR_BUFFER_REMOTE_IMAGE"], "."]),
        ])

    commands.append(("Full automated test suite", [sys.executable, "-m", "pytest", "-q"]))

    for name, command in commands:
        if not record(_run_step(name, command, env=env)):
            break
    else:
        record(_installed_distribution_check(env))

    failed = [step for step in steps if step["status"] != "passed"]
    report = {
        "certification": "Tessellatum Foundry pre-production",
        "profile": args.profile,
        "status": "failed" if failed else "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": None,
        "steps": steps,
        "skipped": skipped,
        "limitations": [
            "A local pass is not proof of production identity, cloud IAM, TLS, network policy or managed-storage behaviour.",
            "The CI profile uses ephemeral CI services; it does not certify backups, restore or real customer tenancy in a hosted environment.",
            "The live external Nairobi raster smoke test remains a separate network-dependent check.",
            "A real browser-driven customer journey remains a separate release gate until browser automation is added.",
        ],
    }
    try:
        report["git_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nCertification status: {report['status'].upper()}")
    print(f"Report: {args.report}")
    if skipped:
        for item in skipped:
            print(f"SKIPPED: {item['name']} — {item['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
