# Universal Thermostat component for Home Assistant

Universal Thermostat is designed to complete almost all climate control tasks in a certain zone.

Component grew out of [Smart Thermostat] from [hacker-cb], who did the great job I am extremely appreciated for!

### Key features:
- supports multiple heating and cooling entities
- supports various target entity domains: `switch`, `climate`, `input_boolean`, `number`, `input_number`
- supports invert logic for any heater or cooler
- supports PID/PWM regulation for supported entities
- supports `auto` mode with adjustable cooling and heating deltas
- supports `heat_cool` mode with separate temperature cooling and heating setpoints
- supports templates for configurable parameters
- supports presets with flexible parameters

### Supported domains and modes for heaters and coolers:

* `switch`, `input_boolean` - basic toggling mode or PWM mode
* `climate` - basic toggling mode or PID regulator mode
* `number`+`switch`, `input_number`+`switch` -  PID regulator mode with toggleable switch


## Installation (via HACS)

This is recommended way, which will handle one-click upgrade in HACS.

1. Install [hacs] if it is not installed.
2. Open HACS -> Integrations. Click 3 dots in the upper right corner.
3. Click Custom repositories.
4. Add `vaproloff/universalThermostat` repository.
5. Find `Universal Thermostat` in HACS catalog and click `install` button.


## Installation (Manual)

NOTE: This is not recommended way, because you will need to upgrade component manually. 

1. Copy `/custom_components/universal_thermostat` to your `<config_dir>/custom_components/` directory.

   * On HassIO the final location will be `/config/custom_components/universal_thermostat`.
   * On Supervised the final location will be `/usr/share/hassio/homeassistant/custom_components/universal_thermostat`.
   * _NOTE: You will need to create the `custom_components` folder if it does not exist._

2. Restart Home Assistant Core.


## Simple config example
```yaml
climate:
  - platform: universal_thermostat    
    target_sensor: sensor.kitchen_temperature
    cooler: switch.kitchen_cooler_switch
```

