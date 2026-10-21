---
name: Bug report
about: Something does not work as described in the README
title: "[BUG] "
labels: bug
assignees: fustom

---

Please check the [wiki](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/wiki) and existing
issues (including closed ones) first.

**Describe the bug**
What happens, and what you expected instead.

**Diagnostics file**
Settings → Devices & services → Ariston NET → ⋮ → *Download diagnostics*, then drag the file here.
It contains the raw cloud data with your credentials, gateway id, serial number and location removed.
Most device-specific bugs cannot be fixed without it.

**Environment**
 - Home Assistant version:
 - Integration version (HACS → Ariston NET):
 - Device type shown on the device page (e.g. `GALEVO`, `VELIS LydosHybrid`, `VELIS Evo2 | Model 4`):

**Debug log** (optional)
```yaml
logger:
  logs:
    custom_components.ariston: debug
    ariston: debug
```
