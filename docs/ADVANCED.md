# Universal Thermostat - Advanced configuration

This document describes advanced configuration options for Universal Thermostat.

👉 If you're new — start with the main README first.

For a user-friendly explanation of runtime behavior, see [Behavior Guide](./BEHAVIOR.md).

## Supported Devices & Control Modes

Universal Thermostat supports multiple device types with different control strategies.

| Domain            | Control modes        |
|-------------------|----------------------|
| `switch`          | ON/OFF, PWM (PID)    |
| `input_boolean`   | ON/OFF, PWM (PID)    |
| `climate`         | ON/OFF, PID          |
| `number`          | PID                  |
| `input_number`    | PID                  |

## Controller types

Depending on entity domain and configuration, one of the following controllers will be created.

### Switch Controller (ON/OFF)

Simple hysteresis-based control.
- turns ON/OFF based on temperature thresholds
- supports cycle protection
- can be inverted

### PID PWM Switch Controller

- PID calculates output (0–100%)
- output is translated into ON/OFF cycles
- useful for:
  - electric heaters
  - valves
  - relays

### Climate Controller

- acts like ON/OFF
- optionally adjusts target temperature using delta

### PID Climate Controller

- continuously adjusts climate setpoint
- uses PID regulation

### Number Controller (PID)

- controls numeric entities (`number`, `input_number`)
- optional switch to enable/disable device
- ideal for:
  - analog valves
  - dimmers
  - power regulators

## HVAC Modes

Available modes depend on configured devices.

### `heat`

- only heaters are active
- coolers are disabled

### `cool`

- only coolers are active
- heaters are disabled

### `heat_cool`

- both heaters and coolers are active
- uses:
  - `target_temp_low` → heaters
  - `target_temp_high` → coolers

### `auto`

- both heaters and coolers are active
- dynamic targets:
    ```
    heater_target_temp = thermostat_target_temp - auto_heat_delta
    cooler_target_temp = thermostat_target_temp + auto_cool_delta
    ```

## Full config example

```yaml
climate:
  - platform: universal_thermostat
    name: Kitchen Thermostat
    unique_id: kitchen_thermostat
    object_id: kitchen_thermostat
    target_sensor: sensor.kitchen_temperature
    min_temp: 18
    max_temp: 28
    precision: 0.1
    target_temp_step: 0.5
    target_temp: 24.5
    target_temp_low: 24
    target_temp_high: 25
    auto_cool_delta: "{{ states('input_number.auto_cool_delta') | float }}"
    auto_heat_delta: 1.0
    heat_cool_disabled: false
    initial_hvac_mode: heat_cool
    heater:
      - entity_id: climate.kitchen_heating_floor_thermostat
        kp: 1.3
        ki: 0.5
        kd: 10
        pid_sample_period: 300
        min: 16
        max: 35
      - entity_id: switch.kitchen_heater_switch
        inverted: false
        cold_tolerance: 0.3
        hot_tolerance: 0.3
        min_cycle_duration: 600
    cooler:
      - entity_id: number.kitchen_cooler_regulator
        switch_entity_id: switch.kitchen_cooler_regulator_switch
        switch_inverted: true
        kp: 20
        ki: 0.01
        kd: 2
        min: 0
        max: 10
      - entity_id: climate.kitchen_cooler_thermostat
        cold_tolerance: 0.3
        hot_tolerance: 0.3
        target_temp_delta: 1.0
        ignore_windows: true
    windows:
      - entity_id: switch.window_1
        timeout:
          seconds: 2
      - entity_id: input_boolean.window_2
        inverted: true
        timeout: "{{ states('input_number.window_open_timeout') | float }}"
      - binary_sensor.window_3
    presets:
      sleep:
        temp_delta: "{{ states('input_number.sleep_temp_delta') | float }}"
      away:
        heat_delta: -1.0
        cool_delta: 2.0
      eco:
        target_temp: 18.0
        heat_target_temp: 18.0
        cool_target_temp: 29.0
```

## Common config options

