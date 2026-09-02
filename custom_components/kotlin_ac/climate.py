"""Climate entity for AC Brain."""

from __future__ import annotations

import math

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_HALVES, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .models import (
    AutoActuation,
    CommandStatus,
    ControlAction,
    ControlIssue,
    RequestedMode,
    SensorStatus,
)


HA_TO_REQUESTED_MODE = {
    HVACMode.COOL: "COOL",
    HVACMode.HEAT: "HEAT",
    HVACMode.AUTO: "AUTO",
    HVACMode.DRY: "DRY",
    HVACMode.FAN_ONLY: "FAN",
}
REQUESTED_TO_HA_MODE = {
    RequestedMode.COOL: HVACMode.COOL,
    RequestedMode.HEAT: HVACMode.HEAT,
    RequestedMode.AUTO: HVACMode.AUTO,
    RequestedMode.DRY: HVACMode.DRY,
    RequestedMode.FAN: HVACMode.FAN_ONLY,
}

HA_TO_DAIKIN_FAN = {
    FAN_LOW: "LOW",
    FAN_MEDIUM: "MED",
    FAN_HIGH: "HIGH",
    "Low Auto": "LOW_AUTO",
    "Med Auto": "MED_AUTO",
    "High Auto": "HIGH_AUTO",
    FAN_AUTO: "LOW_AUTO",
}
DAIKIN_TO_HA_FAN = {
    "LOW": FAN_LOW,
    "MED": FAN_MEDIUM,
    "HIGH": FAN_HIGH,
    "LOW_AUTO": "Low Auto",
    "MED_AUTO": "Med Auto",
    "HIGH_AUTO": "High Auto",
}

