"""Typed asynchronous client for the AC Brain REST API.

The caller injects and owns an aiohttp-compatible session.  This module never
creates or closes a session and has no dependency on Home Assistant.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any
from urllib.parse import quote, urlsplit

from .models import (
    AcState,
    CommandInfo,
    CommandResult,
    ModelValidationError,
    parse_command,
    parse_state,
)


class AcApiError(Exception):
    """Base class for failures callers may safely translate for their UI."""


class AcCannotConnectError(AcApiError):
    """The controller could not be reached before the request completed."""


class AcInvalidResponseError(AcApiError):
    """The controller returned a successful but invalid document."""


class AcHttpError(AcApiError):
    """An unexpected HTTP status was returned."""

    def __init__(self, status: int):
        self.status = status
        super().__init__(f"AC Brain returned HTTP {status}")


class AcConflictError(AcHttpError):
    """The supplied desired revision is stale."""


class AcValidationError(AcHttpError):
    """The controller rejected an invalid intent change."""


class AcCommandError(AcHttpError):
    """The controller could not apply or verify the physical command."""


class AcPersistenceError(AcHttpError):
    """The controller could not durably accept the intent change."""


class AcApiClient:
    """Small API v2 client with a read-only legacy compatibility path."""

    def __init__(
        self,
        session: Any,
        base_url: str,
        *,
        # Actor requests can queue behind the controller's bounded 14-second
        # Daikin read. Keep one finite total request budget with enough margin
        # to durably accept a write even though physical confirmation is never
        # awaited by this client.
        timeout_seconds: float = 30.0,
    ) -> None:
        if session is None:
            raise ValueError("session is required")
        if not isinstance(base_url, str):
            raise ValueError("base_url must be a string")
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) URL without query or fragment")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")

        self._session = session
        self._base_url = normalized_url
        self._timeout_seconds = float(timeout_seconds)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def async_get_state(self) -> AcState:
        """Read API v2 state, falling back to legacy state only on v2 404."""

        status, payload = await self._request_json(
            "GET", "/api/v2/state", success_statuses={200, 404}
        )
        if status == 404:
            _, payload = await self._request_json(
                "GET", "/state", success_statuses={200}
            )
        return self._parse_state(payload)

    async def async_patch_state(
        self,
        changes: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> CommandResult:
        """Apply one logical intent change using optimistic concurrency."""

        if not isinstance(changes, Mapping):
            raise TypeError("changes must be a mapping")
        if not changes:
            raise ValueError("changes must not be empty")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")

        # Copy the top-level mapping so a caller cannot add/remove fields while
        # the asynchronous request is in flight. Nested values are serialized by
        # the injected HTTP client and are never interpolated into a URL.
        document = dict(changes)
        status, payload = await self._request_json(
            "PATCH",
            "/api/v2/state",
            success_statuses={200, 202},
            json=document,
            headers={
                "If-Match": f'"desired-{expected_revision}"',
                "Prefer": "wait=0",
            },
        )

        response = self._as_mapping(payload)
        state_payload: Any = response.get("state", response)
        if isinstance(state_payload, Mapping) and "command" not in state_payload:
            wrapper_command = response.get("command")
            if wrapper_command is not None:
                state_payload = dict(state_payload)
                state_payload["command"] = wrapper_command

        state = self._parse_state(state_payload)
        return CommandResult(
            state=state,
            status_code=status,
            accepted_pending=status == 202,
        )

    async def async_get_command(self, command_id: str) -> CommandInfo:
        """Read the current status of one previously accepted command."""

        if not isinstance(command_id, str) or not command_id:
            raise ValueError("command_id must be a non-empty string")
        encoded_id = quote(command_id, safe="")
        _, payload = await self._request_json(
            "GET",
            f"/api/v2/commands/{encoded_id}",
            success_statuses={200},
        )
        try:
            return parse_command(self._as_mapping(payload))
        except ModelValidationError as err:
            raise AcInvalidResponseError("Invalid command-status document") from err

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        success_statuses: set[int],
        **kwargs: Any,
    ) -> tuple[int, Any]:
        request_kwargs = dict(kwargs)
        request_kwargs["timeout"] = self._timeout_seconds
        url = f"{self._base_url}{path}"

        try:
            async with self._session.request(
                method, url, **request_kwargs
            ) as response:
                status = response.status
                if status not in success_statuses:
                    self._raise_for_status(status)
                if status == 404:
                    return status, None
                try:
                    payload = await response.json()
                except Exception as err:
                    raise AcInvalidResponseError(
                        "AC Brain returned invalid JSON"
                    ) from err
                return status, payload
        except AcApiError:
            raise
        except Exception as err:
            raise AcCannotConnectError("Unable to connect to AC Brain") from err

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status in {409, 412}:
            raise AcConflictError(status)
        if status == 422:
            raise AcValidationError(status)
        if status == 502:
            raise AcCommandError(status)
        if status == 503:
            raise AcPersistenceError(status)
        raise AcHttpError(status)

    @staticmethod
    def _as_mapping(value: Any) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise AcInvalidResponseError("AC Brain response must be a JSON object")
        return value

    @staticmethod
    def _parse_state(value: Any) -> AcState:
        try:
            return parse_state(AcApiClient._as_mapping(value))
        except ModelValidationError as err:
            raise AcInvalidResponseError("Invalid AC Brain state document") from err


__all__ = [
    "AcApiClient",
    "AcApiError",
    "AcCannotConnectError",
    "AcCommandError",
    "AcConflictError",
    "AcHttpError",
    "AcInvalidResponseError",
    "AcPersistenceError",
    "AcValidationError",
]
