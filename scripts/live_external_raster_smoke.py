"""Live smoke test: discover and execute a real external Nairobi Sentinel-2 COG.

This intentionally exercises the public STAC catalogue, source allowlist, HEAD
validator discovery, ETag-pinned HTTP range reads, TIFF parsing, raster.window
Run orchestration, independent output validation and Artifact publication.
No source raster is downloaded or stored in Foundry.
"""

from __future__ import annotations

import json
import tempfile
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path

from pyproj import CRS
from urllib.parse import urlsplit

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.external_raster_orchestration import (
    ExternalRasterWindowRunOrchestrator,
)
from tessellatum_foundry.execution.external_raster_runs import (
    ExternalRasterWindowRunFactory,
)
from tessellatum_foundry.execution.runs import RunRepository
from tessellatum_foundry.sources.http import HttpSourceAdapter
from tessellatum_foundry.sources.models import SourceIntegrityError
from tessellatum_foundry.sources.raster import BudgetedRasterRangeReader
from tessellatum_foundry.sources.stac import resolve_stac_asset
from tessellatum_foundry.sources.tiff import TiffRangeReader
from tessellatum_foundry.storage.artifacts import FileSystemArtifactStore
from tessellatum_foundry.storage.raster_window import decode_raster_window_artifact


CATALOG = "https://earth-search.aws.element84.com/v1"
ALLOWED_ASSET_HOSTS = {"sentinel-cogs.s3.us-west-2.amazonaws.com"}
MAX_ITEM_BYTES = 2 * 1024 * 1024


