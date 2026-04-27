"""Adds support for universal thermostat units."""

import logging
from typing import Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import split_entity_id
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CLIMATE_TEMP_DELTA,
    CONF_COLD_TOLERANCE,
    CONF_HOT_TOLERANCE,
    CONF_IGNORE_WINDOWS,
    CONF_INVERTED,
    CONF_KEEP_ALIVE,
    CONF_MIN_DUR,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PID_MAX,
    CONF_PID_MIN,
    CONF_PID_SAMPLE_PERIOD,
    CONF_PID_SWITCH_ENTITY_ID,
    CONF_PID_SWITCH_INVERTED,
    CONF_PWM_SWITCH_PERIOD,
)
from .controllers.abstract_controller import AbstractController
from .controllers.climate_pid_controller import ClimatePidController
from .controllers.climate_switch_controller import ClimateSwitchController
from .controllers.number_pid_controller import NumberPidController
from .controllers.pwm_switch_pid_controller import PwmSwitchPidController
from .controllers.switch_controller import SwitchController

_LOGGER = logging.getLogger(__name__)


def create_controllers(
    prefix: str,
    mode: str,
    conf_list: Any,
) -> list[AbstractController]:
    """Controller factory."""
    if conf_list is None:
        return []
    if not isinstance(conf_list, list):
        conf_list = [conf_list]

    controllers: list[AbstractController] = []

    for controller_number, conf in enumerate(conf_list, 1):
        name = f"{prefix}_{controller_number}"

        entity_id = conf[CONF_ENTITY_ID]
        inverted = conf.get(CONF_INVERTED, False)
        keep_alive = _cv_time_period(conf.get(CONF_KEEP_ALIVE, None))
        ignore_windows = conf.get(CONF_IGNORE_WINDOWS, False)

        domain = split_entity_id(entity_id)[0]

        controller = None

        if domain in [SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]:
            if CONF_PID_KP in conf:
                controller = PwmSwitchPidController(
                    name,
                    mode,
                    entity_id,
                    conf[CONF_PID_KP],
                    conf[CONF_PID_KI],
                    conf[CONF_PID_KD],
                    conf.get(CONF_PID_SAMPLE_PERIOD, None),
                    inverted,
                    keep_alive,
                    ignore_windows,
                    conf[CONF_PWM_SWITCH_PERIOD],
                )
            else:
                min_duration = _cv_time_period(conf.get(CONF_MIN_DUR, None))
                cold_tolerance = conf[CONF_COLD_TOLERANCE]
                hot_tolerance = conf[CONF_HOT_TOLERANCE]

                controller = SwitchController(
                    name,
                    mode,
                    entity_id,
                    cold_tolerance,
                    hot_tolerance,
                    inverted,
                    keep_alive,
                    ignore_windows,
                    min_duration,
                )

        elif domain == CLIMATE_DOMAIN:
            if CONF_PID_KP in conf:
                controller = ClimatePidController(
                    name,
                    mode,
                    entity_id,
                    conf[CONF_PID_KP],
                    conf[CONF_PID_KI],
                    conf[CONF_PID_KD],
                    conf.get(CONF_PID_SAMPLE_PERIOD, None),
                    inverted,
                    keep_alive,
                    ignore_windows,
                    conf.get(CONF_PID_MIN, None),
                    conf.get(CONF_PID_MAX, None),
                )
            else:
                min_duration = _cv_time_period(conf.get(CONF_MIN_DUR, None))
                cold_tolerance = conf[CONF_COLD_TOLERANCE]
                hot_tolerance = conf[CONF_HOT_TOLERANCE]
                temp_delta = conf.get(CONF_CLIMATE_TEMP_DELTA, None)

                controller = ClimateSwitchController(
                    name,
                    mode,
                    entity_id,
                    cold_tolerance,
                    hot_tolerance,
                    temp_delta,
                    inverted,
                    keep_alive,
                    ignore_windows,
                    min_duration,
                )

        elif domain in [INPUT_NUMBER_DOMAIN, NUMBER_DOMAIN]:
            controller = NumberPidController(
                name,
                mode,
                entity_id,
                conf[CONF_PID_KP],
                conf[CONF_PID_KI],
                conf[CONF_PID_KD],
                _cv_time_period(conf.get(CONF_PID_SAMPLE_PERIOD, None)),
                inverted,
                keep_alive,
                ignore_windows,
                conf.get(CONF_PID_MIN, None),
                conf.get(CONF_PID_MAX, None),
                conf.get(CONF_PID_SWITCH_ENTITY_ID, None),
                conf[CONF_PID_SWITCH_INVERTED],
            )

        else:
            _LOGGER.error(
                "Unsupported %s domain: '%s' for entity %s", name, domain, entity_id
            )

        if controller:
            controllers.append(controller)

    return controllers


def _cv_time_period(value: Any) -> Any:
    """Convert a config flow duration dict to a time period."""
    if value is None:
        return None
    return cv.positive_time_period(value)
