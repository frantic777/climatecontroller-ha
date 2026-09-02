# Home Assistant app metadata

- Preserve saved-user options during upgrades; do not add deployment logic that writes HVAC mode,
  target, fan, power, or selected rooms.
- Keep the image reference generic so Supervisor resolves the signed multi-architecture manifest.
- Fail-safe defaults belong only to first installation; they are not migration instructions.
- Bump `config.yaml` only as part of the matching immutable source release.

