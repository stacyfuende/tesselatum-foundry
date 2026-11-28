from copy import deepcopy
import json
from pathlib import Path

import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.customer_requests import (
    CustomerProductRequestError,
    prepare_customer_product_request,
)

ROOT = Path(__file__).resolve().parents[2]


def load_blueprint():
    return json.loads(
        (ROOT / "examples/product_blueprints/nairobi-site-coordinate-standardization.json")
        .read_text(encoding="utf-8")
    )


def request():
    return {
        "request_id": "customer-site-001",
        "job_type": "standardize_site_coordinates",
        "product_name": "Nairobi acquisition sites",
        "source_file": {
            "file_name": "sites.geojson",
            "media_type": "application/geo+json",
            "coordinate_reference_system": {"authority": "EPSG", "code": 4326},
        },
        "audience": "Property investment team",
        "decision_context": "Prepare acquisition candidates for metric distance analysis.",
        "geographic_scope": "Nairobi metropolitan region",
    }


def test_customer_request_resolves_to_approved_plan_without_exposing_execution_design():
    blueprint = load_blueprint()
    original = deepcopy(blueprint)
    result = prepare_customer_product_request(
        request(), blueprint=blueprint, capabilities=CapabilityRegistry()
    )

    assert result["status"] == "awaiting_source_ingestion"
    assert result["customer_summary"]["product_name"] == "Nairobi acquisition sites"
    assert result["customer_summary"]["audience"] == "Property investment team"
    assert result["customer_summary"]["output_coordinate_reference_system"] == "EPSG:32737"
    assert result["source_requirement"]["coordinate_order"] == "longitude, latitude"
    assert result["execution_plan"]["status"] == "planned"
    assert result["execution_plan"]["node_order"] == ["standardize"]
    assert blueprint == original


def test_customer_request_rejects_unregistered_job_type():
    item = request()
    item["job_type"] = "invent_a_spatial_method"
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, blueprint=load_blueprint(), capabilities=CapabilityRegistry()
        )


def test_customer_request_rejects_template_mismatch():
    item = load_blueprint()
    item["blueprint_id"] = "some-other-product"
    with pytest.raises(CustomerProductRequestError, match="approved product template"):
        prepare_customer_product_request(
            request(), blueprint=item, capabilities=CapabilityRegistry()
        )


def test_customer_request_rejects_wrong_source_crs():
    item = request()
    item["source_file"]["coordinate_reference_system"]["code"] = 3857
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, blueprint=load_blueprint(), capabilities=CapabilityRegistry()
        )


def test_customer_request_requires_customer_context():
    item = request()
    del item["decision_context"]
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, blueprint=load_blueprint(), capabilities=CapabilityRegistry()
        )
