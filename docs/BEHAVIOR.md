# How Universal Thermostat Works

This guide explains the runtime behavior of Universal Thermostat in practical
terms. It is meant for users who want to understand what the thermostat will do
after it has been configured, without reading the full YAML reference or the
source code.

For installation and quick start, see the main [README](../README.md). For every
configuration option, see [Advanced Configuration](./ADVANCED.md).

## Mental Model

Universal Thermostat creates one Home Assistant `climate` entity from:

- one temperature sensor
- one or more heater controllers
- one or more cooler controllers
- optional window entities
- optional presets

The thermostat itself does not heat or cool anything directly. It decides which
controllers are allowed to run in the current HVAC mode. Each controller then
decides what to do with its own target entity.

There are two important controller states:

- **running** means Universal Thermostat currently allows the controller to work.
- **active** means the real device is currently doing work, or appears to be
  doing work.

For example, a heater switch controller can be **running** in `heat` mode, but
the physical switch can still be off because the room is already warm enough.

## Control Loop

Universal Thermostat reacts to events instead of polling.

Control is recalculated when:

- Home Assistant starts or the integration is reloaded
- the target temperature sensor changes
- the thermostat HVAC mode changes
- the thermostat target temperature changes
- a configured template value changes
- a window entity changes
- a preset is selected or cleared
- PID or PWM timers fire
- keep-alive timers fire

On each control pass Universal Thermostat:

1. Updates the last active HVAC mode if the current mode is not `off`.
2. Checks whether any configured window should pause controllers.
3. Stops controllers that are no longer allowed to run.
4. Starts controllers that are now allowed to run.
5. Asks each controller to apply its own logic.

If the HVAC mode is `off`, all running controllers are stopped. Once `off` has
already been processed, repeated control passes are skipped until the mode
changes again.

## Available HVAC Modes

Available modes depend on configured controllers.

| Configured controllers | Available modes |
|------------------------|-----------------|
| Heaters only | `off`, `heat` |
| Coolers only | `off`, `cool` |
| Heaters and coolers | `off`, `heat`, `cool`, `auto`, `heat_cool` |

`auto` can be hidden with `auto_mode_disabled`. `heat_cool` can be hidden with
`heat_cool_disabled`.

## What Each HVAC Mode Does

| Mode | Running controller groups | Thermostat target model |
|------|---------------------------|--------------------------|
| `off` | none | Keeps stored target values, no control |
| `heat` | heaters only | One target: `target_temp` |
| `cool` | coolers only | One target: `target_temp` |
| `heat_cool` | heaters and coolers | Range: `target_temp_low` / `target_temp_high` |
| `auto` | heaters and coolers | One center target plus deltas |

The mode decides which controller groups are allowed to run. It does not mean
their target entities are always physically on.

## Target Temperatures

In `heat` and `cool`, the thermostat uses a single target:

```text
controller target = target_temp
```

In `heat_cool`, the thermostat uses a range:

```text
heater target = target_temp_low
cooler target = target_temp_high
```

In `auto`, the thermostat shows one target temperature, but internally treats it
as the center of a comfort band:

```text
heater target = target_temp - auto_heat_delta
cooler target = target_temp + auto_cool_delta
```

Example:

```text
target_temp = 25
auto_heat_delta = 1
auto_cool_delta = 1

heater target = 24
cooler target = 26
```

This makes `auto` different from `heat_cool`:

- `heat_cool` exposes both boundaries directly.
- `auto` exposes the center point and calculates the boundaries.

## Switching Modes

When switching modes, Universal Thermostat tries to preserve the effective
heating or cooling boundary instead of blindly keeping the displayed target
value.

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
| `heat 24 -> heat_cool` | low target becomes `24`, high target becomes `25` |
| `cool 24 -> heat_cool` | high target becomes `24`, low target becomes `23` |

Direct `heat -> cool` and `cool -> heat` switches keep the current `target_temp`
unchanged.

If the thermostat is switched from `off` to another mode, it uses the last active
HVAC mode as context when possible. This helps `turn_on` restore the previous
operating mode.

## Temperature Rounding

When Universal Thermostat calculates a target temperature, it rounds it to the
configured `target_temp_step` if one is set. If no explicit step is set, Home
Assistant precision is used for the displayed target step.

