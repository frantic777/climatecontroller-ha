"""Immutable wire models for the AC Brain REST APIs.

This module deliberately has no Home Assistant or aiohttp imports.  It is the
normalization boundary between the legacy state document and API v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, TypeVar


class ModelValidationError(ValueError):
    """Raised when a server document cannot be represented safely."""


class RequestedMode(str, Enum):
    """Durable user mode; AUTO is intentionally a controller-only mode."""

    HEAT = "HEAT"
    COOL = "COOL"
    AUTO = "AUTO"
    FAN = "FAN"
    DRY = "DRY"


class AutoActuation(str, Enum):
    """Whether AUTO proposals are disabled, shadowed, or physically enabled."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    ENABLED = "enabled"


class ControlAction(str, Enum):
    OFF = "OFF"
    IDLE = "IDLE"
    HEATING = "HEATING"
    COOLING = "COOLING"
    FAN = "FAN"
    DRYING = "DRYING"
    LOCKOUT = "LOCKOUT"
    DEGRADED = "DEGRADED"


class DevicePower(str, Enum):
    OFF = "OFF"
    ON = "ON"


class DeviceMode(str, Enum):
    HEAT = "HEAT"
    COOL = "COOL"
    FAN = "FAN"
    DRY = "DRY"


class ZoneDemand(str, Enum):
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"
    SATISFIED = "SATISFIED"
    HEAT_CALL = "HEAT_CALL"
    COOL_CALL = "COOL_CALL"


class SensorStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    FRESH = "FRESH"
    MISSING = "MISSING"
    STALE = "STALE"
    INVALID = "INVALID"


class ControlIssue(str, Enum):
    MISSING_SENSOR = "MISSING_SENSOR"
    STALE_SENSOR = "STALE_SENSOR"
    INVALID_SENSOR = "INVALID_SENSOR"
    UNKNOWN_ZONE = "UNKNOWN_ZONE"
    INSUFFICIENT_AIRFLOW = "INSUFFICIENT_AIRFLOW"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    INVALID_TARGET = "INVALID_TARGET"
    PERSISTENT_CALL = "PERSISTENT_CALL"


class CommandStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    QUEUED = "QUEUED"
    PENDING = "PENDING"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    CONFIRMED = "CONFIRMED"
    RETRYING = "RETRYING"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
    NOOP = "NOOP"


class ComponentStatus(str, Enum):
    """Sanitized readiness state for one controller dependency."""

    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


@dataclass(frozen=True, slots=True)
class ControlIntent:
    enabled: bool
    mode: RequestedMode
    target_temperature: float
    fan_rate: str
    selected_zones: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposedAutoPlan:
    action: ControlAction
    power: DevicePower
    mode: DeviceMode
    equipment_target_temperature: float
    fan_rate: str
    open_zones: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlStatus:
    action: ControlAction | None
    effective_mode: str | None
    reason: str | None
    lockout_remaining_seconds: float | None
    decision_at: str | None
    issues: tuple[ControlIssue, ...] = ()
    auto_actuation: AutoActuation = AutoActuation.DISABLED
    physical_write_gate_open: bool = False
    auto_write_suppressed: bool = False
    proposed_auto_plan: ProposedAutoPlan | None = None


@dataclass(frozen=True, slots=True)
class ZoneStatus:
    selected: bool
    temperature: float | None
    sensor_fresh: bool | None
    demand: ZoneDemand | None
    desired_damper: bool | None
    actual_damper: bool | None
    sensor_status: SensorStatus | None = None


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    available: bool | None
    last_seen: str | None
    power: str | None
    mode: str | None


