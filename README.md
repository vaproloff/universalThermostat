# Universal Thermostat component for Home Assistant

[![HACS validation](https://github.com/vaproloff/universalThermostat/actions/workflows/hacs.yaml/badge.svg)](https://github.com/vaproloff/universalThermostat/actions/workflows/hacs.yaml)
[![Hassfest](https://github.com/vaproloff/universalThermostat/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/vaproloff/universalThermostat/actions/workflows/hassfest.yaml)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue)
![Version](https://img.shields.io/badge/version-2026.5.2-blue)
![HACS](https://img.shields.io/badge/HACS-Custom-orange)
[![GitHub stars](https://img.shields.io/github/stars/vaproloff/universalThermostat?style=social)](https://github.com/vaproloff/universalThermostat/stargazers)

Universal Thermostat is an advanced climate controller for Home Assistant that combines multiple heating and cooling devices into a single smart thermostat.

Built for real-world smart homes where different climate systems must work together seamlessly.

## ✨ Features

- 🔥 Combine multiple heaters and coolers into one thermostat
- 🎯 Advanced control: PID and PWM
- 🧠 Smart HVAC modes: auto, heat/cool
- 🪟 Window-aware logic with delays
- 🎛 Flexible preset system (eco, away, sleep, etc.)
- ⚙️ Easy setup via UI (config flow)
- 🧩 YAML support for advanced setups
- 🔄 Template support for dynamic configuration

## 🧠 Why this integration exists

Home Assistant does not provide a flexible way to combine multiple climate devices into a single thermostat.

This integration solves real-world tasks:
- combining floor heating + radiators + AC
- controlling multiple devices in one zone
- preventing heating/cooling when windows are open
- achieving precise temperature control using PID

## 🚀 Installation

### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if not installed yet
2. Go to **HACS → Integrations**
3. Open menu (⋮) → **Custom repositories**
4. Add repository:
   `https://github.com/vaproloff/universalThermostat`
5. Find **Universal Thermostat** and click **Install**
6. Restart Home Assistant

### Manual

1. Copy folder:
   `/custom_components/universal_thermostat`
   into your Home Assistant config:
   `<config_dir>/custom_components/universal_thermostat` directory.
2. Restart Home Assistant

## ⚡ Quick start (UI)

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **Universal Thermostat** and choose it
4. Complete basic setup:
   - set friendly name
   - choose temperature sensor
5. Then go to integration entry options (⚙️), where you can
   - configure heaters and/or coolers
   - configure windows and presets
   - configure settings

👉 No YAML required for basic usage

## ⚠️ Configuration modes

This integration supports two configuration methods:

- ✅ UI (recommended) – easy setup via Home Assistant interface
- ⚙️ YAML – for advanced configurations and full control

Most users should use the UI setup.

#### Simple YAML example:
```yaml
climate:
  - platform: universal_thermostat
    name: Living Room
    target_sensor: sensor.room_temperature
    heater:
      - entity_id: switch.heater
    cooler:
      - entity_id: climate.ac
```

## 🔧 Example use cases

- Combine floor heating + AC into one thermostat
- Control multiple heaters in large rooms
- Stop HVAC when windows are open
- Fine-tune temperature with PID control
- Use presets like eco / away / sleep

## ⚙️ Supported domains:

- `switch`, `input_boolean` - basic toggling mode or PWM mode
- `climate` - basic toggling mode or PID regulator mode
- `number`, `input_number` – PID control (optionally with `switch`)

👉 See full details: [Advanced Configuration](./docs/ADVANCED.md)

## 🪟 Window support

Optionally link window sensors (or similar entities) to pause heating/cooling.

Features:
- multiple windows
- optional delays
- per-controller ignore option

👉 See configuration examples: [Advanced Configuration](./docs/ADVANCED.md)

## 🎛 Presets

Flexible preset system (eco, away, sleep, etc.):
- temperature adjustments
- HVAC mode changes
- auto mode tuning

👉 See full configuration: [Advanced Configuration](./docs/ADVANCED.md)

## 🔥 HVAC Modes

Supports:
- `heat`
- `cool`
- `heat_cool`
- `auto`

Behavior adapts automatically based on configured devices.

Learn how modes, target temperatures, and controllers behave: [Behavior Guide](./docs/BEHAVIOR.md)

👉 Details: [Advanced Configuration](./docs/ADVANCED.md)

## 📚 Advanced Configuration

Full YAML configuration with all options:
👉 See: [docs/ADVANCED.md](./docs/ADVANCED.md)

## 🐞 Debugging

If something doesn't work as expected, enable debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.universal_thermostat: debug
```

Then reproduce the issue and check Home Assistant logs.

## 💬 Support / Issues

If you find a bug:
1. Enable debug logs
2. Reproduce issue
3. Create GitHub issue with logs