## Full config example
```yaml
climate:
  - platform: universal_thermostat    
    name: Kitchen Thermostat
    unique_id: kitchen_thermostat
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

## Glossary

* `target_temp` - Climate target temperature, can be changed in UI. Initial can be set via `target_temp` config option.
* `cur_temp` - Current sensor temperature. Will be reported by `target_sensor` entity.
* `CONFIG.xxx` - Reference to the config option.
* `CONFIG.CONTROLLER.xxx` - Reference to the config controller option (**heater/cooler**).


## Common config options

* `name` _(Required)_ - Climate entity name
* `unique_id` _(Optional)_ - Climate entity `unique_id`
* `cooler` _(Optional)_ - String, Array or Map of the coolers.
* `heater` _(Optional)_ - String, Array or Map of the heaters.
* `target_sensor` _(Required)_ - Target temperature sensor
* `min_temp` _(Optional, default=7)_ - Set minimum set point available.
* `max_temp` _(Optional, default=35)_ - Set maximum set point available.
* `target_temp` _(Optional)_ - Initial target temperature.
* `target_temp_low` _(Optional)_ - Initial target low temperature (for `heat_cool` mode).
* `target_temp_high` _(Optional)_ - Initial target high temperature (for `heat_cool` mode).
* `auto_cool_delta` _(Optional)_ - Target temperature delta for Coolers in `auto` mode. Could be a template. Default: 1.0.
* `auto_heat_delta` _(Optional)_ - Target temperature delta for Heaters in `auto` mode. Could be a template. Default: 1.0.
* `heat_cool_disabled` _(Optional)_ - Disables `heat_cool` mode. Default: false.
* `initial_hvac_mode` _(Optional)_ - Initial HVAC mode.
* `precision` _(Optional)_ - Precision for this device. Supported values are 0.1, 0.5 and 1.0. Default: 0.1 for Celsius and 1.0 for Fahrenheit.
* `target_temp_step` _(Optional)_ - Temperature set point step. Supported values are 0.1, 0.5 and 1.0. Default: equals to `precision`.
* `presets` _(Optional)_ - Map of presets.

_NOTE: at least one of `heater` or `cooler` is required._


## Common behavior

Initial HVAC mode can be set via `initial_hvac_mode` config option.

Thermostat behavior will depend on active HVAC mode. HVAC mode can be set in UI.

### HVAC_MODE = `heat`
_NOTE: available if at least one `CONFIG.heater` was defined._

* All **heater** controllers will be turned on. Specific behavior of each **heater** will depend on the controller type.
* All **cooler** controllers will be turned off.

### HVAC_MODE = `cool`

_NOTE: available if at least one `CONFIG.coller` was defined._

* All **cooler** controllers will be turned on. Specific behavior of each **cooler** will depend on the controller type.
* All **heater** controllers will be turned off.

### HVAC_MODE = `heat_cool` 

_NOTE: available if at least one `CONFIG.heater` and at least one `CONFIG.cooler` were defined._

* All **cooler** and **heater** controllers will be turned on.
* Specific behavior of each **heater** and **cooler** will depend on the controller type.
* All **cooler** controllers will pick `target_temp_high` as their `target_temp`.
* All **heater** controllers will pick `target_temp_low` as their `target_temp`.

### HVAC_MODE = `auto` 

_NOTE: available if at least one `CONFIG.heater` and at least one `CONFIG.cooler` were defined._

* All **cooler** and **heater** controllers will be turned on.
* Specific behavior of each **heater** and **cooler** will depend on the controller type.
* All **cooler** controllers will pick `target_temp + auto_cool_delta` as their `target_temp`.
* All **heater** controllers will pick `target_temp - auto_heat_delta` as their `target_temp`.

_NOTE: turning on controller **DOES NOT MEANS** turning on `CONFIG.CONTROLLER.enitity_id` inside controller. 
Controller behavior depends on the **specific controller logic** and described below for each controller._


## Controllers

Specific controller will be created for each `heater`/`cooler` config option based on `CONFIG.CONTROLLER.enitity_id` domain. 

### Switch controller (ON/OFF)

Supported domains: `switch`,`input_boolean` 

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional, default=false)_ - Need to invert `entity_id` logic.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while. 
* `min_cycle_duration` _(Optional, default=null)_ - Minimal cycle duration. Used to protect from on/off cycling.
* `cold_tolerance` _(Optional, default=0.3)_ - Cold tolerance.
* `hot_tolerance` _(Optional, default=0.3)_ - Hot tolerance.

#### Behavior

* Turn on `entity_id` if `cur_temp <= target_temp - cold_tolerance` (heater) or `cur_temp >= target_temp + self._hot_tolerance` (cooler)
* No `entity_id` changes will be performed if config `min_cycle_duration` was set and enough time was not passed since last switch.
* Behavior on/off will be inverted if `inverted` config option was set to `true`

### PWM Switch PID controller

Domains: `switch`,`input_boolean`.

* Internal PID limits are integers, defined as constants `PWM_SWITCH_MIN_VALUE` and `PWM_SWITCH_MAX_VALUE` (0, 100).
  So, you must use this limits when tuning `pid_params` terms. 

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional, default=false)_ - Need to invert `entity_id` logic.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while. 
* `kp` _(Required)_ - PID proportional coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `ki` _(Required)_ - PID integral coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `kd` _(Required)_ - PID derivative coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `pwm_period`  _(Required)_ - PWM period. Switch will be turned on and turned off according internal PID output once in this period.  

#### Behavior

* PID output will be calculated internally based on provided PID coefficients.
* `pwm_period` will be separated to two parts: `ON` and `OFF`. Each part duration will depend on PID output. 
* PWM on/off need will be checked every `pwm_period/100` time **but not often than each 1 second**. (`PWM_SWITCH_MAX_VALUE` internal const variable)
* Behavior on/off will be inverted if `inverted` config option was set to `true`.
* It is keep on/off state duration before Home Assistant restart. Last change time is saved in thermostat state attributes.

NOTE: This mode will be set if entity domain is one of the listed above and `pid_params` config entry is present.

### Climate controller (Switch mode)

Domains: `climate`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional, default=false)_ - Need to invert `entity_id` logic.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `min_cycle_duration` _(Optional, default=null)_ - Minimal cycle duration. Used to protect from on/off cycling.
* `cold_tolerance` _(Optional, default=0.3)_ - Cold tolerance. Could be a template.
* `hot_tolerance` _(Optional, default=0.3)_ - Hot tolerance. Could be a template.
* `target_temp_delta` _(Optional, default=None)_ - Delta between Thermostat set point and target climate entity. Could be a template. If not mentioned - temperature control will be disabled.

#### Behavior

* Climate `entity_id` will be turned on when controller is active.
* Climate `entity_id` will be turned off when controller is not active.
* Climate `entity_id` temperature set point will be adjusted taking `target_temp_delta` into account if it specified:
  * Thermostat set point + `target_temp_delta` - for heaters;
  * Thermostat set point - `target_temp_delta` - for coolers;

### Climate controller (PID mode)

Domains: `climate`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional, default=false)_ - Need to invert `entity_id` logic.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while.
* `kp` _(Required)_ - PID proportional coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `ki` _(Required)_ - PID integral coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `kd` _(Required)_ - PID derivative coefficient, could be a template (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `min` _(Optional)_ - Minimum temperature which can be set. Attribute `min_temp` from `entity_id` will be used if not specified. Could be a template.
* `max` _(Optional)_ - Maximum temperature which can be set. Attribute `max_temp` from `entity_id` will be used if not specified. Could be a template.

#### Behavior

* Climate `entity_id` will be turned on when controller is active.
* Climate `entity_id` will be turned off when controller is not active.
* Climate `entity_id` temperature will be adjusted every `pid_sample_period` it is provided, or on every `CONFIF.target_sensor` update if `pid_sample_period` is not provided.
* PID parameters will be inverted if `inverted` was set to `true`

### Number + Switch controller (PID mode supported)

Domains: `number`,`input_number`

#### Config options

* `entity_id` _(Required)_ - Target entity ID.
* `inverted` _(Optional, default=false)_ - Need to invert `entity_id` logic.
* `keep_alive` _(Optional)_ - Send keep-alive interval. Use with heaters, coolers,  A/C units that shut off if they don’t receive a signal from their remote for a while. 
* `pid_params` _(Required)_ - PID params comma-separated string or array in the format `Kp, Ki, Kd` (_Always positive, will be inverted internally for cool mode_).
* `pid_sample_period` _(Optional)_ - PID constant sample time period.
* `min` _(Optional)_ - Minimum temperature which can be set. Attribute `min` from `entity_id` will be used if not specified.
* `max` _(Optional)_ - Maximum temperature which can be set. Attribute `max` from `entity_id` will be used if not specified.
* `switch_entity_id` _(Required)_ - Switch entity which belongs to `switch`,`input_boolean` domains.
* `switch_inverted` _(Optional, default=false)_ - Is `switch_entity_id` inverted?

#### Behavior

* Switch `switch_entity_id` will be turned on when controller is active.
* Switch `switch_entity_id` will be turned off when controller is not active.
* Number `entity_id` temperature will be adjusted every `pid_sample_period` it is provided, or on every `CONFIF.target_sensor` update if `pid_sample_period` is not provided.
* `pid_params` will be inverted if `inverted` was set to `true`
* `switch_entity_id` behavior will be inverted if `switch_inverted` was set to `true`


## Presets

Presets are optional and will be available if at least one preset mode added to the config.
All supported preset modes are equal in functionality, their behaviour depends only on used config parameters.

#### Supported preset modes:
* `sleep`
* `away`
* `eco`

#### Common behavior
* if any preset is active, changing `hvac_mode` manually resets current preset to `None`
* if any preset is active, activating `None` `preset_mode` restores thermostat parameters to None-preset state
* if any preset is active, activating another delta `preset_mode` applies all changes relatively to None-preset state
* preset activation can change `hvac_mode` if preset config needs it
* if you want to decrease target temperature, use negative float number.

### Single temperature delta preset config:

#### Config options

* `temp_delta` _(Required)_ - single target temperature delta, signed float, can be a template

#### Behavior

* changes thermostat target temperatures (both ranged and non-ranged):
  * `target_temp + temp_delta`
  * `target_temp_low + temp_delta`
  * `target_temp_high + temp_delta`

### Heating/cooling temperature deltas preset config:

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


## Future TODOs:

* Adjustable delays for turning heater/cooler on/off.
* Add support templates for `pwm_period`.


## Reporting an Issue

1. Set up your logger to print debug messages for this component using:
```yaml
logger:
  default: info
  logs:
    custom_components.universal_thermostat: debug
```
1. Restart HA
2. Verify you're still having the issue
3. File an issue in this GitHub Repository containing your HA log (Developer section > Info > Load Full Home Assistant Log)
   * You can paste your log file at pastebin https://pastebin.com/ and submit a link.
   * Please include details about your setup (Pi, NUC, etc, docker?, HassOS?)
   * The log file can also be found at `/<config_dir>/home-assistant.log`
   

[Smart Thermostat]: https://github.com/hacker-cb/hassio-component-smart-thermostat
[hacker-cb]: https://github.com/hacker-cb
[hacs]: https://hacs.xyz