def fetch_stac_item() -> tuple[dict, str]:
    """Find a recent Sentinel-2 item intersecting Nairobi and return its red band."""
    query = urllib.parse.urlencode(
        {
            "collections": "sentinel-2-l2a",
            "bbox": "36.6,-1.5,37.1,-1.1",
            "datetime": "2024-01-01T00:00:00Z/2026-12-31T23:59:59Z",
            "limit": "20",
            "sortby": "-properties.datetime",
        }
    )
    request = urllib.request.Request(
        f"{CATALOG}/search?{query}",
        headers={
            "Accept": "application/geo+json",
            "User-Agent": "Tessellatum-Foundry-live-test/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(MAX_ITEM_BYTES + 1)
    if len(payload) > MAX_ITEM_BYTES:
        raise RuntimeError("STAC search response exceeded the 2 MiB test limit.")
    result = json.loads(payload)
    features = result.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("Earth Search returned no Sentinel-2 items for Nairobi.")
    for item in features:
        assets = item.get("assets", {})
        for asset_key in ("red", "B04"):
            asset = assets.get(asset_key)
            if not isinstance(asset, dict):
                continue
            href = asset.get("href")
            if not isinstance(href, str):
                continue
            host = (urlsplit(href).hostname or "").lower()
            if host in ALLOWED_ASSET_HOSTS:
                return item, asset_key
    raise RuntimeError(
        "No allowlisted Sentinel-2 red-band COG was returned for Nairobi."
    )


def discover_strong_etag(uri: str) -> str:
    request = urllib.request.Request(
        uri,
        method="HEAD",
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "Tessellatum-Foundry-live-test/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_host = (urlsplit(response.geturl()).hostname or "").lower()
        if final_host not in ALLOWED_ASSET_HOSTS:
            raise RuntimeError(
                "COG HEAD request redirected outside the exact asset allowlist."
            )
        etag = response.headers.get("ETag")
    if not etag or etag.startswith("W/"):
        raise SourceIntegrityError("Live COG did not provide a strong ETag.")
    return etag


def main() -> None:
    item, asset_key = fetch_stac_item()
    reference = resolve_stac_asset(
        item,
        asset_key,
        catalog_id="earth-search",
        allowed_hosts=ALLOWED_ASSET_HOSTS,
    )
    etag = discover_strong_etag(reference.uri)
    reference = replace(reference, etag=etag, media_type="image/tiff", selection={})
    adapter = HttpSourceAdapter(
        allowed_hosts=ALLOWED_ASSET_HOSTS,
        timeout_seconds=45,
    )
    descriptor = adapter.describe(reference)
    if descriptor.byte_size is None or descriptor.byte_size < 1024:
        raise RuntimeError("Live COG did not expose a trustworthy object size.")

    # Independently inspect the remote TIFF header before declaring the Geo-Cell.
    metadata_budget = BudgetedRasterRangeReader(
        adapter,
        reference,
        max_requests=64,
        max_total_bytes=8 * 1024 * 1024,
        max_range_bytes=2 * 1024 * 1024,
    )
    source_raster = TiffRangeReader(metadata_budget).read(
        file_size=descriptor.byte_size
    )
    metadata = source_raster.metadata
    if not metadata.crs:
        raise RuntimeError("Live Sentinel-2 COG has no supported embedded CRS.")
    crs_authority = CRS.from_user_input(metadata.crs).to_authority()
    if crs_authority is None:
        raise RuntimeError("Live Sentinel-2 COG CRS has no authority identifier.")
    crs_declaration = {
        "authority": crs_authority[0],
        "code": int(crs_authority[1]),
    }
    if metadata.width < 64 or metadata.height < 64 or metadata.band_count != 1:
        raise RuntimeError(
            "Live red-band COG does not meet the one-band 64x64 smoke-test contract."
        )

    cell = {
        "cell_id": "live-nairobi-sentinel2-red-window",
        "version": "1.0.0",
        "capability": {"capability_id": "raster.window", "version": "1.0.0"},
        "inputs": {
            "raster": {
                "source": "external",
                "reference": reference.to_dict(),
                "spatial": {
                    "kind": "raster",
                    "crs": crs_declaration,
                    "raster": {
                        "width": metadata.width,
                        "height": metadata.height,
                        "band_count": metadata.band_count,
                        "dtypes": list(metadata.dtypes),
                        "resolution": [
                            (
                                metadata.transform[1] ** 2
                                + metadata.transform[4] ** 2
                            ) ** 0.5,
                            (
                                metadata.transform[2] ** 2
                                + metadata.transform[5] ** 2
                            ) ** 0.5,
                        ],
                    },
                },
            }
        },
        "parameters": {
            "row_offset": 0,
            "column_offset": 0,
            "height": 64,
            "width": 64,
            "bands": [1],
        },
        "output_contracts": {
            "window": {
                "data_kind": "raster",
                "media_types": ["application/vnd.tessellatum.raster-window"],
                "crs": crs_declaration,
            }
        },
    }

    capabilities = CapabilityRegistry()
    capability = capabilities.get("raster.window", "1.0.0")
    with tempfile.TemporaryDirectory(prefix="foundry-live-raster-") as directory:
        root = Path(directory)
        runs = RunRepository(root / "control")
        store = FileSystemArtifactStore(root / "artifacts")
        queued = ExternalRasterWindowRunFactory(
            run_repository=runs,
            capabilities=capabilities,
        ).create_queued_run(cell=cell, capability=capability)
        orchestrator = ExternalRasterWindowRunOrchestrator(
            artifact_store=store,
            run_repository=runs,
            source_adapter_resolver=lambda _reference: adapter,
            source_authorizer=lambda _reference, _actor: None,
            capabilities=capabilities,
            max_requests=256,
            max_source_bytes=64 * 1024 * 1024,
            max_range_bytes=16 * 1024 * 1024,
        )
        result = orchestrator.execute(
            run_id=queued["run_id"],
            cell=cell,
            capability=capability,
            actor_id="live-test:github-actions",
            artifact_id="live.nairobi.sentinel2.red.window",
            artifact_version="1.0.0",
        )
        artifact = store.get_artifact("live.nairobi.sentinel2.red.window", "1.0.0")
        store.verify_artifact(artifact)
        decoded = decode_raster_window_artifact(store.read_bytes(artifact))
        report = runs.get_validation_report(
            artifact["metadata"]["validation_report_id"]
        )

        assert result["run"]["status"] == "succeeded"
        assert report["overall_status"] == "passed"
        assert decoded.header["window"]["width"] == 64
        assert decoded.header["window"]["height"] == 64
        assert decoded.header["provenance"]["source_etag"] == etag
        assert result["source_range_requests"] > 0
        assert 0 < result["source_bytes_requested"] < descriptor.byte_size

        print(json.dumps({
            "status": "passed",
            "catalog": CATALOG,
            "collection": item["collection"],
            "item_id": item["id"],
            "asset": asset_key,
            "source_host": urlsplit(reference.uri).hostname,
            "source_bytes_total": descriptor.byte_size,
            "source_bytes_read_by_foundry": result["source_bytes_requested"],
            "source_range_requests": result["source_range_requests"],
            "source_read_fraction": round(
                result["source_bytes_requested"] / descriptor.byte_size, 6
            ),
            "source_crs": metadata.crs,
            "source_grid": [metadata.width, metadata.height],
            "output_window": [64, 64],
            "artifact_checksum": artifact["checksum"]["value"],
            "validation": report["overall_status"],
            "run_status": result["run"]["status"],
        }, indent=2))


if __name__ == "__main__":
    main()