* `name` _(Required)_ - Universal Thermostat `climate` entity name.
* `unique_id` _(Optional)_ - Universal Thermostat `climate` entity `unique_id`.
* `object_id` _(Optional)_ - Universal Thermostat `climate` entity suggested `entity_id`.
* `target_sensor` _(Required)_ - Target temperature sensor. Must be with `sensor` domain.
* `cooler` _(Optional)_ - String, Array or Map of the cooler(s).
* `heater` _(Optional)_ - String, Array or Map of the heater(s).
* `min_temp` _(Optional)_ - Set minimum set point available.
* `max_temp` _(Optional)_ - Set maximum set point available.
* `target_temp` _(Optional)_ - Initial target temperature.
* `target_temp_low` _(Optional)_ - Initial target low temperature (for `heat_cool` mode).
* `target_temp_high` _(Optional)_ - Initial target high temperature (for `heat_cool` mode).
* `auto_cool_delta` _(Optional)_ - Target temperature delta for Coolers in `auto` mode. Could be a template. Default: `1.0`.
* `auto_heat_delta` _(Optional)_ - Target temperature delta for Heaters in `auto` mode. Could be a template. Default: `1.0`.
* `heat_cool_disabled` _(Optional)_ - Disables `heat_cool` mode. Default: `false`.
* `auto_mode_disabled` _(Optional)_ - Disables `auto` mode. Default: `false`.
* `initial_hvac_mode` _(Optional)_ - Initial HVAC mode.
* `precision` _(Optional)_ - Precision for this device. Supported values are `0.1`, `0.5` and `1.0`. Default: `0.1` for Celsius and `1.0` for Fahrenheit.
* `target_temp_step` _(Optional)_ - Temperature set point step. Supported values are `0.1`, `0.5` and `1.0`. Default: equals to `precision`.
* `windows` _(Optional)_ - String, Array or Map of the window entities.
* `presets` _(Optional)_ - Map of presets.

_NOTE: at least one of `heater` or `cooler` is required._

## Common behavior

Initial HVAC mode can be set via `initial_hvac_mode` config option.

Thermostat behavior will depend on active HVAC mode. HVAC mode can be set in UI.

### HVAC_MODE = `heat`
_NOTE: available if at least one `heater` was defined._

* All **heater** controllers will be turned on. Specific behavior of each **heater** will depend on the controller type.
* All **cooler** controllers will be turned off.

### HVAC_MODE = `cool`

_NOTE: available if at least one `cooler` was defined._

* All **cooler** controllers will be turned on. Specific behavior of each **cooler** will depend on the controller type.
* All **heater** controllers will be turned off.

### HVAC_MODE = `heat_cool`

_NOTE: available if at least one `heater` and one `cooler` were defined._

* All **cooler** and **heater** controllers will be turned on.
* Specific behavior of each **heater** and **cooler** will depend on the controller type.
* All **cooler** controllers will pick thermostat's `target_temp_high` as their `target_temp`.
* All **heater** controllers will pick thermostat's `target_temp_low` as their `target_temp`.

### HVAC_MODE = `auto`

_NOTE: available if at least one `heater` and  one `cooler` were defined._

* All **cooler** and **heater** controllers will be turned on.
* Specific behavior of each **heater** and **cooler** will depend on the controller type.
* All **cooler** controllers will pick thermostat's `target_temp + auto_cool_delta` as their `target_temp`.
* All **heater** controllers will pick thermostat's `target_temp - auto_heat_delta` as their `target_temp`.

_NOTE: turning on controller **DOES NOT MEANS** turning on `enitity_id` inside controller._
_Controller behavior depends on the **specific controller logic** and described below for each controller._


## Controllers

Specific controller will be created for each `heater`/`cooler` config option based on `enitity_id` domain.

### Switch controller (ON/OFF)

Supported domains: `switch`,`input_boolean`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `ignore_windows` _(Optional)_ - Need to ignore windows logic. Default: `false`.
* `min_cycle_duration` _(Optional)_ - Minimal cycle duration. Used to protect from on/off cycling. Default: `null`.
* `cold_tolerance` _(Optional)_ - Cold tolerance. Could be a template. Default: `0.3`.
* `hot_tolerance` _(Optional)_ - Hot tolerance. Could be a template. Default: `0.3`.

#### Behavior

* Switch entity will be turned on when:
  * `current_temp <= target_temp - cold_tolerance` - for heater,
  * `current_temp >= target_temp + hot_tolerance` - fo cooler.
* Switch entity will be turned off when:
  * `current_temp >= target_temp + hot_tolerance` - for heater,
  * `current_temp <= target_temp - cold_tolerance` - fo cooler.
* No changes will be performed if config `min_cycle_duration` was set and enough time was not passed since last switch.
* Behavior on/off will be inverted if `inverted` config option was set to `true`.

### PWM Switch PID controller

Supported domains: `switch`,`input_boolean`.

* Internal PID limits are integers, defined as constants `PWM_SWITCH_MIN_VALUE` and `PWM_SWITCH_MAX_VALUE` (0, 100).
  So, you must use this limits when tuning `pid_params` terms.

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `ignore_windows` _(Optional)_ - Need to ignore windows logic. Default: `false`.
* `kp` _(Required)_ - PID proportional coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `ki` _(Required)_ - PID integral coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `kd` _(Required)_ - PID derivative coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `pwm_period`  _(Required)_ - PWM period. Switch will be turned on and turned off according internal PID output once in this period.

