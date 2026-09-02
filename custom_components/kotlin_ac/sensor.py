"""Diagnostic sensors for AC Brain."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .models import AcState, SensorStatus


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up stable diagnostic counters and timestamps."""

    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            KotlinDiagnosticSensor(
                coordinator,
                "stale_zone_count",
                "Stale Zone Count",
                lambda state: _sensor_count(state, SensorStatus.STALE),
            ),
            KotlinDiagnosticSensor(
                coordinator,
                "invalid_zone_count",
                "Invalid Zone Count",
                lambda state: _sensor_count(state, SensorStatus.INVALID),
            ),
            KotlinDiagnosticSensor(
                coordinator,
                "confirmed_compressor_starts",
                "Confirmed Compressor Starts",
                lambda state: state.observability.confirmed_compressor_starts,
            ),
            KotlinDiagnosticSensor(
                coordinator,
                "confirmed_direction_changes",
                "Confirmed Direction Changes",
                lambda state: state.observability.confirmed_direction_changes,
            ),
            KotlinDiagnosticSensor(
                coordinator,
                "last_device_contact",
                "Last Device Contact",
                lambda state: state.device.last_seen,
            ),
        ]
    )


class KotlinDiagnosticSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        key: str,
        name: str,
        value: Callable[[AcState], Any],
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"kotlin_ac_{key}"
        self._attr_name = name
        self._value = value

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self):
        state = self.coordinator.data
        return self._value(state) if state is not None else None


def _sensor_count(state: AcState, status: SensorStatus) -> int:
    return sum(zone.sensor_status is status for zone in state.zones.values())
