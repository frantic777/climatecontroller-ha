# Public distribution rules

This repository is a generated publication boundary, not the controller source of truth.

- Never add controller source, credentials, household data, internal IP inventories, database
  contents, commissioning handoffs, or private-repository links.
- `kotlin_climate_brain/` and `custom_components/kotlin_ac/` are synchronized only from a tested,
  immutable release of the private source repository.
- The app version, integration manifest version, public tag, and GHCR image tag must match exactly.
- Never replace or move an existing release tag. Publish a new stable semantic version.
- Run `python3 scripts/validate_distribution.py` and package the integration before committing.

