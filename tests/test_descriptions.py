"""Consistency checks between entity descriptions and translations."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from custom_components.ariston import binary_sensor, number, select, sensor, switch, time
from custom_components.ariston.entity import AristonEntityDescription

COMPONENT = Path(__file__).parents[1] / "custom_components" / "ariston"
PLATFORMS = {
    "binary_sensor": binary_sensor.BINARY_SENSOR_TYPES,
    "number": number.NUMBER_TYPES,
    "select": select.SELECT_TYPES,
    "sensor": sensor.SENSOR_TYPES,
    "switch": switch.SWITCH_TYPES,
    "time": time.TIME_TYPES,
}


def _translations(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text())["entity"]


def test_every_description_has_a_translated_name() -> None:
    strings = _translations("strings.json")
    english = _translations("translations/en.json")
    for platform, descriptions in PLATFORMS.items():
        for description in descriptions:
            assert isinstance(description, AristonEntityDescription)
            name = strings[platform][description.translation_key]["name"]
            assert english[platform][description.translation_key]["name"] == name
            # Zone entities need the placeholder, device entities must not have it.
            assert ("{zone}" in name) is description.zone, (platform, description.key)


def test_keys_are_unique_per_platform() -> None:
    for platform, descriptions in PLATFORMS.items():
        duplicates = [k for k, n in Counter(d.key for d in descriptions).items() if n > 1]
        assert not duplicates, (platform, duplicates)


def test_no_orphan_translations() -> None:
    strings = _translations("strings.json")
    for platform, descriptions in PLATFORMS.items():
        keys = {d.translation_key for d in descriptions}
        assert set(strings[platform]) == keys, platform
