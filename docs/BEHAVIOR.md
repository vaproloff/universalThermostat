# How Universal Thermostat Works

This guide explains the runtime behavior of Universal Thermostat in practical terms. It is meant for users who want to understand what the thermostat will do, without reading the full YAML reference.

For installation and quick start, see the main [README](../README.md). For every configuration option, see [Advanced Configuration](./ADVANCED.md).

## Mental Model

Universal Thermostat creates one Home Assistant `climate` entity from one temperature sensor and one or more heater/cooler controllers.

The thermostat decides which controllers are allowed to work in the current HVAC mode. Each controller then decides what to do with its own target entity.

A controller being active inside Universal Thermostat does not always mean the physical device is currently heating or cooling. For example, an ON/OFF heater controller can be allowed to run, but it will only turn the heater on when the room is cold enough.

## HVAC Modes

Available modes depend on configured devices. If only heaters are configured, cooling modes are not available. If both heaters and coolers are configured, Universal Thermostat can expose `heat`, `cool`, `heat_cool`, and `auto`.

| Mode | Active controller groups | Thermostat target model |
|------|--------------------------|--------------------------|
| `heat` | Heaters only | One target: `target_temp` |
| `cool` | Coolers only | One target: `target_temp` |
| `heat_cool` | Heaters and coolers | Range: `target_temp_low` / `target_temp_high` |
| `auto` | Heaters and coolers | One center target plus deltas |

## Target Temperatures

In `heat` and `cool`, the thermostat uses a single target temperature:

```text
target_temp
```

In `heat_cool`, the thermostat uses a range:

```text
heater target = target_temp_low
cooler target = target_temp_high
```

In `auto`, the thermostat still shows one target temperature, but internally treats it as the center of a comfort band:

```text
heater target = target_temp - auto_heat_delta
cooler target = target_temp + auto_cool_delta
```

With `target_temp = 25`, `auto_heat_delta = 1`, and `auto_cool_delta = 1`, heaters work around `24` and coolers work around `26`.

## Auto vs Heat/Cool

`heat_cool` exposes the comfort band directly. You set the low and high temperatures yourself.

`auto` exposes the center of the comfort band. The low and high control points are calculated from the center target and the configured deltas.

Use `heat_cool` when you want to set the lower and upper limits directly. Use `auto` when you prefer to set a comfort point and keep heating/cooling separation controlled by deltas.

## Switching Modes

When switching modes, Universal Thermostat tries to preserve the effective heating or cooling boundary instead of blindly keeping the displayed target value.

Examples with `auto_heat_delta = 1` and `auto_cool_delta = 1`:

| Switch | Result |
|--------|--------|
| `heat 24 -> auto` | `target_temp` becomes `25`; heater target stays `24`, cooler target becomes `26` |
| `cool 24 -> auto` | `target_temp` becomes `23`; cooler target stays `24`, heater target becomes `22` |
| `auto 25 -> heat` | `target_temp` becomes `24` |
| `auto 25 -> cool` | `target_temp` becomes `26` |
| `heat_cool low=24 high=26 -> auto` | `target_temp` becomes `25` |
| `heat_cool -> heat` | `target_temp` becomes `target_temp_low` |
| `heat_cool -> cool` | `target_temp` becomes `target_temp_high` |

Direct `heat -> cool` and `cool -> heat` switches keep the current `target_temp` unchanged.

If the thermostat is switched from `off` to `heat_cool`, it uses the last active HVAC mode as context when possible. If there is no useful previous mode, it calculates the range from the current `target_temp` as if switching from `auto`.

## Controller Behavior

Controller type defines how the target is applied to a real entity.

ON/OFF controllers use hysteresis. A heater turns on when the current temperature is below its target minus cold tolerance. A cooler turns on when the current temperature is above its target plus hot tolerance.

Climate controllers call climate services on the target entity. In switch-like mode, they work with hysteresis. In PID mode, they continuously adjust the target climate setpoint.

PWM switch controllers use PID output as a duty cycle. For example, `30%` means the switch should be on for about 30 percent of the PWM period.

Number controllers use PID output to set a numeric entity, optionally with a separate switch entity to enable or disable the device.

## Windows

Window entities pause controllers when a window is considered open. A controller with `ignore_windows` keeps working even when windows are open.

Window timeouts delay the stop/start reaction. This is useful to avoid short accidental openings immediately affecting climate control.

## Presets

Presets can adjust target temperatures, change HVAC mode, or tune auto-mode heating/cooling targets.

When a preset is active and the HVAC mode is changed manually, Universal Thermostat resets the preset to `None`. When returning to `None`, the thermostat restores the saved non-preset state when possible.

## Where To Go Next

Use the UI options for normal setup. Use [Advanced Configuration](./ADVANCED.md) when you need YAML, templates, PID tuning, PWM setup, or detailed controller options.
