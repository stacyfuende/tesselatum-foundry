from __future__ import annotations

import hashlib
import json

import pytest

from tessellatum_foundry.execution.batches import ProcessedFeatureBatch
from tessellatum_foundry.sources.batches import FeatureBatch
from tessellatum_foundry.validation.streaming import (
    StreamingValidationError,
    VectorBufferStreamingValidator,
)


CRS = {"authority": "EPSG", "code": "3857"}
DIGEST = "sha256:" + "a" * 64


def feature_collection(start: int, count: int, *, output: bool = False) -> dict:
    features = []
    for index in range(start, start + count):
        geometry = (
            {
                "type": "Polygon",
                "coordinates": [[
                    [index, index],
                    [index + 1, index],
                    [index + 1, index + 1],
                    [index, index + 1],
                    [index, index],
                ]],
            }
            if output
            else {"type": "Point", "coordinates": [index, index]}
        )
        features.append({
            "type": "Feature",
            "id": index,
            "geometry": geometry,
            "properties": {"index": index},
        })
    return {"type": "FeatureCollection", "features": features}


def make_pair(sequence: int, offset: int, count: int = 2):
    source = json.dumps(
        feature_collection(offset, count), sort_keys=True, separators=(",", ":")
    ).encode()
    result = json.dumps(
        feature_collection(offset, count, output=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    input_batch = FeatureBatch(
        sequence=sequence,
        first_feature_offset=offset,
        feature_count=count,
        payload=source,
        checksum_sha256=hashlib.sha256(source).hexdigest(),
    )
    output_batch = ProcessedFeatureBatch(
        sequence=sequence,
        first_feature_offset=offset,
        feature_count=count,
        input_checksum_sha256=input_batch.checksum_sha256,
        payload=result,
        output_checksum_sha256=hashlib.sha256(result).hexdigest(),
        output_crs=CRS,
        duration_ms=15,
        runtime_image_digest=DIGEST,
    )
    return input_batch, output_batch


def validator():
    return VectorBufferStreamingValidator(
        input_crs=CRS,
        expected_output_crs=CRS,
        permitted_geometry_types={"Polygon", "MultiPolygon"},
    )


def test_streaming_validator_aggregates_batches_without_retaining_collections():
    critic = validator()
    critic.add(*make_pair(0, 0))
    critic.add(*make_pair(1, 2))

    report = critic.finish()

    assert report.passed
    assert report.batch_count == 2
    assert report.feature_count == 4
    assert report.duration_ms == 30
    assert report.geometry_types == ("Polygon",)
    assert report.as_validation_report("run:stream")["overall_status"] == "passed"


def test_streaming_validator_rejects_non_contiguous_batches():
    critic = validator()
    critic.add(*make_pair(0, 0))

    with pytest.raises(StreamingValidationError, match="not contiguous"):
        critic.add(*make_pair(2, 2))


def test_streaming_validator_rejects_output_with_wrong_source_checksum():
    critic = validator()
    input_batch, output_batch = make_pair(0, 0)
    mismatched = ProcessedFeatureBatch(
        sequence=output_batch.sequence,
        first_feature_offset=output_batch.first_feature_offset,
        feature_count=output_batch.feature_count,
        input_checksum_sha256="0" * 64,
        payload=output_batch.payload,
        output_checksum_sha256=output_batch.output_checksum_sha256,
        output_crs=output_batch.output_crs,
        duration_ms=output_batch.duration_ms,
        runtime_image_digest=output_batch.runtime_image_digest,
    )

    with pytest.raises(StreamingValidationError, match="exact input batch"):
        critic.add(input_batch, mismatched)


def test_streaming_validator_fails_when_worker_crs_differs():
    critic = validator()
    input_batch, output_batch = make_pair(0, 0)
    wrong_crs = ProcessedFeatureBatch(
        sequence=output_batch.sequence,
        first_feature_offset=output_batch.first_feature_offset,
        feature_count=output_batch.feature_count,
        input_checksum_sha256=output_batch.input_checksum_sha256,
        payload=output_batch.payload,
        output_checksum_sha256=output_batch.output_checksum_sha256,
        output_crs={"authority": "EPSG", "code": "4326"},
        duration_ms=output_batch.duration_ms,
        runtime_image_digest=output_batch.runtime_image_digest,
    )
    critic.add(input_batch, wrong_crs)

    assert not critic.finish().passed


def test_empty_stream_is_not_valid():
    report = validator().finish()

    assert not report.passed
    assert report.batch_count == 0
