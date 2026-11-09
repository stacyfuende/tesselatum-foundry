"""Single-tenant authenticated HTTP control plane for Foundry."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from tessellatum_foundry.execution.remote_worker import (
    RemoteVectorBufferWorker,
    RemoteVectorReprojectWorker,
)
from tessellatum_foundry.local import LocalFoundry
from tessellatum_foundry.storage.artifacts import ImmutableArtifactError
from tessellatum_foundry.storage.definitions import ImmutableDefinitionError


def _build_foundry_from_environment() -> LocalFoundry:
    root = Path(os.environ.get("FOUNDRY_DATA_DIR", "./foundry-data"))
    mode = os.environ.get("FOUNDRY_WORKER_MODE", "docker")
    if mode == "docker":
        return LocalFoundry(root)
    if mode != "remote":
        raise RuntimeError("FOUNDRY_WORKER_MODE must be 'docker' or 'remote'.")

    buffer_url = os.environ.get("FOUNDRY_VECTOR_BUFFER_URL", "")
    buffer_token = os.environ.get("FOUNDRY_VECTOR_BUFFER_TOKEN", "")
    reproject_url = os.environ.get("FOUNDRY_VECTOR_REPROJECT_URL", "")
    reproject_token = os.environ.get("FOUNDRY_VECTOR_REPROJECT_TOKEN", "")
    if not all((buffer_url, buffer_token, reproject_url, reproject_token)):
        raise RuntimeError(
            "Remote mode requires URLs and bearer tokens for both vector workers."
        )
    return LocalFoundry(
        root,
        worker=RemoteVectorBufferWorker(
            buffer_url,
            bearer_token=buffer_token,
        ),
        reproject_worker=RemoteVectorReprojectWorker(
            reproject_url,
            bearer_token=reproject_token,
        ),
    )


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object.")
    return value


def _public_artifact(record: dict[str, Any]) -> dict[str, Any]:
    """Hide host filesystem paths behind an opaque API storage identifier."""
    public = dict(record)
    storage = dict(record["storage"])
    storage["uri"] = f"foundry://sha256/{record['checksum']['value']}"
    storage["provider"] = "foundry-api"
    storage.pop("object_key", None)
    public["storage"] = storage
    return public


def create_app(
    foundry: LocalFoundry | None = None,
    *,
    api_token: str | None = None,
    max_request_bytes: int | None = None,
) -> FastAPI:
    """Create a private, single-tenant API app with an injected or env-built Foundry."""
    token = api_token if api_token is not None else os.environ.get("FOUNDRY_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32:
        raise RuntimeError("FOUNDRY_API_TOKEN must contain at least 32 characters.")
    maximum = (
        max_request_bytes
        if max_request_bytes is not None
        else int(os.environ.get("FOUNDRY_API_MAX_REQUEST_BYTES", str(32 * 1024 * 1024)))
    )
    if maximum < 1024:
        raise ValueError("API request limit must be at least 1024 bytes.")
    control_plane = foundry or _build_foundry_from_environment()

    def authorize(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {token}".encode("utf-8")
        supplied = authorization.encode("utf-8") if isinstance(authorization, str) else b""
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    async def read_json_object(request: Request) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != (
            "application/json"
        ):
            raise HTTPException(
                status_code=415, detail="content_type_must_be_application_json"
            )
        raw_length = request.headers.get("content-length")
        if raw_length is None:
            raise HTTPException(status_code=411, detail="content_length_required")
        try:
            content_length = int(raw_length)
        except ValueError as error:
            raise HTTPException(
                status_code=400, detail="invalid_content_length"
            ) from error
        if content_length < 1:
            raise HTTPException(status_code=400, detail="empty_request_body")
        if content_length > maximum:
            raise HTTPException(status_code=413, detail="request_size_limit_exceeded")
        body = await request.body()
        if len(body) != content_length:
            raise HTTPException(status_code=400, detail="content_length_mismatch")
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=400, detail="invalid_json") from error
        return _require_object(value, "request body")

    app = FastAPI(
        title="Tessellatum Foundry Control Plane",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)])
    def list_capabilities() -> list[dict[str, Any]]:
        return control_plane.capabilities.list()

    @app.get("/v1/implementations", dependencies=[Depends(authorize)])
    def list_implementations() -> list[dict[str, Any]]:
        return control_plane.implementations.list()

    @app.post("/v1/artifacts", dependencies=[Depends(authorize)])
    async def put_artifact(request: Request) -> dict[str, Any]:
        payload = await read_json_object(request)
        allowed = {
            "artifact_id",
            "version",
            "content_base64",
            "created_by",
            "media_type",
            "format",
            "spatial",
            "rights",
            "metadata",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown_artifact_fields: {', '.join(sorted(unknown))}",
            )
        required = {
            "artifact_id",
            "version",
            "content_base64",
            "created_by",
            "media_type",
            "format",
        }
        missing = required - set(payload)
        if missing:
            raise HTTPException(
                status_code=422,
                detail="missing_artifact_fields: " + ", ".join(sorted(missing)),
            )
        for field in ("artifact_id", "version", "created_by", "media_type", "format"):
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=422, detail=f"{field}_must_be_a_non_empty_string"
                )
        encoded = payload.get("content_base64")
        if not isinstance(encoded, str) or not encoded:
            raise HTTPException(status_code=422, detail="content_base64_is_required")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise HTTPException(status_code=422, detail="invalid_content_base64") from error
        if not content:
            raise HTTPException(status_code=422, detail="artifact_content_is_empty")
        if len(content) > maximum:
            raise HTTPException(status_code=413, detail="artifact_size_limit_exceeded")
        optional_objects = ("spatial", "rights", "metadata")
        for field in optional_objects:
            if field in payload and not isinstance(payload[field], dict):
                raise HTTPException(
                    status_code=422, detail=f"{field}_must_be_a_json_object"
                )
        try:
            record = await run_in_threadpool(
                control_plane.store_artifact,
                artifact_id=payload.get("artifact_id"),
                version=payload.get("version"),
                content=content,
                created_by=payload.get("created_by"),
                media_type=payload.get("media_type"),
                format_name=payload.get("format"),
                spatial=payload.get("spatial"),
                rights=payload.get("rights"),
                metadata=payload.get("metadata"),
            )
            return _public_artifact(record)
        except ImmutableArtifactError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/v1/artifacts/{artifact_id}/{version}",
        dependencies=[Depends(authorize)],
    )
    def get_artifact(artifact_id: str, version: str) -> dict[str, Any]:
        try:
            return _public_artifact(
                control_plane.get_artifact(artifact_id, version)
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="artifact_not_found") from error

    @app.get(
        "/v1/artifacts/{artifact_id}/{version}/content",
        dependencies=[Depends(authorize)],
    )
    def get_artifact_content(artifact_id: str, version: str) -> Response:
        try:
            artifact = control_plane.get_artifact(artifact_id, version)
            content = control_plane.read_artifact(artifact)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="artifact_not_found") from error
        checksum = artifact["checksum"]["value"]
        return Response(
            content=content,
            media_type=artifact["media_type"],
            headers={
                "ETag": f'"{checksum}"',
                "X-Content-SHA256": checksum,
                "Content-Length": str(len(content)),
            },
        )

    @app.get("/v1/cells", dependencies=[Depends(authorize)])
    def list_cells(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return control_plane.definitions.list_records("cell")[-limit:]

    @app.get("/v1/cells/{cell_id}/{version}", dependencies=[Depends(authorize)])
    def get_cell(cell_id: str, version: str) -> dict[str, Any]:
        try:
            return control_plane.definitions.get_cell(cell_id, version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="cell_not_found") from error

    @app.get("/v1/recipes", dependencies=[Depends(authorize)])
    def list_recipes(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return control_plane.definitions.list_records("recipe")[-limit:]

    @app.get("/v1/recipes/{recipe_id}/{version}", dependencies=[Depends(authorize)])
    def get_recipe(recipe_id: str, version: str) -> dict[str, Any]:
        try:
            return control_plane.definitions.get_recipe(recipe_id, version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="recipe_not_found") from error

    @app.post("/v1/cells", dependencies=[Depends(authorize)])
    async def register_cell(request: Request) -> dict[str, Any]:
        payload = await read_json_object(request)
        if set(payload) != {"created_by", "definition"}:
            raise HTTPException(
                status_code=422,
                detail="request_must_contain_only_created_by_and_definition",
            )
        definition = _require_object(payload["definition"], "definition")
        try:
            return await run_in_threadpool(
                control_plane.register_cell,
                definition,
                created_by=payload["created_by"],
            )
        except ImmutableDefinitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/recipes", dependencies=[Depends(authorize)])
    async def register_recipe(request: Request) -> dict[str, Any]:
        payload = await read_json_object(request)
        if set(payload) != {"created_by", "definition"}:
            raise HTTPException(
                status_code=422,
                detail="request_must_contain_only_created_by_and_definition",
            )
        definition = _require_object(payload["definition"], "definition")
        try:
            return await run_in_threadpool(
                control_plane.register_recipe,
                definition,
                created_by=payload["created_by"],
            )
        except ImmutableDefinitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/v1/recipes/{recipe_id}/{version}/runs",
        dependencies=[Depends(authorize)],
    )
    async def execute_recipe(
        recipe_id: str,
        version: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = await read_json_object(request)
        if set(payload) != {"actor_id"}:
            raise HTTPException(
                status_code=422, detail="request_must_contain_only_actor_id"
            )
        try:
            result = await run_in_threadpool(
                control_plane.execute_recipe,
                recipe_id=recipe_id,
                version=version,
                actor_id=payload["actor_id"],
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="recipe_or_dependency_not_found") from error
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "execution_id": result.execution_id,
            "recipe": result.recipe,
            "status": result.status,
            "failed_node_id": result.failed_node_id,
            "error": result.error,
            "runs": [
                {
                    "node_id": node_id,
                    "run_id": item.run.get("run_id"),
                    "status": item.run.get("status"),
                    "error": item.run.get("error"),
                }
                for node_id, item in result.node_results.items()
            ],
            "outputs": {
                name: _public_artifact(artifact)
                for name, artifact in result.outputs.items()
            },
        }

    @app.get("/v1/runs", dependencies=[Depends(authorize)])
    def list_runs(
        recipe_execution_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        records = control_plane.runs.list_runs()
        if recipe_execution_id is not None:
            records = [
                item
                for item in records
                if item.get("recipe_execution_id") == recipe_execution_id
            ]
        return records[-limit:]

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(authorize)])
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return control_plane.get_run(run_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="run_not_found") from error

    @app.get("/v1/reports/{report_id}", dependencies=[Depends(authorize)])
    def get_report(report_id: str) -> dict[str, Any]:
        try:
            return control_plane.get_validation_report(report_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="report_not_found") from error

    return app
