"""Support for PWM switch controllers with PID."""

from collections.abc import Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import DOMAIN as HA_DOMAIN, HomeAssistant, split_entity_id
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from ..const import (
    PWM_SWITCH_ATTR_LAST_CONTROL_STATE,
    PWM_SWITCH_ATTR_LAST_CONTROL_TIME,
    PWM_SWITCH_ATTR_PWM_VALUE,
    PWM_SWITCH_MAX_VALUE,
    PWM_SWITCH_MIN_VALUE,
    REASON_KEEP_ALIVE,
    REASON_PWM_CONTROL,
    REASON_THERMOSTAT_NOT_RUNNING,
    REASON_THERMOSTAT_STOP,
)
from . import AbstractPidController

_LOGGER = logging.getLogger(__name__)


class PwmSwitchPidController(AbstractPidController):
    """PID-PWM switch controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        pid_kp_template: Template,
        pid_ki_template: Template,
        pid_kd_template: Template,
        pid_sample_period: timedelta,
        inverted: bool,
        keep_alive: timedelta | None,
        pwm_period: timedelta,
    ) -> None:
        """Initialize the controller."""
        super().__init__(
            name,
            mode,
            target_entity_id,
            pid_kp_template,
            pid_ki_template,
            pid_kd_template,
            pid_sample_period,
            inverted,
            keep_alive,
        )
        self._pwm_period = pwm_period
        self._pwm_value: int | None = None
        target_entity_name = split_entity_id(target_entity_id)[1]
        self._pwm_value_attr_name = target_entity_name + PWM_SWITCH_ATTR_PWM_VALUE

        self._pwm_control_period = self._pwm_period / PWM_SWITCH_MAX_VALUE
        self._pwm_control_period = max(self._pwm_control_period, timedelta(seconds=1))

        self._last_control_time: datetime | None = None
        self._last_control_state: str | None = None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return controller's extra attributes for thermostat entity."""
        attrs = super().extra_state_attributes or {}

        if None not in (self._last_control_time, self._last_control_state):
            attrs.update(
                {
                    PWM_SWITCH_ATTR_LAST_CONTROL_TIME: self._last_control_time.replace(
                        microsecond=0
                    ),
                    PWM_SWITCH_ATTR_LAST_CONTROL_STATE: self._last_control_state,
                }
            )

        if self._pwm_value is not None:
            attrs[PWM_SWITCH_ATTR_PWM_VALUE] = self._pwm_value

        return attrs

    @property
    def _is_on(self) -> bool:
        return self._hass.states.is_state(
            self._target_entity_id, STATE_ON if not self._inverted else STATE_OFF
        )

    async def async_added_to_hass(self, hass: HomeAssistant, attrs: Mapping[str, Any]):
        """Add controller when adding thermostat entity."""
        await super().async_added_to_hass(hass, attrs)

        pwm_value = attrs.get(PWM_SWITCH_ATTR_PWM_VALUE, None)
        if pwm_value is not None:
            self._pwm_value = self._round_to_target_precision(pwm_value)

        last_control_time = attrs.get(PWM_SWITCH_ATTR_LAST_CONTROL_TIME, None)
        if last_control_time is not None:
            self._last_control_time = dt_util.parse_datetime(last_control_time)

        self._last_control_state = attrs.get(PWM_SWITCH_ATTR_LAST_CONTROL_STATE, None)

        if self._pwm_value is None:
            # Apply default output value
            output = int((PWM_SWITCH_MIN_VALUE + PWM_SWITCH_MAX_VALUE) / 2)
            await self._apply_output(output)

        _LOGGER.info(
            "%s - %s: setting up PWM switch. PWM value: %s, period: %s, last control: [state: %s, time: %s], check PWM control every %s",
            self._thermostat.entity_id,
            self.name,
            self._pwm_value,
            self._pwm_period,
            self._last_control_state,
            self._last_control_time,
            self._pwm_control_period,
        )
        self._thermostat.async_on_remove(
            async_track_time_interval(
                self._hass, self._async_pwm_control, self._pwm_control_period
            )
        )

    def _adapt_pid_output(self, value: float) -> float:
        return value

    def _round_to_target_precision(self, value: float) -> float:
        # PWM value always int
        return int(value)

    def _get_current_output(self):
        return self._pwm_value

    async def _async_turn_on(self, reason):
        _LOGGER.debug(
            "%s - %s: turning on %s (%s)",
            self._thermostat.entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service = SERVICE_TURN_ON if not self._inverted else SERVICE_TURN_OFF
        service_data = {ATTR_ENTITY_ID: self._target_entity_id}
        await self._hass.services.async_call(
            domain=HA_DOMAIN,
            service=service,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        _LOGGER.debug(
            "%s - %s: turning off %s (%s)",
            self._thermostat.entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service = SERVICE_TURN_OFF if not self._inverted else SERVICE_TURN_ON
        service_data = {ATTR_ENTITY_ID: self._target_entity_id}
        await self._hass.services.async_call(
            domain=HA_DOMAIN,
            service=service,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_stop(self):
        await super()._async_stop()
        await self._async_turn_off(reason=REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on:
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    def _get_output_limits(self) -> tuple[float, float]:
        return PWM_SWITCH_MIN_VALUE, PWM_SWITCH_MAX_VALUE

    async def _apply_output(self, output: float):
        if self._pwm_value != output:
            self._pwm_value = output
            self._thermostat.async_write_ha_state()

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        await super()._async_control(
            cur_temp,
            target_temp,
            time,
            force,
            reason,
        )

        if self._last_control_state:
            # Check real state is correct or keepalive requested
            if self._last_control_state == STATE_ON and (
                reason == REASON_KEEP_ALIVE or not self._is_on
            ):
                _LOGGER.debug(
                    "%s: %s force ON (%s)",
                    self._thermostat.entity_id,
                    self.name,
                    reason,
                )
                await self._async_turn_on(reason=reason)
            elif self._last_control_state == STATE_OFF and (
                reason == REASON_KEEP_ALIVE or self._is_on
            ):
                _LOGGER.debug(
                    "%s: %s force OFF (%s)",
                    self._thermostat.entity_id,
                    self.name,
                    reason,
                )
                await self._async_turn_off(reason=reason)

        elif self._is_on:
            # no _last_control_state - should be always off
            await self._async_turn_off(reason=reason)

        if reason == REASON_PWM_CONTROL:
            await self._pwm_control(reason=reason)

    async def _async_pwm_control(self, time=None):
        if not self.running:
            return
        await self.async_control(time=time, reason=REASON_PWM_CONTROL)

    async def _pwm_control(self, reason):
        if self._pwm_value is None:
            # This should really never happen
            _LOGGER.error(
                "%s - %s: PWM value is None (%s)",
                self._thermostat.entity_id,
                self.name,
                reason,
            )
            return

        new_state = None  # will be applied if not None

        pwm_on_duration: timedelta = (
            self._pwm_period * self._pwm_value / PWM_SWITCH_MAX_VALUE
        )
        pwm_off_duration: timedelta = self._pwm_period - pwm_on_duration

        need_to_wait = None

        if None in (self._last_control_state, self._last_control_time):
            # Start with ON state
            new_state = STATE_ON
        else:
            now = dt_util.now().replace(microsecond=0)

            if (
                self._last_control_state == STATE_ON
                and pwm_off_duration.total_seconds() > 0
            ):
                if now >= (self._last_control_time + pwm_on_duration):
                    new_state = STATE_OFF
                else:
                    need_to_wait = self._last_control_time + pwm_on_duration - now

            elif (
                self._last_control_state == STATE_OFF
                and pwm_on_duration.total_seconds() > 0
            ):
                if now >= (self._last_control_time + pwm_off_duration):
                    new_state = STATE_ON
                else:
                    need_to_wait = self._last_control_time + pwm_off_duration - now

        change_info = (
            f"`{self._last_control_state}` -> `{new_state}`"
            if new_state
            else f"`{self._last_control_state}` - wait {need_to_wait}"
        )

        _LOGGER.debug(
            "%s - %s: PWM value: %s, last: (state: %s, time: %s), dur: (on: %s, off: %s): state: (%s) ",
            self._thermostat.entity_id,
            self.name,
            self._pwm_value,
            self._last_control_state,
            self._last_control_time,
            pwm_on_duration,
            pwm_off_duration,
            change_info,
        )

        # Save last control params
        if new_state:
            self._last_control_time = dt_util.now().replace(microsecond=0)
            self._last_control_state = new_state
            self._thermostat.async_write_ha_state()

            if new_state == STATE_ON:
                await self._async_turn_on(reason=reason)
            elif new_state == STATE_OFF:
                await self._async_turn_off(reason=reason)