Controllers can also round outputs to the target entity's own step:

- climate target temperatures use the target climate entity's
  `target_temp_step` when available
- number outputs use the number entity's `step` when available
- PWM output is always rounded to an integer percent

## Startup And Restore

Universal Thermostat restores its previous state when Home Assistant provides
one.

On startup it restores, when available:

- HVAC mode
- single target temperature
- low and high target temperatures
- last active HVAC mode
- last control mode
- preset mode and preset saved state
- controller attributes used by some controllers, such as PWM state

If no previous target temperatures are available:

- `target_temp` falls back to `min_temp`
- `target_temp_low` falls back to `min_temp`
- `target_temp_high` falls back to `max_temp`

If no HVAC mode is restored or configured with `initial_hvac_mode`, the
thermostat starts in `off`.

## Sensor Behavior

The configured temperature sensor is the current room temperature source.

When the sensor changes to a normal numeric value, Universal Thermostat converts
it to a float and runs control.

If the sensor state is `unknown` or `unavailable`, that update is ignored and no
new control pass is run from that event. If a value cannot be converted to a
valid finite number, the current temperature is cleared; running controllers then
skip temperature-based control until a valid value is available again.

## HVAC Action

The thermostat reports `hvac_action` from controller activity:

- `off` when the thermostat HVAC mode is `off`
- `heating` if any active heater controller reports active
- `cooling` if any active cooler controller reports active
- `idle` otherwise

For climate target entities, Universal Thermostat prefers the target entity's
`hvac_action` attribute when it is available. Otherwise it falls back to the
target entity state or switch state.

## Controller Selection

The configured entity domain decides which controller implementation is used.

| Entity domain | Without PID config | With PID config |
|---------------|--------------------|-----------------|
| `switch` / `input_boolean` | ON/OFF switch controller | PWM switch PID controller |
| `climate` | Climate switch controller | Climate PID controller |
| `number` / `input_number` | not used | Number PID controller |

The same physical entity can be configured as both a heater and a cooler. This
is useful for devices such as A/C units that support both heating and cooling.

## Shared Controller Behavior

All controllers share these rules:

- A controller can run only when its group is allowed by the current HVAC mode.
- A controller is stopped when it becomes disallowed.
- A controller is stopped when a window is open, unless `ignore_windows` is set.
- A controller that is not running tries to ensure its target entity is off.
- `keep_alive` repeats the last relevant command on a timer.
- `inverted` reverses on/off meaning for supported controller types.

Controllers receive one target temperature from the thermostat. The target is
chosen by HVAC mode as described above.

## ON/OFF Switch Controllers

Used for `switch` and `input_boolean` entities without PID config.

This controller uses hysteresis with `cold_tolerance` and `hot_tolerance`.

For a heater:

```text
turn on  when current_temp <= target_temp - cold_tolerance
turn off when current_temp >= target_temp + hot_tolerance
```

For a cooler:

```text
turn on  when current_temp >= target_temp + hot_tolerance
turn off when current_temp <= target_temp - cold_tolerance
```

Example heater:

```text
target_temp = 21
cold_tolerance = 0.3
hot_tolerance = 0.3

turn on at 20.7 or below
turn off at 21.3 or above
```

Example cooler:

```text
target_temp = 24
cold_tolerance = 0.3
hot_tolerance = 0.3

turn on at 24.3 or above
turn off at 23.7 or below
```

If `min_cycle_duration` is configured, the controller will not change the
physical switch state until the current state has lasted long enough. Forced
control passes, such as HVAC mode changes or target temperature changes, bypass
this cycle protection.

If `inverted` is enabled, `turn_on` and `turn_off` service calls are swapped.

## Climate Switch Controllers

Used for `climate` entities without PID config.

A climate switch controller behaves like an ON/OFF controller, but instead of
toggling a switch it changes the target climate entity's HVAC mode:

- heater controller starts by setting the target climate entity to `heat`
- cooler controller starts by setting the target climate entity to `cool`
- stopping calls `climate.turn_off`

If `target_temp_delta` is configured, Universal Thermostat also sends a target
temperature to the climate entity:

```text
heater climate setpoint = controller target + target_temp_delta
cooler climate setpoint = controller target - target_temp_delta
```