@dataclass(frozen=True, slots=True)
class CommandInfo:
    command_id: str | None
    status: CommandStatus
    attempt: int
    last_error: str | None
    desired_revision: int | None = None
    plan_revision: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeObservability:
    compressor_running: bool = False
    effective_direction: str | None = None
    confirmed_compressor_starts: int = 0
    confirmed_direction_changes: int = 0
    last_compressor_started_at: str | None = None
    sensorless_run_started_at: str | None = None
    last_compressor_stopped_at: str | None = None
    last_direction_change_at: str | None = None
    direction_continuity_unknown_since: str | None = None
    cumulative_heat_degree_minutes: float = 0.0
    cumulative_cool_degree_minutes: float = 0.0
    pending_command_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class AcState:
    api_version: int
    desired_revision: int | None
    plan_revision: int | None
    applied_plan_revision: int | None
    intent: ControlIntent
    control: ControlStatus
    zones: Mapping[str, ZoneStatus]
    device: DeviceStatus
    command: CommandInfo
    current_temperature: float | None
    current_temperature_contributors: tuple[str, ...] = ()
    controller_ready: bool = False
    readiness_components: Mapping[str, ComponentStatus] = field(
        default_factory=lambda: MappingProxyType({})
    )
    observability: RuntimeObservability = field(default_factory=RuntimeObservability)

    @property
    def accepts_commands(self) -> bool:
        """Whether the responsive API can durably accept desired-state writes."""

        return (
            self.api_version == 2
            and self.desired_revision is not None
            and self.readiness_components.get("persistence")
            is ComponentStatus.READY
            and self.control.physical_write_gate_open
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    state: AcState
    status_code: int
    accepted_pending: bool

    @property
    def command(self) -> CommandInfo:
        return self.state.command


_MISSING = object()
_SAFE_COMPONENT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
EnumT = TypeVar("EnumT", bound=Enum)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelValidationError(f"{path} must be an object")
    return value


def _alias(
    data: Mapping[str, Any], *names: str, default: Any = _MISSING, path: str
) -> Any:
    for name in names:
        if name in data:
            return data[name]
    if default is not _MISSING:
        return default
    raise ModelValidationError(f"{path} is required")


def _boolean(value: Any, path: str, *, optional: bool = False) -> bool | None:
    if value is None and optional:
        return None
    if not isinstance(value, bool):
        raise ModelValidationError(f"{path} must be a boolean")
    return value


def _number(value: Any, path: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ModelValidationError(f"{path} must be finite")
    return result


def _integer(value: Any, path: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelValidationError(f"{path} must be a non-negative integer")
    return value


def _string(value: Any, path: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ModelValidationError(f"{path} must be a string")
    return value


def _enum(enum_type: type[EnumT], value: Any, path: str) -> EnumT:
    raw = _string(value, path)
    try:
        return enum_type(raw.upper())  # type: ignore[arg-type,return-value]
    except ValueError as err:
        raise ModelValidationError(f"{path} has unsupported value") from err


def _optional_enum(
    enum_type: type[EnumT], value: Any, path: str
) -> EnumT | None:
    if value is None:
        return None
    return _enum(enum_type, value, path)


def _casefold_enum(
    enum_type: type[EnumT], value: Any, path: str
) -> EnumT:
    raw = _string(value, path)
    try:
        return enum_type(raw.lower())  # type: ignore[arg-type,return-value]
    except ValueError as err:
        raise ModelValidationError(f"{path} has unsupported value") from err


def _revision(data: Mapping[str, Any], snake: str, camel: str) -> int | None:
    return _integer(
        _alias(data, snake, camel, default=None, path=snake),
        snake,
        optional=True,
    )


def _parse_command(value: Any, path: str = "command") -> CommandInfo:
    data = _mapping(value, path)
    command_id = _string(
        _alias(data, "id", "commandId", "command_id", default=None, path=f"{path}.id"),
        f"{path}.id",
        optional=True,
    )
    status_value = _alias(data, "status", default="UNKNOWN", path=f"{path}.status")
    status = _enum(CommandStatus, status_value, f"{path}.status")
    attempt = _integer(
        _alias(data, "attempt", default=0, path=f"{path}.attempt"),
        f"{path}.attempt",
    )
    last_error = _string(
        _alias(
            data,
            "lastError",
            "last_error",
            default=None,
            path=f"{path}.lastError",
        ),
        f"{path}.lastError",
        optional=True,
    )
    return CommandInfo(
        command_id=command_id,
        status=status,
        attempt=attempt,
        last_error=last_error,
        desired_revision=_revision(data, "desired_revision", "desiredRevision"),
        plan_revision=_revision(data, "plan_revision", "planRevision"),
    )


def parse_command(value: Mapping[str, Any]) -> CommandInfo:
    """Parse a command-status response, including an optional wrapper."""

    data = _mapping(value, "response")
    if "command" in data:
        return _parse_command(data["command"])
    return _parse_command(data)


def _parse_v2(data: Mapping[str, Any]) -> AcState:
    intent_data = _mapping(_alias(data, "intent", path="intent"), "intent")
    mode = _enum(
        RequestedMode,
        _alias(intent_data, "mode", path="intent.mode"),
        "intent.mode",
    )
    enabled = _boolean(
        _alias(intent_data, "enabled", path="intent.enabled"), "intent.enabled"
    )
    target_temperature = _number(
        _alias(
            intent_data,
            "targetTemperature",
            "target_temperature",
            path="intent.targetTemperature",
        ),
        "intent.targetTemperature",
    )
    fan_rate = _string(
        _alias(
            intent_data,
            "fanRate",
            "fan_rate",
            path="intent.fanRate",
        ),
        "intent.fanRate",
    )
    selected_raw = _alias(
        intent_data,
        "selectedZones",
        "selected_zones",
        path="intent.selectedZones",
    )
    if not isinstance(selected_raw, (list, tuple)):
        raise ModelValidationError("intent.selectedZones must be an array")
    selected_zones = tuple(
        _string(zone, f"intent.selectedZones[{index}]")
        for index, zone in enumerate(selected_raw)
    )
    if len(set(selected_zones)) != len(selected_zones):
        raise ModelValidationError("intent.selectedZones must not contain duplicates")

    control_data = _mapping(_alias(data, "control", path="control"), "control")
    action = _optional_enum(
        ControlAction,
        _alias(control_data, "action", default=None, path="control.action"),
        "control.action",
    )
    effective_mode_raw = _alias(
        control_data,
        "effectiveMode",
        "effective_mode",
        default=None,
        path="control.effectiveMode",
    )
    effective_mode = _string(
        effective_mode_raw, "control.effectiveMode", optional=True
    )
    if effective_mode is not None:
        effective_mode = effective_mode.upper()
    reason = _string(
        _alias(control_data, "reason", default=None, path="control.reason"),
        "control.reason",
        optional=True,
    )
    lockout = _number(
        _alias(
            control_data,
            "lockoutRemainingSeconds",
            "lockout_remaining_seconds",
            default=None,
            path="control.lockoutRemainingSeconds",
        ),
        "control.lockoutRemainingSeconds",
        optional=True,
    )
    if lockout is not None and lockout < 0:
        raise ModelValidationError(
            "control.lockoutRemainingSeconds must be non-negative"
        )
    decision_at = _string(
        _alias(
            control_data,
            "decisionAt",
            "decision_at",
            default=None,
            path="control.decisionAt",
        ),
        "control.decisionAt",
        optional=True,
    )
    issues_raw = _alias(
        control_data, "issues", default=[], path="control.issues"
    )
    if not isinstance(issues_raw, (list, tuple)):
        raise ModelValidationError("control.issues must be an array")
    issues = tuple(
        _enum(ControlIssue, issue, f"control.issues[{index}]")
        for index, issue in enumerate(issues_raw)
    )
    if len(set(issues)) != len(issues):
        raise ModelValidationError("control.issues must not contain duplicates")

    auto_actuation = _casefold_enum(
        AutoActuation,
        _alias(
            control_data,
            "autoActuation",
            "auto_actuation",
            default="disabled",
            path="control.autoActuation",
        ),
        "control.autoActuation",
    )
    auto_write_suppressed = _boolean(
        _alias(
            control_data,
            "autoWriteSuppressed",
            "auto_write_suppressed",
            default=False,
            path="control.autoWriteSuppressed",
        ),
        "control.autoWriteSuppressed",
    )
    physical_write_gate_open = _boolean(
        _alias(
            control_data,
            "physicalWriteGateOpen",
            "physical_write_gate_open",
            default=False,
            path="control.physicalWriteGateOpen",
        ),
        "control.physicalWriteGateOpen",
    )
    proposal_raw = _alias(
        control_data,
        "proposedAutoPlan",
        "proposed_auto_plan",
        default=None,
        path="control.proposedAutoPlan",
    )
    proposed_auto_plan = None
    if proposal_raw is not None:
        proposal = _mapping(proposal_raw, "control.proposedAutoPlan")
        open_zones_raw = _alias(
            proposal,
            "openZones",
            "open_zones",
            path="control.proposedAutoPlan.openZones",
        )
        if not isinstance(open_zones_raw, (list, tuple)):
            raise ModelValidationError(
                "control.proposedAutoPlan.openZones must be an array"
            )
        open_zones = tuple(
            _string(zone, f"control.proposedAutoPlan.openZones[{index}]")
            for index, zone in enumerate(open_zones_raw)
        )
        if any(not zone for zone in open_zones):
            raise ModelValidationError(
                "control.proposedAutoPlan.openZones must not contain blank names"
            )
        if len(set(open_zones)) != len(open_zones):
            raise ModelValidationError(
                "control.proposedAutoPlan.openZones must not contain duplicates"
            )
        proposed_auto_plan = ProposedAutoPlan(
            action=_enum(
                ControlAction,
                _alias(
                    proposal,
                    "action",
                    path="control.proposedAutoPlan.action",
                ),
                "control.proposedAutoPlan.action",
            ),
            power=_enum(
                DevicePower,
                _alias(
                    proposal,
                    "power",
                    path="control.proposedAutoPlan.power",
                ),
                "control.proposedAutoPlan.power",
            ),
            mode=_enum(
                DeviceMode,
                _alias(
                    proposal,
                    "mode",
                    path="control.proposedAutoPlan.mode",
                ),
                "control.proposedAutoPlan.mode",
            ),
            equipment_target_temperature=_number(
                _alias(
                    proposal,
                    "equipmentTargetTemperature",
                    "equipment_target_temperature",
                    path=(
                        "control.proposedAutoPlan.equipmentTargetTemperature"
                    ),
                ),
                "control.proposedAutoPlan.equipmentTargetTemperature",
            ),
            fan_rate=_string(
                _alias(
                    proposal,
                    "fanRate",
                    "fan_rate",
                    path="control.proposedAutoPlan.fanRate",
                ),
                "control.proposedAutoPlan.fanRate",
            ),
            open_zones=open_zones,
        )

    zones_data = _mapping(_alias(data, "zones", path="zones"), "zones")
    parsed_zones: dict[str, ZoneStatus] = {}
    for zone_name, raw_zone in zones_data.items():
        if not isinstance(zone_name, str) or not zone_name:
            raise ModelValidationError("zone names must be non-empty strings")
        zone_data = _mapping(raw_zone, f"zones.{zone_name}")
        zone_path = f"zones.{zone_name}"
        selected = _boolean(
            _alias(zone_data, "selected", path=f"{zone_path}.selected"),
            f"{zone_path}.selected",
        )
        temperature = _number(
            _alias(
                zone_data,
                "temperature",
                default=None,
                path=f"{zone_path}.temperature",
            ),
            f"{zone_path}.temperature",
            optional=True,
        )
        sensor_fresh = _boolean(
            _alias(
                zone_data,
                "sensorFresh",
                "sensor_fresh",
                default=None,
                path=f"{zone_path}.sensorFresh",
            ),
            f"{zone_path}.sensorFresh",
            optional=True,
        )
        sensor_status_raw = _alias(
            zone_data,
            "sensorStatus",
            "sensor_status",
            default=None,
            path=f"{zone_path}.sensorStatus",
        )
        if sensor_status_raw is None:
            sensor_status = (
                SensorStatus.FRESH
                if sensor_fresh is True
                else SensorStatus.MISSING
                if sensor_fresh is False and temperature is None
                else SensorStatus.STALE
                if sensor_fresh is False
                else None
            )
        else:
            sensor_status = _enum(
                SensorStatus, sensor_status_raw, f"{zone_path}.sensorStatus"
            )
        demand = _optional_enum(
            ZoneDemand,
            _alias(zone_data, "demand", default=None, path=f"{zone_path}.demand"),
            f"{zone_path}.demand",
        )
        desired_damper = _boolean(
            _alias(
                zone_data,
                "desiredDamper",
                "desired_damper",
                default=None,
                path=f"{zone_path}.desiredDamper",
            ),
            f"{zone_path}.desiredDamper",
            optional=True,
        )
        actual_damper = _boolean(
            _alias(
                zone_data,
                "actualDamper",
                "actual_damper",
                default=None,
                path=f"{zone_path}.actualDamper",
            ),
            f"{zone_path}.actualDamper",
            optional=True,
        )
        parsed_zones[zone_name] = ZoneStatus(
            selected,
            temperature,
            sensor_fresh,
            demand,
            desired_damper,
            actual_damper,
            sensor_status,
        )

    device_data = _mapping(_alias(data, "device", path="device"), "device")
    available = _boolean(
        _alias(device_data, "available", default=None, path="device.available"),
        "device.available",
        optional=True,
    )
    last_seen = _string(
        _alias(
            device_data,
            "lastSeen",
            "last_seen",
            default=None,
            path="device.lastSeen",
        ),
        "device.lastSeen",
        optional=True,
    )
    power = _string(
        _alias(device_data, "power", default=None, path="device.power"),
        "device.power",
        optional=True,
    )
    mode_value = _string(
        _alias(device_data, "mode", default=None, path="device.mode"),
        "device.mode",
        optional=True,
    )
    device = DeviceStatus(
        available,
        last_seen,
        power.upper() if power is not None else None,
        mode_value.upper() if mode_value is not None else None,
    )

    command = _parse_command(_alias(data, "command", path="command"))
    observability_data = _mapping(
        _alias(data, "observability", default={}, path="observability"),
        "observability",
    )
    compressor_running = _boolean(
        _alias(
            observability_data,
            "compressorRunning",
            "compressor_running",
            default=False,
            path="observability.compressorRunning",
        ),
        "observability.compressorRunning",
    )
    effective_direction = _string(
        _alias(
            observability_data,
            "effectiveDirection",
            "effective_direction",
            default=None,
            path="observability.effectiveDirection",
        ),
        "observability.effectiveDirection",
        optional=True,
    )
    if effective_direction is not None:
        effective_direction = effective_direction.upper()
        if effective_direction not in {"HEAT", "COOL"}:
            raise ModelValidationError(
                "observability.effectiveDirection has unsupported value"
            )
    confirmed_compressor_starts = _integer(
        _alias(
            observability_data,
            "confirmedCompressorStarts",
            "confirmed_compressor_starts",
            default=0,
            path="observability.confirmedCompressorStarts",
        ),
        "observability.confirmedCompressorStarts",
    )
    confirmed_direction_changes = _integer(
        _alias(
            observability_data,
            "confirmedDirectionChanges",
            "confirmed_direction_changes",
            default=0,
            path="observability.confirmedDirectionChanges",
        ),
        "observability.confirmedDirectionChanges",
    )
    def observability_time(camel: str, snake: str) -> str | None:
        return _string(
            _alias(
                observability_data,
                camel,
                snake,
                default=None,
                path=f"observability.{camel}",
            ),
            f"observability.{camel}",
            optional=True,
        )

    cumulative_heat = _number(
        _alias(
            observability_data,
            "cumulativeHeatDegreeMinutes",
            "cumulative_heat_degree_minutes",
            default=0.0,
            path="observability.cumulativeHeatDegreeMinutes",
        ),
        "observability.cumulativeHeatDegreeMinutes",
    )
    cumulative_cool = _number(
        _alias(
            observability_data,
            "cumulativeCoolDegreeMinutes",
            "cumulative_cool_degree_minutes",
            default=0.0,
            path="observability.cumulativeCoolDegreeMinutes",
        ),
        "observability.cumulativeCoolDegreeMinutes",
    )
    pending_age = _number(
        _alias(
            observability_data,
            "pendingCommandAgeSeconds",
            "pending_command_age_seconds",
            default=None,
            path="observability.pendingCommandAgeSeconds",
        ),
        "observability.pendingCommandAgeSeconds",
        optional=True,
    )
    if cumulative_heat < 0 or cumulative_cool < 0:
        raise ModelValidationError("cumulative degree-minutes must be non-negative")
    if pending_age is not None and pending_age < 0:
        raise ModelValidationError(
            "observability.pendingCommandAgeSeconds must be non-negative"
        )
    observability = RuntimeObservability(
        compressor_running=compressor_running,
        effective_direction=effective_direction,
        confirmed_compressor_starts=confirmed_compressor_starts,
        confirmed_direction_changes=confirmed_direction_changes,
        last_compressor_started_at=observability_time(
            "lastCompressorStartedAt", "last_compressor_started_at"
        ),
        sensorless_run_started_at=observability_time(
            "sensorlessRunStartedAt", "sensorless_run_started_at"
        ),
        last_compressor_stopped_at=observability_time(
            "lastCompressorStoppedAt", "last_compressor_stopped_at"
        ),
        last_direction_change_at=observability_time(
            "lastDirectionChangeAt", "last_direction_change_at"
        ),
        direction_continuity_unknown_since=observability_time(
            "directionContinuityUnknownSince",
            "direction_continuity_unknown_since",
        ),
        cumulative_heat_degree_minutes=cumulative_heat,
        cumulative_cool_degree_minutes=cumulative_cool,
        pending_command_age_seconds=pending_age,
    )
    controller_ready = _boolean(
        _alias(
            data,
            "controllerReady",
            "controller_ready",
            default=False,
            path="controllerReady",
        ),
        "controllerReady",
    )
    components_data = _mapping(
        _alias(
            data,
            "readinessComponents",
            "readiness_components",
            default={},
            path="readinessComponents",
        ),
        "readinessComponents",
    )
    readiness_components: dict[str, ComponentStatus] = {}
    for component_name, raw_status in components_data.items():
        if not isinstance(component_name, str) or _SAFE_COMPONENT_NAME.fullmatch(
            component_name
        ) is None:
            raise ModelValidationError(
                "readinessComponents names must be safe identifiers"
            )
        status = _string(raw_status, f"readinessComponents.{component_name}")
        try:
            readiness_components[component_name] = ComponentStatus(status.lower())
        except ValueError as err:
            raise ModelValidationError(
                f"readinessComponents.{component_name} has unsupported value"
            ) from err
    explicit_current = _number(
        _alias(
            data,
            "currentTemperature",
            "current_temperature",
            default=None,
            path="currentTemperature",
        ),
        "currentTemperature",
        optional=True,
    )
    contributors_raw = _alias(
        data,
        "currentTemperatureContributors",
        "current_temperature_contributors",
        default=None,
        path="currentTemperatureContributors",
    )
    if contributors_raw is None:
        temperature_contributors = tuple(
            zone_name
            for zone_name, zone in parsed_zones.items()
            if zone.selected and zone.sensor_fresh is True and zone.temperature is not None
        )
    else:
        if not isinstance(contributors_raw, (list, tuple)):
            raise ModelValidationError(
                "currentTemperatureContributors must be an array"
            )
        temperature_contributors = tuple(
            _string(name, f"currentTemperatureContributors[{index}]")
            for index, name in enumerate(contributors_raw)
        )
        if len(set(temperature_contributors)) != len(temperature_contributors):
            raise ModelValidationError(
                "currentTemperatureContributors must not contain duplicates"
            )
        if any(name not in parsed_zones for name in temperature_contributors):
            raise ModelValidationError(
                "currentTemperatureContributors must name reported zones"
            )
    if explicit_current is None:
        contributor_temperatures = [
            parsed_zones[name].temperature
            for name in temperature_contributors
            if parsed_zones[name].temperature is not None
        ]
        current_temperature = (
            sum(contributor_temperatures) / len(contributor_temperatures)
            if contributor_temperatures
            else None
        )
    else:
        current_temperature = explicit_current

    return AcState(
        api_version=2,
        desired_revision=_revision(data, "desired_revision", "desiredRevision"),
        plan_revision=_revision(data, "plan_revision", "planRevision"),
        applied_plan_revision=_revision(
            data, "applied_plan_revision", "appliedPlanRevision"
        ),
        intent=ControlIntent(
            enabled, mode, target_temperature, fan_rate, selected_zones
        ),
        control=ControlStatus(
            action=action,
            effective_mode=effective_mode,
            reason=reason,
            lockout_remaining_seconds=lockout,
            decision_at=decision_at,
            issues=issues,
            auto_actuation=auto_actuation,
            physical_write_gate_open=physical_write_gate_open,
            auto_write_suppressed=auto_write_suppressed,
            proposed_auto_plan=proposed_auto_plan,
        ),
        zones=MappingProxyType(parsed_zones),
        device=device,
        command=command,
        current_temperature=current_temperature,
        current_temperature_contributors=temperature_contributors,
        controller_ready=controller_ready,
        readiness_components=MappingProxyType(readiness_components),
        observability=observability,
    )


def _parse_v1(data: Mapping[str, Any]) -> AcState:
    power = _string(
        _alias(data, "power", default="OFF", path="power"), "power"
    ).upper()
    mode = _enum(
        RequestedMode,
        _alias(data, "mode", default="AUTO", path="mode"),
        "mode",
    )
    target_temperature = _number(
        _alias(
            data,
            "targetTemperature",
            "target_temperature",
            default=22.0,
            path="targetTemperature",
        ),
        "targetTemperature",
    )
    fan_rate = _string(
        _alias(
            data,
            "fanRate",
            "fan_rate",
            default="LOW",
            path="fanRate",
        ),
        "fanRate",
    )
    zones_data = _mapping(
        _alias(data, "zones", default={}, path="zones"), "zones"
    )
    parsed_zones: dict[str, ZoneStatus] = {}
    selected_zones: list[str] = []
    for zone_name, raw_selected in zones_data.items():
        if not isinstance(zone_name, str) or not zone_name:
            raise ModelValidationError("zone names must be non-empty strings")
        selected = _boolean(raw_selected, f"zones.{zone_name}")
        if selected:
            selected_zones.append(zone_name)
        parsed_zones[zone_name] = ZoneStatus(
            selected=selected,
            temperature=None,
            sensor_fresh=None,
            demand=None,
            desired_damper=selected,
            actual_damper=None,
        )

    current_temperature = _number(
        _alias(
            data,
            "currentTemperature",
            "current_temperature",
            default=None,
            path="currentTemperature",
        ),
        "currentTemperature",
        optional=True,
    )
    enabled = power != "OFF"
    # Legacy /state is the virtual/requested state.  It can prove that the
    # desired state is off, but a powered state cannot prove a physical action.
    action = ControlAction.OFF if not enabled else None

    return AcState(
        api_version=1,
        desired_revision=None,
        plan_revision=None,
        applied_plan_revision=None,
        intent=ControlIntent(
            enabled=enabled,
            mode=mode,
            target_temperature=target_temperature,
            fan_rate=fan_rate,
            selected_zones=tuple(selected_zones),
        ),
        control=ControlStatus(
            action=action,
            effective_mode=None,
            reason=None,
            lockout_remaining_seconds=None,
            decision_at=None,
        ),
        zones=MappingProxyType(parsed_zones),
        device=DeviceStatus(
            available=None,
            last_seen=None,
            power=None,
            mode=None,
        ),
        command=CommandInfo(None, CommandStatus.UNKNOWN, 0, None),
        current_temperature=current_temperature,
        current_temperature_contributors=(),
        controller_ready=False,
        readiness_components=MappingProxyType({}),
    )


def parse_state(value: Mapping[str, Any]) -> AcState:
    """Normalize a v1 or v2 state document into one immutable representation."""

    data = _mapping(value, "response")
    version_value = _alias(
        data, "api_version", "apiVersion", default=None, path="api_version"
    )
    if version_value is None:
        return _parse_v1(data)
    version = _integer(version_value, "api_version")
    if version == 1:
        return _parse_v1(data)
    if version == 2:
        return _parse_v2(data)
    raise ModelValidationError("api_version is unsupported")


__all__ = [
    "AcState",
    "AutoActuation",
    "CommandInfo",
    "CommandResult",
    "CommandStatus",
    "ComponentStatus",
    "ControlAction",
    "ControlIssue",
    "ControlIntent",
    "ControlStatus",
    "DeviceMode",
    "DevicePower",
    "DeviceStatus",
    "ModelValidationError",
    "RequestedMode",
    "ProposedAutoPlan",
    "RuntimeObservability",
    "SensorStatus",
    "ZoneDemand",
    "ZoneStatus",
    "parse_command",
    "parse_state",
]
