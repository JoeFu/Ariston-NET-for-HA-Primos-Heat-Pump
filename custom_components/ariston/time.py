"""Time entities for Ariston devices (night mode window on Lydos Hybrid)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import time
from typing import Any

from ariston.const import SystemType, WheType

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities


@dataclass(frozen=True, kw_only=True)
class AristonTimeEntityDescription(TimeEntityDescription, AristonEntityDescription):
    """Describe an Ariston time entity whose cloud value is minutes after midnight."""

    minutes_fn: Callable[[AristonTime], Any]
    set_minutes_fn: Callable[[AristonTime, int], Coroutine[Any, Any, Any]]


TIME_TYPES: tuple[AristonTimeEntityDescription, ...] = (
    AristonTimeEntityDescription(
        key="night_mode_start",
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
        minutes_fn=lambda entity: entity.device.night_mode_begin_as_minutes_value,
        set_minutes_fn=lambda entity, minutes: (
            entity.device.async_set_night_mode_begin_as_minutes_value(minutes)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonTimeEntityDescription(
        key="night_mode_end",
        icon="mdi:weather-sunny",
        entity_category=EntityCategory.CONFIG,
        minutes_fn=lambda entity: entity.device.night_mode_end_as_minutes_value,
        set_minutes_fn=lambda entity, minutes: (
            entity.device.async_set_night_mode_end_as_minutes_value(minutes)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston time entities."""
    async_add_entities(build_entities(entry, TIME_TYPES, AristonTime))


class AristonTime(AristonEntity, TimeEntity):
    """A time-of-day setting stored by the cloud as minutes after midnight."""

    entity_description: AristonTimeEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonTimeEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator, description, zone)

    @property
    def native_value(self) -> time | None:
        """Return the configured time."""
        raw = self.entity_description.minutes_fn(self)
        if raw is None:
            return None
        try:
            minutes = int(raw) % (24 * 60)
        except (TypeError, ValueError):
            return None
        return time(hour=minutes // 60, minute=minutes % 60)

    async def async_set_value(self, value: time) -> None:
        """Write a new time."""
        await self.entity_description.set_minutes_fn(self, value.hour * 60 + value.minute)
        self.notify_state_written()
