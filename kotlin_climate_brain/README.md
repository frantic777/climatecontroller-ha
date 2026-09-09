# Kotlin Climate Brain

This Home Assistant app runs the one Climate Controller runtime for a zoned Daikin SkyFi system.
Supervisor provides singleton process ownership; the app starts immediately after every restart
without handoff files, commissioning markers, runtime selection, or write gates.

The controller keeps Home Assistant settings authoritative and persists power, requested mode,
target, fan, selected rooms, revision, runtime continuity, and any pending command. AUTO chooses
heating or cooling from per-room temperature and humidity-adjusted demand. Humidity never rewrites
the configured target. SkyFi and wall-controller reads are telemetry only and can never replace
Home Assistant intent; physical drift is reconciled back to the persisted settings.

SkyFi access is serialized. A command always writes complete control state first and complete zone
state second, followed by device read-back. The Home Assistant integration is asynchronous, so UI
changes return after durable acceptance while physical confirmation appears on subsequent polls.

The database bootstrap supports clean, legacy, current, interrupted, and stale-rollout database
states. It preserves readable controller data. MariaDB, MQTT, and SkyFi availability never gate
process startup: `/readyz` reports any unavailable function and the controller retries without
resetting data or exiting.

Health endpoints are `/healthz` and `/readyz`; the sole state endpoint is `/api/v2/state`.
