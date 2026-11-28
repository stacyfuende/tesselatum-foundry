"""Bounded, validated GeoJSON ingestion for customer product requests."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.customer_requests import (
    prepare_customer_product_request,
)
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore

VECTOR_MEDIA_TYPE = "application/vnd.tessellatum.spatial-feature-collection+json"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_FEATURES = 100_000
_NAIROBI_ENVELOPE = (36.0, -2.5, 37.5, 0.5)


class CustomerSourceIngestionError(ValueError):
    """Raised when customer source bytes fail the product intake contract."""


def _reject_constant(value: str) -> None:
    raise CustomerSourceIngestionError(
        f"GeoJSON contains non-standard numeric constant: {value}."
    )


def ingest_customer_geojson(
    request: dict[str, Any],
    content: bytes,
    *,
    artifact_store: FileSystemArtifactStore,
    capabilities: CapabilityRegistry,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_features: int = DEFAULT_MAX_FEATURES,
) -> dict[str, Any]:
    """Validate source bytes and register them as an immutable input Artifact."""
    if not isinstance(content, bytes):
        raise TypeError("Customer source content must be bytes.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer.")
    if (
        isinstance(max_features, bool)
        or not isinstance(max_features, int)
        or max_features < 1
    ):
        raise ValueError("max_features must be a positive integer.")
    if len(content) > max_bytes:
        raise CustomerSourceIngestionError(
            f"Source file exceeds the configured {max_bytes}-byte intake limit."
        )

    try:
        prepared = prepare_customer_product_request(
            request, capabilities=capabilities
        )
    except (ValueError, KeyError, TypeError) as error:
        raise CustomerSourceIngestionError(str(error)) from error
    if prepared["status"] != "awaiting_source_ingestion":
        raise CustomerSourceIngestionError(
            "The product request is not eligible for source ingestion."
        )

    try:
        payload = json.loads(
            content.decode("utf-8"),
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CustomerSourceIngestionError(
            "Source file must be valid UTF-8 GeoJSON."
        ) from error

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise CustomerSourceIngestionError(
            "Source must be a GeoJSON FeatureCollection."
        )
    if "crs" in payload:
        raise CustomerSourceIngestionError(
            "Legacy embedded CRS is not accepted; declare EPSG:4326 in the request."
        )
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise CustomerSourceIngestionError(
            "Source FeatureCollection must contain at least one site."
        )
    if len(features) > max_features:
        raise CustomerSourceIngestionError(
            f"Source exceeds the configured {max_features}-feature intake limit."
        )

    west, south, east, north = _NAIROBI_ENVELOPE
    observed_west = observed_south = math.inf
    observed_east = observed_north = -math.inf
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} is not a GeoJSON Feature."
            )
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} is not a Point; "
                "this product accepts one point per site."
            )
        coordinates = geometry.get("coordinates")
        valid_coordinates = (
            isinstance(coordinates, list)
            and len(coordinates) in (2, 3)
            and all(
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
                for value in coordinates
            )
        )
        if not valid_coordinates:
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} has invalid 2D or 3D point coordinates."
            )
        longitude, latitude = coordinates[:2]
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} is outside WGS 84 coordinate bounds."
            )
        if not (west <= longitude <= east and south <= latitude <= north):
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} falls outside the supported "
                "Nairobi intake envelope."
            )
        properties = feature.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise CustomerSourceIngestionError(
                f"Feature {index + 1} properties must be an object or null."
            )
        observed_west = min(observed_west, longitude)
        observed_south = min(observed_south, latitude)
        observed_east = max(observed_east, longitude)
        observed_north = max(observed_north, latitude)

    request_id = request["request_id"]
    identity = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
    artifact = artifact_store.put_bytes(
        artifact_id=f"artifact:customer-source:{identity}",
        version="1.0.0",
        content=content,
        created_by=f"customer-request:{request_id}",
        media_type=VECTOR_MEDIA_TYPE,
        format_name="geojson",
        spatial={
            "kind": "vector",
            "crs": {"authority": "EPSG", "code": 4326},
            "bbox": [
                observed_west,
                observed_south,
                observed_east,
                observed_north,
            ],
            "geometry_types": ["Point"],
        },
        metadata={
            "customer_request_id": request_id,
            "source_file_name": request["source_file"]["file_name"],
            "ingestion_validation": "customer-site-points-v1",
            "feature_count": len(features),
            "coordinate_order": "longitude, latitude",
        },
    )
    binding = {
        "source": "artifact",
        "artifact": {
            "artifact_id": artifact["artifact_id"],
            "version": artifact["version"],
        },
    }
    return {
        "request_id": request_id,
        "status": "source_ingested",
        "artifact": artifact,
        "feature_count": len(features),
        "source_bounds": [
            observed_west,
            observed_south,
            observed_east,
            observed_north,
        ],
        "resolved_input_bindings": {"standardize.features": binding},
        "next_action": (
            "Compile the approved product plan with this immutable Artifact binding, "
            "then execute through the guarded Recipe Run service."
        ),
    }
