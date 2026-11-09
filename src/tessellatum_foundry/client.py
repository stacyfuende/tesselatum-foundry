"""Dependency-free Python client for the authenticated Foundry control-plane API."""

from __future__ import annotations

import base64
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any


class FoundryAPIError(RuntimeError):
    """The Foundry API returned a non-success HTTP response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Foundry API returned HTTP {status_code}: {detail}")


class FoundryTransportError(RuntimeError):
    """The client could not safely complete an API request."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        raise HTTPError(
            request.full_url,
            code,
            "API redirects are disabled.",
            headers,
            file_pointer,
        )


class FoundryClient:
    """Small synchronous client for a single-tenant Foundry API endpoint.

    The client never follows redirects and verifies downloaded Artifact bytes
    against the immutable SHA-256 declared by the API.
    """

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str,
        timeout_seconds: float = 30,
        max_request_bytes: int = 32 * 1024 * 1024,
        max_response_bytes: int = 32 * 1024 * 1024,
        allow_insecure_localhost: bool = False,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "API URL must be an absolute HTTP(S) URL without credentials, "
                "query, or fragment."
            )
        if parsed.scheme != "https" and not (
            allow_insecure_localhost
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError(
                "Foundry API connections require HTTPS; HTTP is allowed only "
                "for explicit localhost tests."
            )
        if not isinstance(bearer_token, str) or len(bearer_token) < 32:
            raise ValueError("A Foundry API bearer token of at least 32 characters is required.")
        if timeout_seconds <= 0 or max_request_bytes < 1 or max_response_bytes < 1:
            raise ValueError("Timeout and request/response limits must be positive.")
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self._opener = build_opener(_RejectRedirects())

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        raw: bool = False,
    ) -> Any:
        body = None
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "*/*" if raw else "application/json",
        }
        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(body) > self.max_request_bytes:
                raise FoundryTransportError("API request exceeds the configured byte limit.")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                response_body = response.read(self.max_response_bytes + 1)
                if len(response_body) > self.max_response_bytes:
                    raise FoundryTransportError(
                        "API response exceeds the configured byte limit."
                    )
                response_headers = response.headers
        except HTTPError as error:
            try:
                error_body = error.read(min(self.max_response_bytes, 64 * 1024))
                parsed_error = json.loads(error_body.decode("utf-8"))
                detail = (
                    parsed_error.get("detail", parsed_error)
                    if isinstance(parsed_error, dict)
                    else parsed_error
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                detail = "request_failed"
            if error.code in {301, 302, 303, 307, 308}:
                raise FoundryTransportError("API redirects are not permitted.") from error
            raise FoundryAPIError(error.code, detail) from error
        except TimeoutError as error:
            raise FoundryTransportError("Foundry API request timed out.") from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise FoundryTransportError("Foundry API request timed out.") from error
            raise FoundryTransportError("Foundry API could not be reached.") from error
        except OSError as error:
            raise FoundryTransportError("Foundry API transport failed.") from error

        if raw:
            return response_body, response_headers
        try:
            result = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FoundryTransportError("Foundry API returned invalid JSON.") from error
        return result

    @staticmethod
    def _segment(value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Resource identifiers and versions must be non-empty strings.")
        return quote(value, safe="")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_capabilities(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/capabilities")

    def list_implementations(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/implementations")

    def put_artifact(
        self,
        *,
        artifact_id: str,
        version: str,
        content: bytes,
        created_by: str,
        media_type: str,
        format_name: str,
        spatial: dict[str, Any] | None = None,
        rights: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, bytes) or not content:
            raise ValueError("Artifact content must be non-empty bytes.")
        payload: dict[str, Any] = {
            "artifact_id": artifact_id,
            "version": version,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "created_by": created_by,
            "media_type": media_type,
            "format": format_name,
        }
        for key, value in (
            ("spatial", spatial),
            ("rights", rights),
            ("metadata", metadata),
        ):
            if value is not None:
                payload[key] = value
        return self._request("POST", "/v1/artifacts", payload)

    def get_artifact(self, artifact_id: str, version: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/artifacts/{self._segment(artifact_id)}/{self._segment(version)}",
        )

    def read_artifact(self, artifact_id: str, version: str) -> bytes:
        metadata = self.get_artifact(artifact_id, version)
        body, headers = self._request(
            "GET",
            (
                f"/v1/artifacts/{self._segment(artifact_id)}/"
                f"{self._segment(version)}/content"
            ),
            raw=True,
        )
        actual = hashlib.sha256(body).hexdigest()
        expected = metadata["checksum"]["value"]
        header_digest = headers.get("X-Content-SHA256")
        if actual != expected or header_digest != expected:
            raise FoundryTransportError(
                "Downloaded Artifact failed SHA-256 verification."
            )
        if len(body) != metadata.get("size_bytes"):
            raise FoundryTransportError(
                "Downloaded Artifact length differs from immutable metadata."
            )
        return body

    def register_cell(
        self, definition: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/cells",
            {"created_by": created_by, "definition": definition},
        )

    def list_cells(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/cells?{urlencode({'limit': limit})}")

    def get_cell(self, cell_id: str, version: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/cells/{self._segment(cell_id)}/{self._segment(version)}",
        )

    def register_recipe(
        self, definition: dict[str, Any], *, created_by: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/recipes",
            {"created_by": created_by, "definition": definition},
        )

    def list_recipes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/recipes?{urlencode({'limit': limit})}")

    def get_recipe(self, recipe_id: str, version: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/recipes/{self._segment(recipe_id)}/{self._segment(version)}",
        )

    def execute_recipe(
        self,
        recipe_id: str,
        version: str,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            (
                f"/v1/recipes/{self._segment(recipe_id)}/"
                f"{self._segment(version)}/runs"
            ),
            {"actor_id": actor_id},
        )

    def list_runs(
        self,
        *,
        recipe_execution_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"limit": limit}
        if recipe_execution_id is not None:
            query["recipe_execution_id"] = recipe_execution_id
        return self._request("GET", f"/v1/runs?{urlencode(query)}")

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/runs/{self._segment(run_id)}")

    def get_report(self, report_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/reports/{self._segment(report_id)}")
