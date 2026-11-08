"""Isolated local Docker worker adapter for the vector.buffer capability."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .protocol import WorkerResult


_IMAGE_DIGEST = re.compile(r"^sha256:[a-fA-F0-9]{64}$")


class WorkerUnavailableError(RuntimeError):
    """Raised when the configured worker image or Docker daemon is unavailable."""


class WorkerExecutionError(RuntimeError):
    """Raised when the container exits without a valid output."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        super().__init__(message)


class WorkerTimeoutError(TimeoutError):
    """Raised when a container exceeds its execution deadline."""


class DockerWorker:
    """Run the Shapely implementation in a network-isolated Docker container."""

    capability_id = "vector.buffer"
    capability_version = "1.0.0"
    implementation_id = "vector-buffer-shapely"
    implementation_version = "1.0.0"
    worker_id = "local-docker-worker"
    worker_type = "local_docker"

    def __init__(
        self,
        image: str | None = None,
        *,
        timeout_seconds: int = 120,
        memory_mib: int = 512,
        cpu_count: float = 1.0,
        max_input_bytes: int = 128 * 1024 * 1024,
        max_output_bytes: int = 128 * 1024 * 1024,
        docker_executable: str = "docker",
    ) -> None:
        self.image = image or os.getenv(
            "FOUNDRY_VECTOR_BUFFER_IMAGE",
            "tessellatum-foundry/vector-buffer-shapely:ci",
        )
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive.")
        if memory_mib < 128:
            raise ValueError("memory_mib must be at least 128.")
        if cpu_count <= 0:
            raise ValueError("cpu_count must be positive.")
        if max_input_bytes < 1 or max_output_bytes < 1:
            raise ValueError("Input and output byte limits must be positive.")
        if not self.image or self.image.startswith("-"):
            raise ValueError("A valid pre-built worker image reference is required.")
        self.timeout_seconds = timeout_seconds
        self.memory_mib = memory_mib
        self.cpu_count = cpu_count
        self.max_input_bytes = max_input_bytes
        self.max_output_bytes = max_output_bytes
        self.docker_executable = docker_executable

    def image_digest(self) -> str:
        try:
            result = subprocess.run(
                [
                    self.docker_executable,
                    "image",
                    "inspect",
                    "--format={{.Id}}",
                    self.image,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise WorkerUnavailableError("Docker CLI is unavailable.") from error
        if result.returncode != 0:
            detail = result.stderr.strip()[-1000:]
            raise WorkerUnavailableError(
                f"Worker image {self.image!r} is not available locally: {detail}"
            )
        digest = result.stdout.strip()
        if not _IMAGE_DIGEST.fullmatch(digest):
            raise WorkerUnavailableError("Docker returned an invalid image ID digest.")
        return digest

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict[str, Any],
        measurement_crs: dict[str, Any],
        parameters: dict[str, Any],
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        if len(input_bytes) > self.max_input_bytes:
            raise WorkerExecutionError("Input Artifact exceeds the worker byte limit.")
        image_digest = runtime_image_digest or self.image_digest()
        if not isinstance(image_digest, str) or not _IMAGE_DIGEST.fullmatch(image_digest):
            raise WorkerUnavailableError("Worker image digest is invalid.")
        request = {
            "request_version": "0.1.0",
            "capability_id": "vector.buffer",
            "capability_version": capability_version,
            "input_crs": input_crs,
            "measurement_crs": measurement_crs,
            "parameters": parameters,
        }
        request_bytes = json.dumps(
            request, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")

        container_name = f"foundry-buffer-{uuid.uuid4().hex}"
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foundry-buffer-") as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            request_path = root / "request.json"
            output_dir = root / "output"
            output_path = output_dir / "result.json"
            input_path.write_bytes(input_bytes)
            request_path.write_bytes(request_bytes)
            input_path.chmod(0o444)
            request_path.chmod(0o444)
            output_dir.mkdir()
            output_dir.chmod(0o777)

            command = [
                self.docker_executable,
                "run",
                "--pull=never",
                "--rm",
                "--init",
                "--name",
                container_name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--pids-limit=128",
                f"--memory={self.memory_mib}m",
                f"--memory-swap={self.memory_mib}m",
                f"--cpus={self.cpu_count:g}",
                "--user=10001:10001",
                "--ulimit=core=0",
                f"--env=FOUNDRY_MAX_OUTPUT_BYTES={self.max_output_bytes}",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                "--mount",
                f"type=bind,src={input_path},dst=/run/input/feature-collection.json,readonly",
                "--mount",
                f"type=bind,src={request_path},dst=/run/request.json,readonly",
                "--mount",
                f"type=bind,src={output_dir},dst=/run/output",
                image_digest,
                "--request",
                "/run/request.json",
                "--input",
                "/run/input/feature-collection.json",
                "--output",
                "/run/output/result.json",
            ]
            try:
                process = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as error:
                raise WorkerTimeoutError(
                    f"Worker exceeded its {self.timeout_seconds}-second timeout."
                ) from error
            except OSError as error:
                raise WorkerUnavailableError("Docker CLI is unavailable.") from error
            finally:
                self._remove_container(container_name)

            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            if process.returncode != 0:
                detail = process.stderr.strip()[-2000:] or process.stdout.strip()[-2000:]
                raise WorkerExecutionError(
                    f"Worker exited with code {process.returncode}: {detail}",
                    exit_code=process.returncode,
                )
            if output_path.is_symlink() or not output_path.is_file():
                raise WorkerExecutionError(
                    "Worker exited without a regular output file."
                )
            if output_path.stat().st_size > self.max_output_bytes:
                raise WorkerExecutionError("Worker output exceeds the configured byte limit.")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WorkerExecutionError(
                    f"Worker produced unreadable JSON output: {error}"
                ) from error

        if not isinstance(payload, dict):
            raise WorkerExecutionError("Worker result must be a JSON object.")
        feature_collection = payload.get("feature_collection")
        output_crs = payload.get("crs")
        if (
            not isinstance(feature_collection, dict)
            or not isinstance(output_crs, dict)
        ):
            raise WorkerExecutionError("Worker result does not match the transport contract.")
        if not _IMAGE_DIGEST.fullmatch(image_digest):
            raise WorkerUnavailableError("Worker image digest changed during execution.")
        return WorkerResult(
            feature_collection=feature_collection,
            crs=output_crs,
            duration_ms=duration_ms,
            runtime_image_digest=image_digest,
        )

    def _remove_container(self, container_name: str) -> None:
        try:
            subprocess.run(
                [self.docker_executable, "rm", "--force", container_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return
