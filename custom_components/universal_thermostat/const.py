"""Constant variables used by integration."""

DEFAULT_NAME = "Universal Thermostat"
DEFAULT_HOT_TOLERANCE = 0.3
DEFAULT_COLD_TOLERANCE = 0.3
DEFAULT_CLIMATE_TEMP_DELTA = 0.0
DEFAULT_AUTO_COOL_DELTA = 1.0
DEFAULT_AUTO_HEAT_DELTA = 1.0
DEFAULT_PID_KP = 0.0
DEFAULT_PID_KI = 0.0
DEFAULT_PID_KD = 0.0
DEFAULT_PID_MIN = 0.0
DEFAULT_PID_MAX = 100.0
CONF_HEATER = "heater"
CONF_COOLER = "cooler"
CONF_INVERTED = "inverted"
CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP = "target_temp"
CONF_TARGET_TEMP_HIGH = "target_temp_high"
CONF_TARGET_TEMP_LOW = "target_temp_low"
CONF_AUTO_COOL_DELTA = "auto_cool_delta"
CONF_AUTO_HEAT_DELTA = "auto_heat_delta"
CONF_HEAT_COOL_DISABLED = "heat_cool_disabled"
CONF_MIN_DUR = "min_cycle_duration"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_CLIMATE_TEMP_DELTA = "target_temp_delta"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_PRECISION = "precision"
CONF_TEMP_STEP = "target_temp_step"
CONF_PID_KP = "kp"
CONF_PID_KI = "ki"
CONF_PID_KD = "kd"
CONF_PID_SAMPLE_PERIOD = "pid_sample_period"
CONF_PID_MIN = "min"
CONF_PID_MAX = "max"
CONF_PWM_SWITCH_PERIOD = "pwm_period"
CONF_PID_SWITCH_ENTITY_ID = "switch_entity_id"
CONF_PID_SWITCH_INVERTED = "switch_inverted"
ATTR_LAST_ASYNC_CONTROL_HVAC_MODE = "async_control_hvac_mode"
ATTR_LAST_ACTIVE_HVAC_MODE = "last_active_hvac_mode"
ATTR_PREV_TARGET = "prev_target_temp"
ATTR_PREV_TARGET_LOW = "prev_target_temp_low"
ATTR_PREV_TARGET_HIGH = "prev_target_temp_high"
REASON_THERMOSTAT_FIRST_RUN = "first_run"
REASON_THERMOSTAT_HVAC_MODE_CHANGED = "hvac_mode_changed"
REASON_THERMOSTAT_TARGET_TEMP_CHANGED = "target_temp_changed"
REASON_THERMOSTAT_SENSOR_CHANGED = "sensor_changed"
REASON_CONTROL_ENTITY_CHANGED = "control_entity_changed"
REASON_AUTO_COOL_DELTAS_CHANGED = "auto_cool_deltas_changed"
REASON_THERMOSTAT_STOP = "stop"
REASON_THERMOSTAT_NOT_RUNNING = "not_running"
REASON_KEEP_ALIVE = "keep_alive"
REASON_PWM_CONTROL = "pwm_control"
REASON_PID_CONTROL = "pid_control"
PWM_SWITCH_ATTR_PWM_VALUE = "pwm_value"
PWM_SWITCH_ATTR_LAST_CONTROL_TIME = "last_control_time"
PWM_SWITCH_ATTR_LAST_CONTROL_STATE = "last_control_state"
PWM_SWITCH_MIN_VALUE = 0
PWM_SWITCH_MAX_VALUE = 100
