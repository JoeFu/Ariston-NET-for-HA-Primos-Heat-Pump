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
from .plant_settings import (
    NIGHT_BEGIN,
    NIGHT_END,
    async_set_plant_setting,
    decode_clock,
    encode_clock,
    get_plant_setting,
)


@dataclass(frozen=True, kw_only=True)
class AristonTimeEntityDescription(TimeEntityDescription, AristonEntityDescription):
    """Describe an Ariston time entity backed by a cloud clock value (hour * 256 + minute)."""

    value_fn: Callable[[AristonTime], Any]
    set_fn: Callable[[AristonTime, int], Coroutine[Any, Any, Any]]


TIME_TYPES: tuple[AristonTimeEntityDescription, ...] = (
    AristonTimeEntityDescription(
        key="night_mode_start",
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda entity: get_plant_setting(entity.device, NIGHT_BEGIN),
        set_fn=lambda entity, value: async_set_plant_setting(entity.device, NIGHT_BEGIN, value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid, WheType.NuosSplit],
    ),
    AristonTimeEntityDescription(
        key="night_mode_end",
        icon="mdi:weather-sunny",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda entity: get_plant_setting(entity.device, NIGHT_END),
        set_fn=lambda entity, value: async_set_plant_setting(entity.device, NIGHT_END, value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid, WheType.NuosSplit],
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
    """A time-of-day setting stored by the cloud as hour * 256 + minute."""

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
        return decode_clock(self.entity_description.value_fn(self))

    async def async_set_value(self, value: time) -> None:
        """Write a new time."""
        encoded = encode_clock(value)
        await self.async_write(lambda: self.entity_description.set_fn(self, encoded))