The resulting setpoint is clamped to the target climate entity's min/max
temperature when those attributes are available, then rounded to the target
climate entity's supported step.

This is useful when the controlled climate device has its own internal
thermostat and needs a slightly more aggressive setpoint than the Universal
Thermostat boundary.

## PID Controllers

PID controllers calculate an output from the difference between current
temperature and target temperature.

PID is recalculated when:

- the target sensor changes
- the thermostat target changes
- the HVAC mode changes
- a preset changes
- a relevant template changes
- a window change causes control
- the optional `pid_sample_period` timer fires
- a forced control pass runs

If `pid_sample_period` is configured, PID also runs on that fixed interval. If it
is not configured, PID behaves more dynamically and recalculates on relevant
events.

`kp`, `ki`, and `kd` can be templates. When their rendered values change:

- changing `kp` updates the proportional gain
- changing `ki` updates the integral gain and resets PID
- changing `kd` updates the derivative gain and resets PID

When the target setpoint changes, PID is reset.

For cooler controllers, PID gains are internally inverted. If `inverted` is set,
they are inverted again. This lets the same PID parameters work with heating and
cooling semantics.

## PWM Switch PID Controllers

Used for `switch` and `input_boolean` entities with PID config.

The PID output range is `0..100`. The output is interpreted as a duty cycle over
the configured `pwm_period`.

Example:

```text
pwm_period = 10 minutes
PID output = 30

switch on  for about 3 minutes
switch off for about 7 minutes
```

Universal Thermostat checks PWM state regularly. The check period is
`pwm_period / 100`, but never less than one second.

The controller stores its last PWM value, last PWM state, and last control time
in thermostat attributes so it can continue reasonably after a restart.

When stopped, it turns the switch off. If `inverted` is enabled, on/off service
calls are swapped.

## Climate PID Controllers

Used for `climate` entities with PID config.

The PID output is adapted into a target setpoint for the climate entity:

```text
climate setpoint = min + PID_output_percent * (max - min) / 100
```

For heater controllers, output limits are `min -> max`. For cooler controllers,
they are reversed so stronger cooling moves the setpoint in the cooling
direction.

The `min` and `max` config values limit the PID output range. If they are not
configured, Universal Thermostat uses the target climate entity's `min_temp` and
`max_temp` attributes when available, with the thermostat min/max as fallback.

The final setpoint is rounded to the target climate entity's supported
temperature step.

The controller also ensures the target climate entity is in the correct HVAC
mode (`heat` or `cool`) while it is running, and calls `climate.turn_off` when it
stops.

## Number PID Controllers

Used for `number` and `input_number` entities.

The PID output is adapted into the configured number range:

```text
number value = min + PID_output_percent * (max - min) / 100
```

For heater controllers, output limits are `min -> max`. For cooler controllers,
they are reversed.

If `min` or `max` are not configured, Universal Thermostat uses the number
entity's own `min` and `max` attributes when available, with the thermostat
min/max as fallback.

The final value is rounded to the number entity's `step` attribute when
available.

An optional `switch_entity_id` can be used together with the number output. When
configured, Universal Thermostat turns the switch on while the controller is
running and turns it off when the controller stops. `switch_inverted` reverses
that switch logic.

If no optional switch is configured, the controller's running state is treated as
its on/off state.

## Windows

Window entities pause controllers when any configured window is considered open.

Supported window-like domains are:

- `binary_sensor`
- `input_boolean`
- `switch`

By default, a window is open when its state is `on`. If `inverted` is enabled,
the window is open when its state is `off`.

When a window is open:

- running controllers are stopped
- stopped controllers are not started
- controllers with `ignore_windows` keep running

If a window has no `timeout`, it affects control immediately.

If a window has a `timeout`, the timeout is applied both when opening and when
closing:

- when it opens, controllers pause only after it has stayed open for the timeout
- when it closes, controllers resume only after it has stayed closed for the
  timeout

This avoids reacting to very short openings and avoids immediately restarting
devices after a window closes.

On first startup control, Universal Thermostat uses the current window state
without waiting for the safe timeout check.

## Presets

Presets temporarily change the thermostat's HVAC mode and/or target
temperatures.

When a preset is selected from `none`, Universal Thermostat saves the current
non-preset state:

- HVAC mode
- `target_temp`
- `target_temp_low`
- `target_temp_high`

