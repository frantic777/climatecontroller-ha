"""Typed Home Assistant coordinator for AC Brain."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AcApiClient,
    AcApiError,
    AcConflictError,
    AcPersistenceError,
    AcValidationError,
)
from .models import AcState, CommandResult


_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = timedelta(seconds=5)

PatchFactory = Callable[[AcState], Mapping[str, Any]]


def _v2_progress(state: AcState) -> tuple[int, int, int] | None:
    """Return the monotonic controller progress tuple for comparable v2 states."""

    if state.api_version != 2 or state.desired_revision is None:
        return None
    return (
        state.desired_revision,
        state.plan_revision if state.plan_revision is not None else -1,
        state.applied_plan_revision
        if state.applied_plan_revision is not None
        else -1,
    )


def _would_regress(candidate: AcState, current: AcState | None) -> bool:
    if current is None:
        return False
    candidate_progress = _v2_progress(candidate)
    current_progress = _v2_progress(current)
    return (
        candidate_progress is not None
        and current_progress is not None
        and candidate_progress < current_progress
    )


class AcDataUpdateCoordinator(DataUpdateCoordinator[AcState]):
    """Own polling and serialize revision-protected intent commands."""

    def __init__(self, hass: HomeAssistant, client: AcApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="kotlin_ac_coordinator",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        self._command_lock = asyncio.Lock()

    async def _async_update_data(self) -> AcState:
        try:
            state = await self.client.async_get_state()
        except AcApiError as err:
            raise UpdateFailed("Unable to update AC Brain state") from err

        # A GET already in flight when a PATCH is durably accepted can return
        # the previous projection after the accepted state has been published.
        # Desired revisions are monotonic, so never regress the HA UI to that
        # stale intent. Equal revisions are retained because plan/command state
        # can continue advancing in the background.
        current = self.data
        if current is not None and _would_regress(state, current):
            return current
        return state

    async def async_apply_patch(
        self, changes: Mapping[str, Any] | PatchFactory
    ) -> CommandResult:
        """Durably accept one revision and publish the server-returned intent."""

        try:
            # Serialize only revision selection and durable PATCH acceptance.
            # Physical application continues independently in the controller;
            # ordinary coordinator refreshes publish its progress.
            async with self._command_lock:
                current = self.data
                if current is None:
                    raise HomeAssistantError("AC Brain state is not available")
                if current.api_version != 2 or current.desired_revision is None:
                    raise HomeAssistantError(
                        "This AC Brain version does not support atomic commands"
                    )

                resolved = changes(current) if callable(changes) else changes
                if not isinstance(resolved, Mapping) or not resolved:
                    raise HomeAssistantError("AC Brain command contains no changes")

                result = await self.client.async_patch_state(
                    resolved,
                    expected_revision=current.desired_revision,
                )
                # A poll or wall-controller adoption can advance the actor while
                # this PATCH response is in flight. Never let its older response
                # regress desired, plan, or applied progress already published.
                if not _would_regress(result.state, self.data):
                    self.async_set_updated_data(result.state)
                return result
        except AcConflictError as err:
            # Release the command lock before a potentially slow refresh. Never
            # retry blindly: doing so could overwrite a newer user command.
            try:
                await self.async_request_refresh()
            except Exception:
                _LOGGER.debug(
                    "Unable to refresh AC Brain after revision conflict",
                    exc_info=True,
                )
            raise HomeAssistantError(
                "AC Brain changed concurrently; try the command again"
            ) from err
        except AcValidationError as err:
            raise HomeAssistantError("AC Brain rejected the command") from err
        except AcPersistenceError as err:
            raise HomeAssistantError("AC Brain could not save the command") from err
        except AcApiError as err:
            raise HomeAssistantError("AC Brain could not apply the command") from err


@dataclass(frozen=True, slots=True)
class AcRuntimeData:
    """Objects owned by one config entry."""

    client: AcApiClient
    coordinator: AcDataUpdateCoordinator


__all__ = ["AcDataUpdateCoordinator", "AcRuntimeData", "PatchFactory"]