#### Behavior

* PID output will be calculated internally based on provided PID coefficients.
* `pwm_period` will be separated to two parts: `ON` and `OFF`. Each part duration will depend on PID output.
* PWM on/off need will be checked every `pwm_period/100` time **but not often than each 1 second**. (`PWM_SWITCH_MAX_VALUE` internal const variable)
* Behavior on/off will be inverted if `inverted` config option was set to `true`.
* It is keep on/off state duration before Home Assistant restart. Last change time is saved in thermostat state attributes.

NOTE: This mode will be set if entity domain is one of the listed above and pid parameters config entry is present.

### Climate controller (Switch mode)

Supported domains: `climate`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `ignore_windows` _(Optional)_ - Need to ignore windows logic. Default: `false`.
* `min_cycle_duration` _(Optional)_ - Minimal cycle duration. Used to protect from on/off cycling. Default: `null`.
* `cold_tolerance` _(Optional)_ - Cold tolerance. Could be a template. Default: `0.3`.
* `hot_tolerance` _(Optional)_ - Hot tolerance. Could be a template. Default: `0.3`.
* `target_temp_delta` _(Optional)_ - Delta between Thermostat set point and target climate entity. Could be a template. Default: `0.0`.

#### Behavior

* Climate entity will be turned on when:
  * `current_temp <= target_temp - cold_tolerance` - for heater,
  * `current_temp >= target_temp + hot_tolerance` - fo cooler.
* Climate entity will be turned off when:
  * `current_temp >= target_temp + hot_tolerance` - for heater,
  * `current_temp <= target_temp - cold_tolerance` - fo cooler.
* Climate entity temperature set point will be adjusted taking `target_temp_delta` into account if it specified:
  * thermostat's `target_temp` + `target_temp_delta` - for heaters;
  * thermostat's `target_temp` - `target_temp_delta` - for coolers;

### Climate controller (PID mode)

Supported domains: `climate`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `ignore_windows` _(Optional)_ - Need to ignore windows logic. Default: `false`.
* `kp` _(Required)_ - PID proportional coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `ki` _(Required)_ - PID integral coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `kd` _(Required)_ - PID derivative coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `min` _(Optional)_ - Minimum temperature which can be set. Attribute `min_temp` from `entity_id` will be used if not specified. Could be a template.
* `max` _(Optional)_ - Maximum temperature which can be set. Attribute `max_temp` from `entity_id` will be used if not specified. Could be a template.

#### Behavior

* Climate entity will be turned on when controller is active.
* Climate entity will be turned off when controller is not active.
* Climate `entity_id` temperature will be adjusted every `pid_sample_period` it is provided, or on every `target_sensor` update if `pid_sample_period` is not provided.
* PID parameters will be inverted if `inverted` was set to `true`

### Number + Switch controller (PID mode supported)

Supported domains: `number`,`input_number`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `ignore_windows` _(Optional)_ - Need to ignore windows logic. Default: `false`.
* `kp` _(Required)_ - PID proportional coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `ki` _(Required)_ - PID integral coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `kd` _(Required)_ - PID derivative coefficient. Could be a template (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `min` _(Optional)_ - Minimum temperature which can be set. Attribute `min` from `entity_id` will be used if not specified. Could be a template.
* `max` _(Optional)_ - Maximum temperature which can be set. Attribute `max` from `entity_id` will be used if not specified. Could be a template.
* `switch_entity_id` _(Optional)_ - Switch entity which belongs to `switch`,`input_boolean` domains.
* `switch_inverted` _(Optional)_ - Is `switch_entity_id` inverted? Default: `false`.

#### Behavior

* Switch will be turned on when controller is active if it is set.
* Switch will be turned off when controller is not active if it is set.
* Number entity temperature will be adjusted every `pid_sample_period` it is provided, or on every `target_sensor` update if `pid_sample_period` is not provided.
* PID parameters will be inverted if `inverted` was set to `true`
* `switch_entity_id` behavior will be inverted if `switch_inverted` was set to `true`

## Windows

Windows are optional and their logic will be available if at least one window entity added to the config.

#### Supported window domains:

* `switch`
* `input_boolean`
* `binary_sensor`

#### Simple window entity:
```yaml
windows: binary_sensor.my_window
```

#### Entity list:
```yaml
windows:
  - binary_sensor.my_window
  - input_boolean.heater_block
```

#### Entity map:
```yaml
windows:
  - entity_id: binary_sensor.my_window
    timeout: "{{ states('input_number.window_open_timeout') | float }}"
  - entity_id: input_boolean.heater_can_work
    inverted: true
```

#### Mixed:
```yaml
windows:
  - binary_sensor.my_window_1
  - entity_id: binary_sensor.my_window_2
    timeout:
      minutes: 2
  - entity_id: input_boolean.heater_can_work
    inverted: true
```

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional)_ - Need to invert `entity_id` logic. Default: `false`
* `timeout` _(Optional)_ - time period to wait until stop/start controller after window opening/closing. Can be a template. Default: `none`

