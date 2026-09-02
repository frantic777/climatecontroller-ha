"""Selected-zone switches for AC Brain."""

from __future__ import annotations

import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity


_UNUSED_ZONE_NAME = re.compile(r"^NA\d*$", re.IGNORECASE)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up switches and discover new real zones while the entry is loaded."""

    coordinator = entry.runtime_data.coordinator
    known_zones: set[str] = set()

    def add_discovered_zones() -> None:
        state = coordinator.data
        if state is None:
            return
        new_zones = [
            zone_name
            for zone_name in state.zones
            if zone_name not in known_zones
            and _UNUSED_ZONE_NAME.fullmatch(zone_name) is None
        ]
        if not new_zones:
            return

        # Mark names before handing entities to Home Assistant so a nested or
        # repeated coordinator notification cannot enqueue duplicates.
        known_zones.update(new_zones)
        async_add_entities(
            [KotlinZoneDamper(coordinator, zone_name) for zone_name in new_zones]
        )

    add_discovered_zones()
    entry.async_on_unload(coordinator.async_add_listener(add_discovered_zones))


class KotlinZoneDamper(CoordinatorEntity, SwitchEntity):
    """Whether a zone is selected for conditioning, not physical damper state."""

    def __init__(self, coordinator, zone_name: str) -> None:
        super().__init__(coordinator)
        self._zone_name = zone_name
        self._attr_unique_id = (
            f"kotlin_damper_{zone_name.lower().replace(' ', '_')}"
        )
        self._attr_name = zone_name
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        state = self.coordinator.data
        return (
            super().available
            and state is not None
            and state.accepts_commands
            and self._zone_name in state.zones
        )

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data
        zone = state.zones.get(self._zone_name) if state is not None else None
        return zone.selected if zone is not None else False

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_selected(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_selected(False)

    async def _set_selected(self, selected: bool) -> None:
        zone_name = self._zone_name

        def build_patch(state):
            if zone_name not in state.zones:
                raise HomeAssistantError("AC Brain zone is no longer available")

            selected_names = set(state.intent.selected_zones)
            if selected:
                selected_names.add(zone_name)
            else:
                selected_names.discard(zone_name)

            # The full selection is revision-protected. Resolving this factory
            # inside the coordinator's command lock prevents concurrent switch
            # calls from dropping one another's changes.
            ordered_selection = [
                name for name in state.zones if name in selected_names
            ]
            return {"selectedZones": ordered_selection}

        await self.coordinator.async_apply_patch(build_patch)