ACTION_TO_HA = {
    ControlAction.OFF: HVACAction.OFF,
    ControlAction.IDLE: HVACAction.IDLE,
    ControlAction.HEATING: HVACAction.HEATING,
    ControlAction.COOLING: HVACAction.COOLING,
    ControlAction.FAN: HVACAction.FAN,
    ControlAction.DRYING: HVACAction.DRYING,
    ControlAction.LOCKOUT: HVACAction.IDLE,
    ControlAction.DEGRADED: HVACAction.IDLE,
}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the AC Brain climate entity from config-entry runtime data."""

    async_add_entities([KotlinMainAC(entry.runtime_data.coordinator)])


class KotlinMainAC(CoordinatorEntity, ClimateEntity):
    """Requested comfort state backed by confirmed controller action."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "kotlin_climate_brain_main"
        self._attr_name = "Kotlin Climate Brain"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_precision = PRECISION_HALVES
        self._attr_min_temp = 16.0
        self._attr_max_temp = 32.0
        self._attr_target_temperature_step = 0.5
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.FAN_MODE
        )
        self._attr_fan_modes = list(HA_TO_DAIKIN_FAN)

    @property
    def hvac_modes(self):
        """Expose AUTO only when the controller can actually actuate AUTO safely."""

        state = self.coordinator.data
        modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ]
        if (
            state is not None
            and state.control.auto_actuation is AutoActuation.ENABLED
        ):
            modes.insert(3, HVACMode.AUTO)
        return modes

    @property
    def available(self) -> bool:
        state = self.coordinator.data
        return (
            super().available
            and state is not None
            and state.accepts_commands
        )

    @property
    def current_temperature(self) -> float | None:
        state = self.coordinator.data
        return state.current_temperature if state is not None else None

    @property
    def target_temperature(self) -> float | None:
        state = self.coordinator.data
        return state.intent.target_temperature if state is not None else None

    @property
    def hvac_mode(self):
        state = self.coordinator.data
        if state is None or not state.intent.enabled:
            return HVACMode.OFF
        return REQUESTED_TO_HA_MODE.get(state.intent.mode, HVACMode.AUTO)

    @property
    def hvac_action(self):
        state = self.coordinator.data
        if state is None or state.control.action is None:
            return None
        return ACTION_TO_HA.get(state.control.action)

    @property
    def fan_mode(self):
        state = self.coordinator.data
        if state is None:
            return FAN_LOW
        return DAIKIN_TO_HA_FAN.get(state.intent.fan_rate, FAN_LOW)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose sanitized control diagnostics without credentials or URLs."""

        state = self.coordinator.data
        if state is None:
            return {}
        sensor_statuses = [zone.sensor_status for zone in state.zones.values()]
        proposal = state.control.proposed_auto_plan
        return {
            "api_version": state.api_version,
            "desired_revision": state.desired_revision,
            "plan_revision": state.plan_revision,
            "applied_plan_revision": state.applied_plan_revision,
            "effective_mode": state.control.effective_mode,
            "control_reason": state.control.reason,
            "lockout_remaining_seconds": state.control.lockout_remaining_seconds,
            "command_status": state.command.status.value,
            "command_pending": state.command.status
            in {
                CommandStatus.QUEUED,
                CommandStatus.PENDING,
                CommandStatus.APPLYING,
                CommandStatus.RETRYING,
            },
            "device_last_seen": state.device.last_seen,
            "control_issues": [issue.value for issue in state.control.issues],
            "persistent_call": ControlIssue.PERSISTENT_CALL in state.control.issues,
            "stale_sensor_count": sensor_statuses.count(SensorStatus.STALE),
            "invalid_sensor_count": sensor_statuses.count(SensorStatus.INVALID),
            "missing_sensor_count": sensor_statuses.count(SensorStatus.MISSING),
            "compressor_running": state.observability.compressor_running,
            "confirmed_compressor_starts": (
                state.observability.confirmed_compressor_starts
            ),
            "confirmed_direction_changes": (
                state.observability.confirmed_direction_changes
            ),
            "last_compressor_started_at": (
                state.observability.last_compressor_started_at
            ),
            "sensorless_run_started_at": (
                state.observability.sensorless_run_started_at
            ),
            "last_compressor_stopped_at": (
                state.observability.last_compressor_stopped_at
            ),
            "last_direction_change_at": (
                state.observability.last_direction_change_at
            ),
            "direction_continuity_unknown_since": (
                state.observability.direction_continuity_unknown_since
            ),
            "pending_command_age_seconds": (
                state.observability.pending_command_age_seconds
            ),
            "controller_ready": state.controller_ready,
            "readiness_components": {
                name: status.value
                for name, status in state.readiness_components.items()
            },
            "current_temperature_contributors": list(
                state.current_temperature_contributors
            ),
            "auto_actuation": state.control.auto_actuation.value,
            "physical_write_gate_open": state.control.physical_write_gate_open,
            "auto_write_suppressed": state.control.auto_write_suppressed,
            "proposed_auto_plan": (
                {
                    "action": proposal.action.value,
                    "power": proposal.power.value,
                    "mode": proposal.mode.value,
                    "equipment_target_temperature": (
                        proposal.equipment_target_temperature
                    ),
                    "fan_rate": proposal.fan_rate,
                    "open_zones": list(proposal.open_zones),
                }
                if proposal is not None
                else None
            ),
        }

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Atomically change requested power and mode."""

        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_apply_patch({"enabled": False})
            return
        requested_mode = HA_TO_REQUESTED_MODE.get(hvac_mode)
        if requested_mode is None:
            raise HomeAssistantError("Unsupported AC Brain HVAC mode")
        state = self.coordinator.data
        if (
            hvac_mode == HVACMode.AUTO
            and (
                state is None
                or state.control.auto_actuation is not AutoActuation.ENABLED
            )
        ):
            raise HomeAssistantError("AC Brain AUTO actuation is not enabled")
        await self.coordinator.async_apply_patch(
            {"enabled": True, "mode": requested_mode}
        )

    async def async_turn_on(self) -> None:
        """Enable the last requested mode without changing it."""

        await self.coordinator.async_apply_patch({"enabled": True})

    async def async_turn_off(self) -> None:
        """Disable conditioning without losing the requested mode."""

        await self.coordinator.async_apply_patch({"enabled": False})

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the comfort target with one atomic patch."""

        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        try:
            temperature = float(value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Invalid AC Brain target temperature") from err
        if not math.isfinite(temperature):
            raise HomeAssistantError("Invalid AC Brain target temperature")
        await self.coordinator.async_apply_patch(
            {"targetTemperature": temperature}
        )

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set requested fan rate with one atomic patch."""

        fan_rate = HA_TO_DAIKIN_FAN.get(fan_mode)
        if fan_rate is None:
            raise HomeAssistantError("Unsupported AC Brain fan mode")
        await self.coordinator.async_apply_patch({"fanRate": fan_rate})
