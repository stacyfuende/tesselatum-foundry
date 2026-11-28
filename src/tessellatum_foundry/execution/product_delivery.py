"""Verified, portable export bundles for accepted spatial products."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_GEOJSON_TYPES = {"Feature", "FeatureCollection"}
_MAX_MANIFEST_BYTES = 5 * 1024 * 1024


class ProductExportError(ValueError):
    """Raised when a product cannot be safely exported."""


def build_geojson_product_bundle(
    manifest: dict[str, Any],
    *,
    artifact_store: Any,
    max_output_bytes: int = 100 * 1024 * 1024,
) -> bytes:
    """Build a deterministic ZIP for an accepted product containing GeoJSON outputs.

    Only immutable Artifact references in the supplied product manifest are read.
    The Artifact Store verifies content hashes before bytes are returned.
    """
    if manifest.get("status") != "accepted" or manifest.get("release_allowed") is not True:
        raise ProductExportError("Only accepted products eligible for release can be exported.")
    fingerprint = manifest.get("manifest_fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch(
        r"[a-f0-9]{64}", fingerprint
    ):
        raise ProductExportError("Product manifest fingerprint is missing or invalid.")
    canonical = dict(manifest)
    canonical.pop("manifest_fingerprint", None)
    canonical_bytes = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    expected = hashlib.sha256(canonical_bytes).hexdigest()
    if expected != fingerprint:
        raise ProductExportError("Product manifest fingerprint verification failed.")
    if (
        isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or max_output_bytes < 1
    ):
        raise ValueError("max_output_bytes must be a positive integer.")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ProductExportError("Product manifest contains no outputs.")
    payloads: list[tuple[str, bytes, dict[str, Any]]] = []
    total = 0
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict) or output.get("status") != "assembled":
            raise ProductExportError("Every product output must be assembled.")
        output_id = output.get("output_id")
        if (
            not isinstance(output_id, str)
            or not _IDENTIFIER.fullmatch(output_id)
            or output_id in seen
        ):
            raise ProductExportError("Output identifiers must be unique safe filenames.")
        seen.add(output_id)
        artifact_ref = output.get("artifact")
        if not isinstance(artifact_ref, dict):
            raise ProductExportError(f"Output {output_id!r} has no Artifact reference.")
        media_type = artifact_ref.get("media_type", "").split(";", 1)[0].strip().lower()
        if media_type not in {
            "application/geo+json",
            "application/json",
            "application/vnd.tessellatum.spatial-feature-collection+json",
        }:
            raise ProductExportError(f"Output {output_id!r} is not a supported GeoJSON media type.")
        artifact_id, version = artifact_ref.get("artifact_id"), artifact_ref.get("version")
        if not isinstance(artifact_id, str) or not isinstance(version, str):
            raise ProductExportError(f"Output {output_id!r} has an invalid Artifact identity.")
        try:
            artifact = artifact_store.get_artifact(artifact_id, version)
            if (
                artifact.get("checksum") != artifact_ref.get("checksum")
                or artifact.get("size_bytes") != artifact_ref.get("size_bytes")
                or artifact.get("media_type") != artifact_ref.get("media_type")
            ):
                raise ProductExportError(
                    f"Output {output_id!r} Artifact metadata differs from the manifest."
                )
            declared_size = artifact.get("size_bytes")
            if (
                isinstance(declared_size, bool)
                or not isinstance(declared_size, int)
                or declared_size < 0
            ):
                raise ProductExportError(f"Output {output_id!r} has an invalid Artifact size.")
            if total + declared_size > max_output_bytes:
                raise ProductExportError("Product exceeds the configured export byte limit.")
            content = artifact_store.read_bytes(artifact, max_bytes=max_output_bytes - total)
        except (OSError, KeyError, RuntimeError, ValueError) as error:
            if isinstance(error, ProductExportError):
                raise
            raise ProductExportError(
                f"Output {output_id!r} could not be verified in Artifact storage."
            ) from error
        total += len(content)
        if total > max_output_bytes:
            raise ProductExportError("Product exceeds the configured export byte limit.")
        try:
            document = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProductExportError(f"Output {output_id!r} is not valid UTF-8 JSON.") from error
        if (
            not isinstance(document, dict)
            or document.get("type") not in _GEOJSON_TYPES
        ):
            raise ProductExportError(
                f"Output {output_id!r} is not a GeoJSON Feature or FeatureCollection."
            )
        path = f"outputs/{output_id}.geojson"
        payloads.append((path, content, {
            "output_id": output_id,
            "artifact_id": artifact_id,
            "version": version,
            "path": path,
            "media_type": artifact_ref["media_type"],
            "size_bytes": len(content),
            "checksum": {
                "algorithm": "sha256",
                "value": hashlib.sha256(content).hexdigest(),
            },
        }))

    export_index = {
        "bundle_version": "1.0.0",
        "product_id": manifest.get("product_id"),
        "product_version": manifest.get("product_version"),
        "product_manifest_fingerprint": fingerprint,
        "outputs": [record for _, _, record in payloads],
    }
    entries = [
        (
            "product-manifest.json",
            json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode("utf-8"),
        ),
        ("manifest-fingerprint-input.json", canonical_bytes),
        (
            "export-index.json",
            json.dumps(export_index, sort_keys=True, indent=2, allow_nan=False).encode("utf-8"),
        ),
        *[(path, content) for path, content, _ in payloads],
    ]
    if len(entries[0][1]) > _MAX_MANIFEST_BYTES:
        raise ProductExportError("Product manifest exceeds the export metadata limit.")

    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path, content in entries:
            info = zipfile.ZipInfo(
                path, date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue()
