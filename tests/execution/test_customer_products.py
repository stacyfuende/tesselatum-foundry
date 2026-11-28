from tessellatum_foundry.execution.customer_products import run_customer_spatial_product


def test_customer_product_service_composes_registered_lifecycle(monkeypatch):
    events = []
    blueprint = {"blueprint_id": "approved-product", "outputs": []}
    plan = {"status": "planned", "blueprint": blueprint}
    prepared = {
        "status": "awaiting_source_ingestion",
        "execution_plan": plan,
        "customer_summary": {"product_name": "Approved product"},
    }
    ingestion = {
        "artifact": {
            "artifact_id": "source-1",
            "version": "1.0.0",
            "checksum": {"algorithm": "sha256", "value": "a" * 64},
        },
        "feature_count": 3,
        "source_bounds": [36.8, -1.3, 36.9, -1.2],
        "resolved_input_bindings": {"standardize.features": {"source": "artifact"}},
    }
    compiled = {"recipe": {"recipe_id": "recipe-1"}}
    execution = type(
        "Execution",
        (),
        {"status": "succeeded", "node_results": {"standardize": object()}, "error": None},
    )()

    def prepare(*args, **kwargs):
        events.append("prepare")
        return prepared

    def ingest(*args, **kwargs):
        events.append("ingest")
        return ingestion

    def compile_recipe(*args, **kwargs):
        events.append("compile")
        return compiled

    def execute(*args, **kwargs):
        events.append("execute")
        return execution

    def accept(*args, **kwargs):
        events.append("accept")
        return {"status": "accepted", "release_allowed": True}

    def assemble(*args, **kwargs):
        events.append("manifest")
        return {"status": "accepted", "manifest_fingerprint": "b" * 64}

    def export(*args, **kwargs):
        events.append("export")
        return b"verified-zip"

    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.prepare_customer_product_request",
        prepare,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.ingest_customer_geojson",
        ingest,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.compile_product_blueprint_recipe",
        compile_recipe,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.execute_product_blueprint_plan",
        execute,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.evaluate_product_acceptance",
        accept,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.assemble_product_manifest",
        assemble,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.build_geojson_product_bundle",
        export,
    )

    result = run_customer_spatial_product(
        {"request_id": "request-1"},
        b"source",
        artifact_store=object(),
        capabilities=object(),
        recipe_service=object(),
        cell_templates={"standardize": {}},
        output_bindings={},
        actor_id="customer-1",
    )

    assert events == [
        "prepare", "ingest", "compile", "execute", "accept", "manifest", "export"
    ]
    assert result["status"] == "delivered"
    assert result["source"]["feature_count"] == 3
    assert result["execution"]["status"] == "succeeded"
    assert result["delivery"]["content"] == b"verified-zip"
    assert result["delivery"]["media_type"] == "application/zip"


def test_customer_product_service_never_exports_unaccepted_products(monkeypatch):
    from tessellatum_foundry.execution.customer_products import run_customer_spatial_product

    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.prepare_customer_product_request",
        lambda *args, **kwargs: {
            "status": "awaiting_source_ingestion",
            "execution_plan": {"status": "planned", "blueprint": {}},
            "customer_summary": {},
        },
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.ingest_customer_geojson",
        lambda *args, **kwargs: {
            "artifact": {"artifact_id": "source", "version": "1.0.0", "checksum": {}},
            "feature_count": 1,
            "source_bounds": [0, 0, 0, 0],
            "resolved_input_bindings": {},
        },
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.compile_product_blueprint_recipe",
        lambda *args, **kwargs: {"recipe": {"recipe_id": "recipe"}},
    )
    execution = type(
        "Execution", (), {"status": "failed", "node_results": {}, "error": "worker failed"}
    )()
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.execute_product_blueprint_plan",
        lambda *args, **kwargs: execution,
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.evaluate_product_acceptance",
        lambda *args, **kwargs: {"status": "rejected", "release_allowed": False},
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.assemble_product_manifest",
        lambda *args, **kwargs: {"status": "rejected"},
    )
    monkeypatch.setattr(
        "tessellatum_foundry.execution.customer_products.build_geojson_product_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Must not export")),
    )

    result = run_customer_spatial_product(
        {"request_id": "request-2"},
        b"source",
        artifact_store=object(),
        capabilities=object(),
        recipe_service=object(),
        cell_templates={"standardize": {}},
        output_bindings={},
        actor_id="customer-2",
    )
    assert result["status"] == "rejected"
    assert result["delivery"]["content"] is None
