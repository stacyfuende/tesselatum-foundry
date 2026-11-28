import pytest

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.customer_requests import (
    CustomerProductRequestError,
    prepare_customer_product_request,
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


def test_customer_request_resolves_to_approved_plan_and_customer_summary():
    result = prepare_customer_product_request(
        request(), capabilities=CapabilityRegistry()
    )

    assert result["status"] == "awaiting_source_ingestion"
    assert result["customer_summary"]["product_name"] == "Nairobi acquisition sites"
    assert result["customer_summary"]["audience"] == "Property investment team"
    assert result["customer_summary"]["output_coordinate_reference_system"] == "EPSG:32737"
    assert result["source_requirement"]["coordinate_order"] == "longitude, latitude"
    assert result["execution_plan"]["status"] == "planned"
    assert result["execution_plan"]["node_order"] == ["standardize"]
    assert (
        result["execution_plan"]["blueprint"]["blueprint_id"]
        == "nairobi-site-coordinate-standardization"
    )


def test_customer_request_rejects_unregistered_job_type():
    item = request()
    item["job_type"] = "invent_a_spatial_method"
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )


def test_customer_request_rejects_wrong_source_crs():
    item = request()
    item["source_file"]["coordinate_reference_system"]["code"] = 3857
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )


def test_customer_request_requires_customer_context():
    item = request()
    del item["decision_context"]
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )

def test_customer_request_rejects_geography_outside_supported_utm_area():
    item = request()
    item["geographic_scope"] = "Mombasa"
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )


def test_customer_request_rejects_file_media_type_mismatch():
    item = request()
    item["source_file"]["media_type"] = "application/json"
    with pytest.raises(CustomerProductRequestError, match="extension and declared media type"):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )


def test_customer_request_rejects_path_like_file_names():
    item = request()
    item["source_file"]["file_name"] = "../sites.geojson"
    with pytest.raises(Exception):
        prepare_customer_product_request(
            item, capabilities=CapabilityRegistry()
        )
