# Universal Thermostat component for Home Assistant

Integration based on [Smart Thermostat] custom component from [hacker-cb], who did the great job 
I am extremely appreciated for!
Compared with it, I've added some functionality for my needs, namely:
* `heat_cool` mode now uses two target temperatures - `target_temp_low` and `target_temp_high`;
* in `heat_cool` mode coolers and heaters both continue working according to their target set points;
* added `auto` mode with common target temperatures and heating/cooling deltas - for those who prefer one temperature setting or who has compatibility issues with two targets;
* `climate` domain controllers can now also work in simple toggling mode like `switch` without PID;
* PID controller is now local module, not using any dependencies, with other - more classic behaviour;
* Thermostat now restores its state when using `climate.turn_on` service;
* PID parameters, tolerances, limits can now be templates, with values changing tracking without restarting;
* controllers target entities state changing not causes control immediately, they will be updated after target sensor state change;

### Supported domains and modes for heaters and coolers:

* `switch`, `input_boolean` - Basic toggling or PWM mode.
* `climate` - Basic toggling or PID regulator.
* `number`+`switch`, `input_number`+`switch` -  PID regulator with toggleable switch.

### Current features:

* Support multiple heaters/coolers.
* Supports `heat_cool` and `auto` modes.
* Supports invert logic of the heater/cooler.

## Installation (via HACS)

This is recommended way, which will handle one-click upgrade in HACS.

1. Install [hacs] if it is not installed.
2. Open HACS -> Integrations. Click 3 dots in the upper right corner.
3. Click Custom repositories.
4. Add `https://github.com/vaproloff/universalThermostat` repository.
5. Find `Universal Thermostat` and click install button.

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
    auto_cool_delta: 0.5
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
* `auto_cool_delta` _(Optional)_ - Target temperature delta for Coolers in `auto` mode. Default: 1.0.
* `auto_heat_delta` _(Optional)_ - Target temperature delta for Heaters in `auto` mode. Default: 1.0.
* `heat_cool_disabled` _(Optional)_ - Disables `heat_cool` mode. Default: false.
* `initial_hvac_mode` _(Optional)_ - Initial HVAC mode.
* `precision` _(Optional)_ - Precision for this device. Supported values are 0.1, 0.5 and 1.0. Default: 0.1 for Celsius and 1.0 for Fahrenheit.
* `target_temp_step` _(Optional)_ - Temperature set point step. Supported values are 0.1, 0.5 and 1.0. Default: equals to `precision`.

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

## Future TODOs:

* Adjustable delays for turning heater/cooler on/off.
* Add support for preset modes.
* Add support templates for `pwm_period`.

## Reporting an Issue

1. Setup your logger to print debug messages for this component using:
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