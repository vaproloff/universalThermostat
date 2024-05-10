"""Abstract class for controller with PID."""

import abc
from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any, final

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.template import RenderInfo, Template

from ..const import (
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    REASON_KEEP_ALIVE,
    REASON_PID_CONTROL,
    REASON_THERMOSTAT_SENSOR_CHANGED,
    REASON_THERMOSTAT_TARGET_TEMP_CHANGED,
)
from . import AbstractController
from .pid_controller import PIDController

_LOGGER = logging.getLogger(__name__)


class AbstractPidController(AbstractController, abc.ABC):
    """Abstract class for controller with PID."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        pid_kp_template: Template,
        pid_ki_template: Template,
        pid_kd_template: Template,
        pid_sample_period: timedelta | None,
        inverted: bool,
        keep_alive: timedelta | None,
    ) -> None:
        """Initialize the controller."""
        super().__init__(name, mode, target_entity_id, inverted, keep_alive)
        self._pid_kp_template = pid_kp_template
        self._pid_ki_template = pid_ki_template
        self._pid_kd_template = pid_kd_template
        self._pid_sample_period = pid_sample_period
        self._pid: PIDController | None = None
        self._last_output: float | None = None
        self._last_output_limits: None
        self._last_current_value = None

    def get_used_template_entity_ids(self) -> list[str]:
        """Get template entitites to track state."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._pid_kp_template is not None:
            try:
                template_info: RenderInfo = self._pid_kp_template.async_render_to_info()
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._pid_kp_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._pid_ki_template is not None:
            try:
                template_info: RenderInfo = self._pid_ki_template.async_render_to_info()
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._pid_ki_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._pid_kd_template is not None:
            try:
                template_info: RenderInfo = self._pid_kd_template.async_render_to_info()
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._pid_kd_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    async def async_added_to_hass(self, hass: HomeAssistant, attrs: Mapping[str, Any]):
        """Add controller when adding thermostat entity."""
        await super().async_added_to_hass(hass, attrs)

        if self._pid_sample_period:
            _LOGGER.info(
                "%s: %s - Setting up PID regulator. Mode: static period (%s)",
                self._thermostat_entity_id,
                self.name,
                self._pid_sample_period,
            )
            self._thermostat.async_on_remove(
                async_track_time_interval(
                    self._hass, self.__async_pid_control, self._pid_sample_period
                )
            )
        else:
            _LOGGER.info(
                "%s: %s - Setting up PID regulator. Mode: Dynamic period on sensor changes",
                self._thermostat_entity_id,
                self.name,
            )

    @final
    async def __async_pid_control(self, time=None):
        if not self.running:
            return
        await self.async_control(time=time, reason=REASON_PID_CONTROL)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return controller's extra attributes for thermostat entity."""
        return {
            CONF_PID_KP: self.pid_kp,
            CONF_PID_KI: self.pid_ki,
            CONF_PID_KD: self.pid_kd,
        }

    @property
    def pid_kp(self) -> float:
        """Returns Proportional Coefficient."""

        if self._pid_kp_template is None:
            _LOGGER.warning(
                "PID Derivative parameter can't be none. Returning default value"
            )
            return float(DEFAULT_PID_KP)

        try:
            pid_kp = self._pid_kp_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning default value",
                self._pid_kp_template,
                e,
            )
            return float(DEFAULT_PID_KP)

        try:
            pid_kp = float(pid_kp)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning default value",
                pid_kp,
                e,
            )
            return float(DEFAULT_PID_KP)

        if self._mode == HVACMode.COOL:
            pid_kp *= -1

        if self._inverted:
            pid_kp *= -1

        return pid_kp

    @property
    def pid_ki(self) -> float:
        """Returns Integral Coefficient."""

        if self._pid_ki_template is None:
            _LOGGER.warning(
                "PID Derivative parameter can't be none. Returning default value"
            )
            return float(DEFAULT_PID_KI)

        try:
            pid_ki = self._pid_ki_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning default value",
                self._pid_ki_template,
                e,
            )
            return float(DEFAULT_PID_KI)

        try:
            pid_ki = float(pid_ki)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning default value",
                pid_ki,
                e,
            )
            return float(DEFAULT_PID_KI)

        if self._mode == HVACMode.COOL:
            pid_ki *= -1

        if self._inverted:
            pid_ki *= -1

        return pid_ki

    @property
    def pid_kd(self) -> float:
        """Returns Derivative Coefficient."""

        if self._pid_kd_template is None:
            _LOGGER.warning(
                "PID Derivative parameter can't be none. Returning default value"
            )
            return float(DEFAULT_PID_KD)

        try:
            pid_kd = self._pid_kd_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning default value",
                self._pid_kd_template,
                e,
            )
            return float(DEFAULT_PID_KD)

        try:
            pid_kd = float(pid_kd)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning default value",
                pid_kd,
                e,
            )
            return float(DEFAULT_PID_KD)

        if self._mode == HVACMode.COOL:
            pid_kd *= -1

        if self._inverted:
            pid_kd *= -1

        return pid_kd

    async def _async_start(self, cur_temp, target_temp) -> bool:
        return self._setup_pid(cur_temp)

    async def _async_stop(self):
        self._reset_pid()
        self._last_current_value = None

    @final
    def _setup_pid(self, cur_temp):
        _ = cur_temp

        output_limits = self.__get_output_limits()

        if not self.__validate_output_limits(output_limits):
            return False

        self._last_output_limits = output_limits

        sample_time = (
            self._pid_sample_period.total_seconds() if self._pid_sample_period else None
        )

        pid_kp = self.pid_kp
        pid_ki = self.pid_ki
        pid_kd = self.pid_kd

        self._pid = PIDController(
            pid_kp,
            pid_ki,
            pid_kd,
            sample_time,
        )

        _LOGGER.debug(
            "%s: %s - Setup PID done. (PID Kp: %s, PID Ki: %s, PID Kd: %s, limits: %s)",
            self._thermostat_entity_id,
            self.name,
            pid_kp,
            pid_ki,
            pid_kd,
            output_limits,
        )

        return True

    def _reset_pid(self):
        self._pid = None
        self._last_output = None

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        if not self._pid:
            # This should really never happen
            _LOGGER.error("%s: %s - No PID", self._thermostat_entity_id, self.name)
            return

        kp_new = self.pid_kp
        if self._pid.kp != kp_new:
            _LOGGER.debug(
                "%s: %s - Proportional gain was changed from %s to %s",
                self._thermostat_entity_id,
                self.name,
                self._pid.kp,
                kp_new,
            )
            self._pid.kp = kp_new

        ki_new = self.pid_ki
        if self._pid.ki != ki_new:
            _LOGGER.debug(
                "%s: %s - Integral gain was changed from %s to %s",
                self._thermostat_entity_id,
                self.name,
                self._pid.ki,
                ki_new,
            )
            self._pid.ki = ki_new
            self._pid.reset()

        kd_new = self.pid_kd
        if self._pid.kd != kd_new:
            _LOGGER.debug(
                "%s: %s - Derivative gain was changed from %s to %s",
                self._thermostat_entity_id,
                self.name,
                self._pid.kd,
                kd_new,
            )
            self._pid.kd = kd_new
            self._pid.reset()

        if self._pid.set_point != target_temp:
            _LOGGER.debug(
                "%s: %s - Target setpoint was changed from %s to %s (%s)",
                self._thermostat_entity_id,
                self.name,
                self._pid.set_point,
                target_temp,
                reason,
            )
            self._pid.set_point = target_temp
            self._pid.reset()

        output_limits = self.__get_output_limits()
        if self._last_output_limits != output_limits:
            _LOGGER.debug(
                "%s: %s - Output limits were changed from %s to %s (%s)",
                self._thermostat_entity_id,
                self.name,
                self._last_output_limits,
                output_limits,
                reason,
            )
            if not self.__validate_output_limits(output_limits):
                return

            self._last_output_limits = output_limits

        if reason == REASON_KEEP_ALIVE and self._last_output:
            await self._apply_output(self._last_output)
        elif reason in (
            REASON_THERMOSTAT_SENSOR_CHANGED,
            REASON_THERMOSTAT_TARGET_TEMP_CHANGED,
            REASON_PID_CONTROL,
        ):
            output = self._pid.update(cur_temp)
            if output is None:
                _LOGGER.debug(
                    "%s: %s - PID output is None",
                    self._thermostat_entity_id,
                    self.name,
                )
                return
            try:
                output = float(output)
            except ValueError:
                _LOGGER.debug(
                    "%s: %s - Can't parse PID output value: %s",
                    self._thermostat_entity_id,
                    self.name,
                    output,
                )
                return
            output = self._adapt_pid_output(output)
            output = self._round_to_target_precision(output)

            current_output = self._round_to_target_precision(self._get_current_output())

            if current_output != output:
                _LOGGER.debug(
                    "%s: %s - Current temp: %s -> %s, target: %s, limits: %s, adjusting from %s to %s (%s) (p:%f, i:%f, d:%f)",
                    self._thermostat_entity_id,
                    self.name,
                    self._last_current_value,
                    cur_temp,
                    target_temp,
                    output_limits,
                    current_output,
                    output,
                    reason,
                    self._pid.p,
                    self._pid.i,
                    self._pid.d,
                )
                await self._apply_output(output)
            else:
                _LOGGER.debug(
                    "%s: %s - Current temp: %s -> %s, target: %s, limits: %s, no changes needed, output: %s (%s) (p:%f, i:%f, d:%f)",
                    self._thermostat_entity_id,
                    self.name,
                    self._last_current_value,
                    cur_temp,
                    target_temp,
                    output_limits,
                    current_output,
                    reason,
                    self._pid.p,
                    self._pid.i,
                    self._pid.d,
                )

            self._last_output = output
            self._last_current_value = cur_temp

    def __validate_output_limits(self, output_limits: tuple[None, None]) -> bool:
        min_output, max_output = output_limits

        if None in (min_output, max_output):
            _LOGGER.error(
                "%s: %s - Invalid output limits: (%s, %s)",
                self._thermostat_entity_id,
                self.name,
                min_output,
                max_output,
            )
            return False
        return True

    def __get_output_limits(self):
        output_limits = self._get_output_limits()
        min_limit, max_limit = output_limits

        return min_limit, max_limit

    @abc.abstractmethod
    def _adapt_pid_output(self, value: float) -> float:
        """Adapt PID output to output limits."""

    @abc.abstractmethod
    def _round_to_target_precision(self, value: float) -> float:
        """Round output to target precision."""

    @abc.abstractmethod
    def _get_current_output(self):
        """Get current output."""

    @abc.abstractmethod
    def _get_output_limits(self) -> tuple[None, None]:
        """Get output limits (min,max) in controller implementation."""

    @abc.abstractmethod
    async def _apply_output(self, output: float):
        """Apply output to target."""