When the preset is changed back to `none`, Universal Thermostat restores that
saved state when possible.

If the HVAC mode is changed manually while a preset is active, the preset is
reset to `none` and the saved preset state is cleared.

### Preset Priority

Preset fields are applied in a specific order.

For single target modes (`heat`, `cool`, `auto`):

1. `temp_delta` shifts the current target and keeps the HVAC mode.
2. `heat_delta` applies in `heat`.
3. `cool_delta` applies in `cool`.
4. `heat_target_temp` applies in `heat`.
5. `cool_target_temp` applies in `cool`.
6. In `auto`, if both `heat_target_temp` and `cool_target_temp` are set, the
   displayed center target is left unchanged and the fixed heating/cooling
   targets are used internally.
7. `target_temp` is used as a fallback fixed target.

For `heat_cool` range mode:

- `temp_delta` shifts both low and high targets.
- `heat_delta` shifts the low target.
- `cool_delta` shifts the high target.
- `heat_target_temp` sets the low target.
- `cool_target_temp` sets the high target.
- `target_temp` sets both low and high targets if more specific fields are not
  present.

### Presets And HVAC Mode Changes

A target-temperature preset can also change HVAC mode in some cases.

If only `cool_target_temp` is configured and the thermostat is in a heating or
ranged mode, the preset can switch to `cool`.

If only `heat_target_temp` is configured and the thermostat is in a cooling or
ranged mode, the preset can switch to `heat`.

If both heating and cooling target temperatures are configured, `auto` and
`heat_cool` can stay in their current mode.

`temp_delta`, paired `heat_delta`/`cool_delta`, and `target_temp` presets do not
change HVAC mode by themselves.

### Presets In Auto Mode

In `auto`, controller targets are normally:

```text
heater target = target_temp - auto_heat_delta
cooler target = target_temp + auto_cool_delta
```

Preset `heat_delta` and `cool_delta` adjust those calculated targets:

```text
heater target = target_temp - auto_heat_delta + heat_delta
cooler target = target_temp + auto_cool_delta + cool_delta
```

If both `heat_target_temp` and `cool_target_temp` are configured, those fixed
targets override the calculated auto targets:

```text
heater target = heat_target_temp
cooler target = cool_target_temp
```

If only one fixed target is configured, it is not used as an internal auto target
pair; instead, the preset may switch HVAC mode as described above.

## Templates

Many advanced values can be templates, including:

- `auto_heat_delta`
- `auto_cool_delta`
- tolerances
- PID gains
- PID min/max limits
- climate `target_temp_delta`
- window timeouts
- preset values

When Universal Thermostat can identify entities used by a template, it listens
for those entity changes and runs control again.

If a rendered template value cannot be converted to the expected type,
Universal Thermostat logs a warning and falls back to the configured default or
skips the affected value, depending on the field.

## Extra Attributes

Universal Thermostat exposes extra attributes that can help with debugging:

- rendered `auto_cool_delta` and `auto_heat_delta`
- per-controller attributes under keys like `heater_<entity_object_id>` and
  `cooler_<entity_object_id>`
- last processed control HVAC mode
- last active HVAC mode
- saved preset state while a preset is active

PID and PWM controllers expose additional values such as PID gains, output
limits, PWM value, and last PWM control state.

## Common Scenarios

### I changed target temperature, but the switch did not move

For ON/OFF controllers this is normal if the current temperature is still inside
the hysteresis band, or if `min_cycle_duration` is preventing a rapid state
change.

### The controller is running, but the device is off

This is normal. `running` means the controller is allowed to work. The controller
can still decide that no physical heating or cooling is needed right now.

### A window closed, but heating did not resume immediately

If the window has a timeout, Universal Thermostat waits until it has remained
closed for that timeout before resuming controllers.

### I selected a preset and the HVAC mode changed

This can happen with fixed target temperature presets. For example, if only a
cooling target is defined, the preset can switch the thermostat to `cool`.

### I changed HVAC mode and my preset disappeared

This is expected. Manual HVAC mode changes reset the active preset to `none`.

## Where To Go Next

Use the UI options for normal setup. Use [Advanced Configuration](./ADVANCED.md)
when you need YAML, templates, PID tuning, PWM setup, or detailed controller
options.
