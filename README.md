# Ariston NET for HA - Primos Heat Pump

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate with hassfest](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/hassfest.yml/badge.svg)](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/hassfest.yml)
[![HACS Action](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/hacs.yml/badge.svg)](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/hacs.yml)
[![CodeQL](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump/actions/workflows/codeql.yml)

Control and monitor **Ariston, Chaffoteaux, Elco, ATAG, NTI, HTP and Racold** boilers, heat pumps and
water heaters that are connected to the **Ariston NET** cloud (the devices you see in the Ariston NET app).

The integration talks to the same API the official app uses, through the
[`ariston`](https://pypi.org/project/ariston/) Python package. Everything is configured from the
Home Assistant UI; no YAML is needed.

> **Upgrading from 0.x?** Entity names changed (they are now "*Device name* + *Function*" and translatable),
> but every entity keeps its unique ID, so entity IDs, history and dashboards are untouched.
> See [What changed in 1.0](#what-changed-in-10).

---

## Features

- **Climate** entity per heating zone (named after the zone you set in the app) with heat / auto / cool /
  off, current and target temperature, and the system mode (Summer, Winter, Heating only, …) as presets.
- **Water heater** entity with target temperature and operation modes. On Velis water heaters the mode
  list also contains **off**, and the setpoint range follows the selected mode as documented in the
  Ariston manual (e.g. Primos / Nuos Split: GREEN up to the heat-pump ceiling of 60 °C, COMFORT and
  BOOST up to 70 °C, i-Memory from 50 °C); out-of-range requests are clamped and logged.
- **Sensors**: heating circuit pressure, flow / return / outside / hot-water temperatures, Wi-Fi signal,
  remaining heating time, available showers, energy consumption (gas and electricity, heating and hot
  water, running totals and last-month figures), error count.
- **Binary sensors**: flame, heat pump running, zone heat request, holiday mode, heating, anti-legionella
  cycle, and a **Problem** sensor that turns on when the appliance reports a fault.
- **Controls**: system mode, hybrid mode, buffer control, automatic thermoregulation, quiet mode, eco mode,
  boost, anti-legionella, night mode with start/end time, flow temperature and offset per zone, setpoint
  limits, energy prices.
- **Services** to start a vacation and to write raw properties.
- **Diagnostics download** (credentials and identifiers redacted) to attach to bug reports.
- Automatic **re-authentication** prompt when the cloud rejects the stored password.

## Supported devices

| Family | Ariston `system type` | Examples | Entities |
| --- | --- | --- | --- |
| Boilers and hybrid / heat-pump systems with the Cube / Sensys gateway | GALEVO | Alteas One, Genus One, Clas One, Nimbus, Alteas Net | climate per zone, water heater, pressure and temperature sensors, energy, system mode, holiday |
| BSB gateways | BSB | Elco, ATAG with BSB bus | climate per zone, water heater, outside temperature, flame |
| Velis water heaters | VELIS | Velis Evo, Evo2, Lux, Lux2, Lydos, Lydos Hybrid, Nuos Split (sold as **Primos 205 / ARIHPWH-200** in Australia), Andris2 | water heater, water temperature, showers, remaining time, eco / boost / anti-legionella, night mode |

Tested by the community on: Alteas One 24, Velis Evo, Velis Lux, Lydos Hybrid, Nuos Split / Primos 205 (ARIHPWH-200).
If your device is missing an entity the app shows, open an issue and attach the diagnostics file.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JoeFu&repository=Ariston-NET-for-HA-Primos-Heat-Pump&category=integration)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/JoeFu/Ariston-NET-for-HA-Primos-Heat-Pump` with category *Integration*.
2. Search **Ariston NET for HA - Primos Heat Pump** → Download.
3. Restart Home Assistant.

### Manual

Copy `custom_components/ariston` into `<config>/custom_components/` and restart Home Assistant.

Requires Home Assistant **2025.1** or newer.

## Configuration

1. Settings → Devices & services → **Add integration** → *Ariston NET*.
2. Enter the e-mail and password of your Ariston NET account.
   The *API URL* and *user agent* fields only appear when
   [advanced mode](https://www.home-assistant.io/blog/2019/07/17/release-96/#advanced-mode) is on; leave
   them alone unless the cloud rejects the defaults.
3. If the account has several devices, pick one. Repeat the setup to add the others; each device is its
   own integration entry.

### Options

Open the entry → **Configure** to change how often the cloud is polled:

| Option | Default | What it refreshes |
| --- | --- | --- |
| Device state | 180 s | temperatures, modes, switches, setpoints |
| Energy consumption | 60 min | consumption totals and last-month figures (the cloud updates hourly) |
| Error list | 600 s | the fault list behind the Problem sensor |

Ariston throttles aggressive polling; the lower bounds in the form keep you on the safe side.

## Entities

Entity names are `<device name> <function>`; the device name is the plant name from the Ariston app.
On multi-zone systems climate and per-zone entities use the zone names from the app.

<details>
<summary>Boilers / heat pumps (GALEVO)</summary>

| Entity | Type | Notes |
| --- | --- | --- |
| *Zone name* | climate | one per zone; presets = system mode |
| *Device* | water_heater | when the system has domestic hot water |
| Heating circuit pressure | sensor | |
| Heating flow setpoint / flow / return temperature | sensor | |
| Outside temperature | sensor | when an outdoor probe is installed |
| Hot water temperature | sensor | |
| *Zone* economy temperature | sensor (diagnostic) | per zone |
| Signal strength | sensor (diagnostic) | gateway Wi-Fi |
| Flame, Heat pump | binary_sensor | |
| *Zone* heat request | binary_sensor | per zone |
| Holiday mode | binary_sensor | attribute: end date |
| Problem, Error count | binary_sensor / sensor | attribute: error list |
| System mode | select | Summer / Winter / Heating only / Off … |
| Hybrid mode, Buffer control mode | select | hybrid systems |
| Automatic thermoregulation, Quiet mode | switch | |
| *Zone* heating flow temperature / offset | number | per zone |
| Heating energy, Hot water energy, Heating gas, … | sensor (energy) | with metering; usable in the Energy dashboard |
| Gas / electricity last month | sensor | with metering |
| Electricity cost, Gas cost, Currency, Gas type, Gas energy unit | number / select | metering settings |
</details>

<details>
<summary>Velis water heaters</summary>

| Entity | Type | Models |
| --- | --- | --- |
| *Device* | water_heater | all except Velis Evo (which uses the Operation mode select) |
| Water temperature | sensor | all |
| Requested temperature in progress | sensor (diagnostic) | all except Evo |
| Available showers | sensor | Evo, Evo2, Lux, Lux2, Lydos, Lydos Hybrid, Andris2 |
| Remaining heating time | sensor | Evo, Evo2, Lux, Lux2, Lydos |
| Heating rate | sensor | Nuos Split |
| Heating, Anti-legionella cycle | binary_sensor | |
| Problem, Error count | binary_sensor / sensor | all |
| Power, Eco mode, Anti-legionella, Power option | switch | |
| Boost, Preheating | switch | Nuos Split |
| Permanent boost, Anti-cooling, Night mode | switch | Lydos Hybrid |
| Night mode start / end | time | Lydos Hybrid |
| Maximum / minimum setpoint temperature, Reduced temperature | number | |
| Maximum green mode temperature | number | Nuos Split (installer parameter "T MAX HP") |
| Requested showers | number | Evo |
| Anti-cooling temperature | number | Lydos Hybrid |
| Operation mode | select | Evo |
</details>

## Services

| Service | Description |
| --- | --- |
| `ariston.create_vacation` | Put a GALEVO system on holiday until `end_date`; omit the date to cancel. |
| `ariston.set_item_by_id` | Write a raw device / thermostat property (`item_id`, `zone`, `value`). Advanced. |

Both take the Home Assistant **device** as target and are documented in Developer tools → Actions.

## Examples

Lower the hot water setpoint at night and raise it in the morning:

```yaml
automation:
  - alias: Hot water night setback
    triggers:
      - trigger: time
        at: "23:00:00"
    actions:
      - action: water_heater.set_temperature
        target:
          entity_id: water_heater.boiler
        data:
          temperature: 45
```

Notify when the appliance reports a fault:

```yaml
automation:
  - alias: Boiler fault
    triggers:
      - trigger: state
        entity_id: binary_sensor.boiler_problem
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: Boiler fault
          message: "{{ state_attr('binary_sensor.boiler_problem', 'errors') }}"
```

Energy dashboard: add *Heating gas* / *Heating electricity* / *Hot water …* sensors as gas and
electricity sources.

## Troubleshooting

**Download diagnostics first.** Settings → Devices & services → Ariston NET → ⋮ → *Download diagnostics*.
The file contains the raw cloud data with your credentials, gateway id, serial number and location removed;
attach it to issues.

| Symptom | What to check |
| --- | --- |
| "Re-authentication required" | You changed the Ariston NET password. Click the notification and enter it. |
| Entities unavailable | The cloud did not answer; the integration retries at the next poll. Check the Ariston NET app works. |
| A value is stale | The cloud itself updates energy figures hourly and state every few minutes. |
| Missing entity | The device does not report that feature. Open an issue with diagnostics. |

Debug logging:

```yaml
logger:
  logs:
    custom_components.ariston: debug
    ariston: debug
```

## What changed in 1.2

- Water heater modes are shown with readable, translated names (Green, Comfort, Boost, i-Memory;
  绿色节能 / 舒适 / 快速加热 / i-Memory 智能 in Chinese). To make that possible the state values of Velis
  modes are now lowercase (`green`, `comfort`, `fast`, `imemory`, `off`). Automations that compare the state or call
  `water_heater.set_operation_mode` must use the lowercase spelling.
- Simplified Chinese translation of the whole integration (`translations/zh-Hans.json`).
- The Primos 205 (ARIHPWH-200) is named as such on the device page.

## What changed in 1.1

- Velis water heaters: **off** is an operation mode, so the mode picker can switch the heater off and
  back on; selecting a mode while off powers the heater on.
- Per-mode setpoint limits from the Ariston manual: GREEN is capped by the heat-pump ceiling reported
  by the cloud (SlpMaxGreenTemperature), i-Memory has a 50 °C floor, COMFORT / BOOST use the installer
  limits. Switching mode adjusts an out-of-range target first; the limits are exposed in the
  `temperature_limits` attribute.
- New number entity *Maximum green mode temperature* (Nuos Split).

## What changed in 1.0

- Entity names follow Home Assistant conventions (`has_entity_name`) and can be translated.
  Unique IDs are unchanged, so nothing has to be renamed.
- New entities: hot water temperature (boilers), water temperature on every Velis model, zone heat request,
  zone economy temperature, system mode select, Problem sensor, night mode start/end (Lydos Hybrid).
- Energy sensors are no longer hidden in the Diagnostic section and can be used in the Energy dashboard.
- Cloud errors mark entities unavailable instead of failing silently; rejected credentials trigger
  re-authentication.
- Config flow: advanced fields hidden by default, device picker, proper error messages, dedicated
  re-authentication step. Options show units and explanations.
- Diagnostics download, services registered once with validated errors, Home Assistant 2025.1+ only.

## Contributing

- Run `ruff check custom_components` and `pytest` before opening a pull request
  (`pip install -r requirements_dev.txt`).
- New entities only need an entry in the platform's `*_TYPES` tuple plus a translation in
  `strings.json` / `translations/en.json`; the tests check that both are present.
- Translations: copy `translations/en.json` to your language code and translate the values.

## Credits

This project started as a fork of [fustom/ariston-remotethermo-home-assistant-v3](https://github.com/fustom/ariston-remotethermo-home-assistant-v3),
which did the API reverse engineering and maintains the `ariston` Python package. That work was inspired by
[chomupashchuk's v2 integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2).
The user-facing structure of this version takes cues from
[0xAHA/Midea-Heat-Pump-HA](https://github.com/0xAHA/Midea-Heat-Pump-HA).

## License

MIT, see [LICENSE](LICENSE).
