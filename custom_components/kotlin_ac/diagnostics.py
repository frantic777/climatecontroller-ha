"""Redacted diagnostics for the AC Brain config entry."""

from __future__ import annotations

from collections import Counter

from .models import CommandStatus, ControlIssue, SensorStatus


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """Return useful state without URLs, credentials, errors, or room names."""

    coordinator = entry.runtime_data.coordinator
    state = coordinator.data
    if state is None:
        return {
            "coordinator_update_success": coordinator.last_update_success,
            "state_available": False,
        }

    demands = Counter(
        zone.demand.value if zone.demand is not None else "UNREPORTED"
        for zone in state.zones.values()
    )
    fresh_count = sum(zone.sensor_fresh is True for zone in state.zones.values())
    statuses = Counter(
        zone.sensor_status.value if zone.sensor_status is not None else "UNREPORTED"
        for zone in state.zones.values()
    )
    selected_count = sum(zone.selected for zone in state.zones.values())
    proposal = state.control.proposed_auto_plan

    return {
        "coordinator_update_success": coordinator.last_update_success,
        "state_available": True,
        "api_version": state.api_version,
        "revisions": {
            "desired": state.desired_revision,
            "plan": state.plan_revision,
            "applied_plan": state.applied_plan_revision,
        },
        "intent": {
            "enabled": state.intent.enabled,
            "mode": state.intent.mode.value,
            "target_temperature": state.intent.target_temperature,
            "fan_rate": state.intent.fan_rate,
        },
        "control": {
            "action": (
                state.control.action.value
                if state.control.action is not None
                else None
            ),
            "effective_mode": state.control.effective_mode,
            "lockout_remaining_seconds": (
                state.control.lockout_remaining_seconds
            ),
            "decision_at": state.control.decision_at,
            "issues": [issue.value for issue in state.control.issues],
            "persistent_call": ControlIssue.PERSISTENT_CALL in state.control.issues,
            "auto_actuation": state.control.auto_actuation.value,
            "physical_write_gate_open": (
                state.control.physical_write_gate_open
            ),
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
                    # Diagnostics deliberately omit room names.
                    "open_zone_count": len(proposal.open_zones),
                }
                if proposal is not None
                else None
            ),
        },
        "device": {
            "available": state.device.available,
            "last_seen": state.device.last_seen,
            "power": state.device.power,
            "mode": state.device.mode,
        },
        "zones": {
            "count": len(state.zones),
            "selected_count": selected_count,
            "fresh_count": fresh_count,
            "stale_count": statuses[SensorStatus.STALE.value],
            "invalid_count": statuses[SensorStatus.INVALID.value],
            "missing_count": statuses[SensorStatus.MISSING.value],
            "demand_counts": dict(sorted(demands.items())),
            "desired_open_damper_count": sum(
                zone.desired_damper is True for zone in state.zones.values()
            ),
            "actual_open_damper_count": sum(
                zone.actual_damper is True for zone in state.zones.values()
            ),
            "damper_mismatch_count": sum(
                zone.desired_damper is not None
                and zone.actual_damper is not None
                and zone.desired_damper != zone.actual_damper
                for zone in state.zones.values()
            ),
        },
        "command": {
            "status": state.command.status.value,
            "attempt": state.command.attempt,
            "pending": state.command.status
            in {
                CommandStatus.QUEUED,
                CommandStatus.PENDING,
                CommandStatus.APPLYING,
                CommandStatus.RETRYING,
            },
            "pending_age_seconds": state.observability.pending_command_age_seconds,
            "has_error": state.command.last_error is not None,
        },
        "runtime": {
            "compressor_running": state.observability.compressor_running,
            "effective_direction": state.observability.effective_direction,
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
            "cumulative_heat_degree_minutes": (
                state.observability.cumulative_heat_degree_minutes
            ),
            "cumulative_cool_degree_minutes": (
                state.observability.cumulative_cool_degree_minutes
            ),
        },
    }
