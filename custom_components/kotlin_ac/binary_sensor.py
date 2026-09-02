"""Diagnostic binary sensors for AC Brain."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .models import CommandStatus


_PENDING_STATUSES = {
    CommandStatus.QUEUED,
    CommandStatus.PENDING,
    CommandStatus.APPLYING,
    CommandStatus.RETRYING,
}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up bounded controller-health indicators."""

    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            KotlinControllerReady(coordinator),
            KotlinDeviceOnline(coordinator),
            KotlinCommandPending(coordinator),
        ]
    )


class _KotlinDiagnosticBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class KotlinControllerReady(_KotlinDiagnosticBinarySensor):
    _attr_unique_id = "kotlin_ac_controller_ready"
    _attr_name = "Controller Ready"

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        return state is not None and state.controller_ready


class KotlinDeviceOnline(_KotlinDiagnosticBinarySensor):
    _attr_unique_id = "kotlin_ac_device_online"
    _attr_name = "Device Online"

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        return state is not None and state.device.available is True


class KotlinCommandPending(_KotlinDiagnosticBinarySensor):
    _attr_unique_id = "kotlin_ac_command_pending"
    _attr_name = "Command Pending"

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        return state is not None and state.command.status in _PENDING_STATUSES