#### Common behavior
* after any window entity turns `on`, controller stops working (`off` if `inverted: true`)
* after all window entities turn `off`, controller starts working (`on` if `inverted: true`)
* if controller has `ignore_windows` config option - it doesn't take into account windows states
* if window has a `timeout` config option - it stops/starts controllers after time period mentioned


## Presets

Presets are optional and will be available if at least one preset mode added to the config.
All preset modes are equal in functionality, their behaviour depends only on used config parameters.

Mapping key will be a preset name.
Preset can have any name, but it is recommended to use defaults, that support icons and translations:
* `eco`
* `away`
* `sleep`
* `boost`
* `comfort`
* `home`
* `activity`

#### Common behavior
* if any preset is active, changing `hvac_mode` manually resets current preset to `None`
* if any preset is active, activating `None` `preset_mode` restores thermostat parameters to None-preset state
* if any preset is active, activating another delta `preset_mode` applies all changes relatively to None-preset state
* preset activation can change `hvac_mode` if preset config needs it
* if you want to decrease target temperature, use negative float number.

### Single temperature delta preset config:

#### Config example

```yaml
presets:
  sleep:
    temp_delta: -1.0
```

#### Config options

* `temp_delta` _(Required)_ - single target temperature delta, signed float, can be a template

#### Behavior

* changes thermostat target temperatures (both ranged and non-ranged):
  * `target_temp + temp_delta`
  * `target_temp_low + temp_delta`
  * `target_temp_high + temp_delta`

### Heating/cooling temperature deltas preset config:

#### Config example

```yaml
presets:
  away:
    heat_delta: -1.0
    cool_delta: 2.0
```

#### Config options

* `heat_delta` _(Required)_ - heating target temperature delta, signed float, can be a template
* `cool_delta` _(Required)_ - heating target temperature delta, signed float, can be a template

#### Behavior

* if `hvac_mode` is `COOL` - changes thermostat target temperature:
  * `target_temp + cool_delta`
* if `hvac_mode` is `HEAT` - changes thermostat target temperature:
  * `target_temp + heat_delta`
* if `hvac_mode` is `HEAT_COOL` - changes thermostat target temperature:
  * `target_temp_low + heat_delta`
  * `target_temp_high + cool_delta`
* if `hvac_mode` is `AUTO` - doesn't change thermostat target temperature,
but creates additional deltas to `auto_cool_delta` and `auto_heat_delta` for `controllers`:
  * heaters' `target_temp`s will be `target_temp - auto_heat_delta + heat_delta`
  * coolers' `target_temp`s will be `target_temp + auto_cool_delta + cool_delta`

### Target temperatures preset config:

#### Config example

```yaml
presets:
  eco:
    heat_target_temp: 18.0
    cool_target_temp: 28.0
  comfort:
    target_temp: 25.0
```

#### Config options

* `target_temp` _(Optional)_ - single target temperature, signed float, can be a template
* `heat_target_temp` _(Optional)_ - heating target temperature, signed float, can be a template
* `cool_target_temp` _(Optional)_ - cooling target temperature, signed float, can be a template

#### Behavior

* if `hvac_mode` is `COOL` - changes thermostat target temperature to `cool_target_temp` if available
or to `target_temp`:
* if `hvac_mode` is `HEAT` - changes thermostat target temperature to `heat_target_temp` if available
or to `target_temp`:
* if `hvac_mode` is `HEAT_COOL` - changes thermostat target temperatures:
  * `target_temp_low` will be `heat_target_temp` if available or `target_temp`
  * `target_temp_high` will be `cool_target_temp` if available or `target_temp`
* if `hvac_mode` is `AUTO` and only `target_temp` is available - changes thermostat target temperature to `target_temp`:
* if `hvac_mode` is `AUTO` and `heat_target_temp` and `cool_target_temp` are available -
doesn't change thermostat target temperature, but creates additional target temperatures for `controllers`:
  * heaters' `target_temp`s will be `heat_target_temp`
  * coolers' `target_temp`s will be `cool_target_temp`

NOTE: Any of these config schemas could be used, but not mixed!
