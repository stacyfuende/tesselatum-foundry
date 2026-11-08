"""Authenticated HTTP adapter for a remote vector.buffer worker."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .docker_worker import (
    WorkerExecutionError,
    WorkerTimeoutError,
    WorkerUnavailableError,
)
from .protocol import WorkerResult

_IMAGE_DIGEST = re.compile(r"^sha256:[a-fA-F0-9]{64}$")
_ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, request, file_pointer, code, message, headers, new_url
    ):
        raise HTTPError(
            request.full_url,
            code,
            "Worker redirects are disabled.",
            headers,
            file_pointer,
        )


class RemoteVectorBufferWorker:
    """Call an authenticated HTTPS worker while preserving the vector.buffer contract."""

    capability_id = "vector.buffer"
    capability_version = "1.0.0"
    worker_type = "remote"

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str,
        timeout_seconds: int = 120,
        max_input_bytes: int = 128 * 1024 * 1024,
        max_output_bytes: int = 128 * 1024 * 1024,
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
                "Worker URL must be an absolute HTTP(S) URL without credentials, "
                "query, or fragment."
            )
        if parsed.scheme != "https" and not (
            allow_insecure_localhost and parsed.hostname in _ALLOWED_LOCAL_HOSTS
        ):
            raise ValueError(
                "Remote workers require HTTPS; HTTP is allowed only for explicit "
                "localhost tests."
            )
        if not isinstance(bearer_token, str) or not bearer_token.strip():
            raise ValueError("A non-empty worker bearer token is required.")
        if timeout_seconds < 1 or max_input_bytes < 1 or max_output_bytes < 1:
            raise ValueError("Timeout and payload limits must be positive.")
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.max_input_bytes = max_input_bytes
        self.max_output_bytes = max_output_bytes
        self._opener = build_opener(_RejectRedirects())
        self._identity: dict[str, str] | None = None

    def _request_json(self, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(
            payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        if body is not None and len(body) > self.max_input_bytes + 1024 * 1024:
            raise WorkerExecutionError(
                "Remote worker request exceeds the configured byte limit."
            )
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
            method="POST" if body is not None else "GET",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_output_bytes + 1)
                if len(raw) > self.max_output_bytes:
                    raise WorkerExecutionError(
                        "Remote worker response exceeds the configured byte limit."
                    )
                if response.status != 200:
                    raise WorkerUnavailableError(
                        f"Remote worker returned HTTP {response.status}."
                    )
        except HTTPError as error:
            if error.code in {301, 302, 303, 307, 308}:
                raise WorkerUnavailableError(
                    "Remote worker redirects are not permitted."
                ) from error
            if error.code in {408, 425, 429, 500, 502, 503, 504}:
                raise WorkerUnavailableError(
                    f"Remote worker temporarily unavailable (HTTP {error.code})."
                ) from error
            raise WorkerExecutionError(
                f"Remote worker rejected the request (HTTP {error.code})."
            ) from error
        except TimeoutError as error:
            raise WorkerTimeoutError(
                f"Remote worker exceeded its {self.timeout_seconds}-second timeout."
            ) from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise WorkerTimeoutError(
                    f"Remote worker exceeded its {self.timeout_seconds}-second timeout."
                ) from error
            raise WorkerUnavailableError("Remote worker could not be reached.") from error
        except OSError as error:
            raise WorkerUnavailableError("Remote worker transport failed.") from error
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkerExecutionError("Remote worker returned invalid JSON.") from error
        if not isinstance(result, dict):
            raise WorkerExecutionError("Remote worker response must be a JSON object.")
        return result

    def _get_identity(self) -> dict[str, str]:
        if self._identity is None:
            identity = self._request_json("/v1/identity")
            required = (
                "worker_id",
                "implementation_id",
                "implementation_version",
                "runtime_image_digest",
            )
            if any(
                not isinstance(identity.get(key), str) or not identity[key]
                for key in required
            ):
                raise WorkerUnavailableError("Remote worker identity is incomplete.")
            if not _IMAGE_DIGEST.fullmatch(identity["runtime_image_digest"]):
                raise WorkerUnavailableError(
                    "Remote worker reported an invalid runtime image digest."
                )
            if (
                identity.get("capability_id") != self.capability_id
                or identity.get("capability_version") != self.capability_version
            ):
                raise WorkerUnavailableError(
                    "Remote worker does not support {self.capability_id}@{self.capability_version}."
                )
            self._identity = {key: identity[key] for key in required}
        return self._identity

    @property
    def worker_id(self) -> str:
        return self._get_identity()["worker_id"]

    @property
    def implementation_id(self) -> str:
        return self._get_identity()["implementation_id"]

    @property
    def implementation_version(self) -> str:
        return self._get_identity()["implementation_version"]

    def image_digest(self) -> str:
        return self._get_identity()["runtime_image_digest"]

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict,
        measurement_crs: dict,
        parameters: dict,
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        if len(input_bytes) > self.max_input_bytes:
            raise WorkerExecutionError(
                "Input Artifact exceeds the remote worker byte limit."
            )
        if capability_version != self.capability_version:
            raise WorkerExecutionError(
                "Remote worker only executes vector.buffer@1.0.0."
            )
        identity = self._get_identity()
        pinned_digest = runtime_image_digest or identity["runtime_image_digest"]
        if pinned_digest != identity["runtime_image_digest"]:
            raise WorkerUnavailableError(
                "Remote worker runtime image changed after preflight."
            )
        try:
            feature_collection = json.loads(input_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkerExecutionError(
                "Input Artifact is not valid UTF-8 JSON."
            ) from error
        payload = self._request_json(
            "/v1/execute",
            {
                "request_version": "0.1.0",
                "capability_id": self.capability_id,
                "capability_version": capability_version,
                "input_feature_collection": feature_collection,
                "input_crs": input_crs,
                "measurement_crs": measurement_crs,
                "parameters": parameters,
            },
        )
        if payload.get("runtime_image_digest") != pinned_digest:
            raise WorkerUnavailableError(
                "Remote worker execution used an unexpected runtime image."
            )
        if (
            not isinstance(payload.get("feature_collection"), dict)
            or payload.get("crs") != input_crs
        ):
            raise WorkerExecutionError(
                "Remote worker result does not match the transport contract."
            )
        reported_duration = payload.get("duration_ms")
        if type(reported_duration) is not int or reported_duration < 0:
            raise WorkerExecutionError(
                "Remote worker returned an invalid execution duration."
            )
        return WorkerResult(
            feature_collection=payload["feature_collection"],
            crs=payload["crs"],
            duration_ms=reported_duration,
            runtime_image_digest=pinned_digest,
        )


class RemoteVectorReprojectWorker(RemoteVectorBufferWorker):
    """Call an authenticated HTTPS worker executing vector.reproject@1.0.0."""

    capability_id = "vector.reproject"
    capability_version = "1.0.0"

    def execute(
        self,
        *,
        input_bytes: bytes,
        capability_version: str,
        input_crs: dict,
        target_crs: dict,
        parameters: dict,
        runtime_image_digest: str | None = None,
    ) -> WorkerResult:
        if len(input_bytes) > self.max_input_bytes:
            raise WorkerExecutionError(
                "Input Artifact exceeds the remote worker byte limit."
            )
        if capability_version != self.capability_version:
            raise WorkerExecutionError(
                "Remote worker only executes vector.reproject@1.0.0."
            )
        identity = self._get_identity()
        pinned_digest = runtime_image_digest or identity["runtime_image_digest"]
        if pinned_digest != identity["runtime_image_digest"]:
            raise WorkerUnavailableError(
                "Remote worker runtime image changed after preflight."
            )
        try:
            feature_collection = json.loads(input_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkerExecutionError(
                "Input Artifact is not valid UTF-8 JSON."
            ) from error
        payload = self._request_json(
            "/v1/execute",
            {
                "request_version": "0.1.0",
                "capability_id": self.capability_id,
                "capability_version": capability_version,
                "input_feature_collection": feature_collection,
                "input_crs": input_crs,
                "target_crs": target_crs,
                "parameters": {
                    key: value for key, value in parameters.items() if key != "target_crs"
                },
            },
        )
        if payload.get("runtime_image_digest") != pinned_digest:
            raise WorkerUnavailableError(
                "Remote worker execution used an unexpected runtime image."
            )
        if (
            not isinstance(payload.get("feature_collection"), dict)
            or payload.get("crs") != target_crs
        ):
            raise WorkerExecutionError(
                "Remote worker result does not match the reprojection transport contract."
            )
        reported_duration = payload.get("duration_ms")
        if type(reported_duration) is not int or reported_duration < 0:
            raise WorkerExecutionError(
                "Remote worker returned an invalid execution duration."
            )
        return WorkerResult(
            feature_collection=payload["feature_collection"],
            crs=payload["crs"],
            duration_ms=reported_duration,
            runtime_image_digest=pinned_digest,
        )
