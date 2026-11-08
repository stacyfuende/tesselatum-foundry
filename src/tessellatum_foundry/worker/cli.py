"""Container entrypoint for the isolated Shapely vector.buffer worker."""

from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from tessellatum_foundry.capabilities.vector_buffer import buffer_feature_collection


def _write_json_once_or_replace(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".result-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _file_size_limit_exceeded(signum: int, frame: Any) -> None:
    raise OSError("Worker output exceeded its configured file-size limit.")


def execute_request(request_path: Path, input_path: Path, output_path: Path) -> None:
    max_output_bytes = int(os.environ["FOUNDRY_MAX_OUTPUT_BYTES"])
    if max_output_bytes < 1:
        raise ValueError("FOUNDRY_MAX_OUTPUT_BYTES must be positive.")
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes)
    )
    signal.signal(signal.SIGXFSZ, _file_size_limit_exceeded)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("request_version") != "0.1.0":
        raise ValueError("Unsupported worker request version.")
    if request.get("capability_id") != "vector.buffer":
        raise ValueError("This worker only executes vector.buffer.")
    if request.get("capability_version") != "1.0.0":
        raise ValueError("This worker only executes vector.buffer@1.0.0.")
    feature_collection = json.loads(input_path.read_text(encoding="utf-8"))
    result = buffer_feature_collection(
        feature_collection,
        input_crs=request["input_crs"],
        measurement_crs=request["measurement_crs"],
        **request["parameters"],
    )
    geometry_types = sorted(
        {
            shape(feature["geometry"]).geom_type
            for feature in result.feature_collection["features"]
        }
    )
    payload = {
        "feature_collection": result.feature_collection,
        "crs": request["input_crs"],
        "geometry_types": geometry_types,
    }
    _write_json_once_or_replace(output_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Foundry vector.buffer worker.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        execute_request(arguments.request, arguments.input, arguments.output)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
