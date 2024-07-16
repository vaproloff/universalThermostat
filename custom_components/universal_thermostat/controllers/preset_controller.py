"""Thermostat presets dealing classes."""

import abc
import logging

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntityFeature,
    HVACMode,
)

from ..const import (
    DEFAULT_PRESET_AUTO_TEMP_DELTA,
    PRESET_NONE_HVAC_MODE,
    PRESET_NONE_TARGET_TEMP,
    PRESET_NONE_TARGET_TEMP_HIGH,
    PRESET_NONE_TARGET_TEMP_LOW,
)

_LOGGER = logging.getLogger(__name__)


class Thermostat(abc.ABC):
    """Abstract class for universal thermostat entity."""

    @property
    @abc.abstractmethod
    def hvac_mode(self) -> HVACMode | None:
        """Get thermostat HVAC mode."""

    @hvac_mode.setter
    @abc.abstractmethod
    def hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set thermostat HVAC mode."""

    @property
    @abc.abstractmethod
    def target_temperature(self) -> float | None:
        """Get thermostat target temperature."""

    @target_temperature.setter
    @abc.abstractmethod
    def target_temperature(self, target_temp: float) -> None:
        """Set thermostat target temperature."""

    @property
    @abc.abstractmethod
    def target_temperature_high(self) -> float | None:
        """Get thermostat high target temperature."""

    @target_temperature_high.setter
    @abc.abstractmethod
    def target_temperature_high(self, target_temp_high: float) -> None:
        """Set thermostat high target temperature."""

    @property
    @abc.abstractmethod
    def target_temperature_low(self) -> float | None:
        """Get thermostat low target temperature."""

    @target_temperature_low.setter
    @abc.abstractmethod
    def target_temperature_low(self, target_temp_low: float):
        """Set thermostat low target temperature."""

    @property
    @abc.abstractmethod
    def preset_mode(self) -> str | None:
        """Get thermostat current preset mode."""

    @preset_mode.setter
    @abc.abstractmethod
    def preset_mode(self, preset_mode: str) -> None:
        """Set thermostat current preset mode."""

    @property
    @abc.abstractmethod
    def preset_modes(self) -> list[str] | None:
        """Get available thermostat preset modes."""

    @property
    @abc.abstractmethod
    def supported_features(self):
        """Get thermostat list of supported features."""

    @abc.abstractmethod
    def set_support_flags(self) -> None:
        """Set thermostat support flags."""

    @abc.abstractmethod
    def async_write_ha_state(self) -> None:
        """Write thermostat state."""


class Preset:
    """Preset class."""

    def __init__(self, preset_config: dict) -> None:
        """Initialize the preset."""
        self._temp_delta: float = preset_config.get("temp_delta")
        self._heat_delta: float = preset_config.get("heat_delta")
        self._cool_delta: float = preset_config.get("cool_delta")
        self._target_temp: float = preset_config.get("target_temp")
        self._heat_target_temp: float = preset_config.get("heat_target_temp")
        self._cool_target_temp: float = preset_config.get("cool_target_temp")

    def get_hvac_mode(self, current_hvac_mode):
        """Return preset HVAC mode according to preset config."""
        if (
            self._temp_delta is not None
            or None not in (self._heat_delta, self._cool_delta)
            or self._target_temp is not None
        ):
            return current_hvac_mode

        if current_hvac_mode in (HVACMode.AUTO, HVACMode.HEAT_COOL):
            if self._heat_target_temp is None and self._cool_target_temp is not None:
                return HVACMode.COOL
            if self._heat_target_temp is not None and self._cool_target_temp is None:
                return HVACMode.HEAT
            return current_hvac_mode

        if (
            current_hvac_mode == HVACMode.HEAT
            and self._heat_target_temp is None
            and self._cool_target_temp is not None
        ):
            return HVACMode.COOL
        if (
            current_hvac_mode == HVACMode.COOL
            and self._heat_target_temp is None
            and self._cool_target_temp is not None
        ):
            return HVACMode.HEAT

        return current_hvac_mode

    def get_target_temp(self, current_hvac_mode, current_target_temp) -> float:
        """Return new target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp + self._temp_delta

        if current_hvac_mode == HVACMode.COOL and self._cool_delta is not None:
            return current_target_temp + self._cool_delta

        if current_hvac_mode == HVACMode.HEAT and self._heat_delta is not None:
            return current_target_temp + self._heat_delta

        if current_hvac_mode == HVACMode.COOL and self._cool_target_temp is not None:
            return self._cool_target_temp

        if current_hvac_mode == HVACMode.HEAT and self._heat_target_temp is not None:
            return self._heat_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp

    def get_target_temp_low(self, current_target_temp_low) -> float:
        """Return new low target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp_low + self._temp_delta

        if self._heat_delta is not None:
            return current_target_temp_low + self._heat_delta

        if self._heat_target_temp is not None:
            return self._heat_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp_low

    def get_target_temp_high(self, current_target_temp_high: float) -> float:
        """Return new high target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp_high + self._temp_delta

        if self._cool_delta is not None:
            return current_target_temp_high + self._cool_delta

        if self._cool_target_temp is not None:
            return self._cool_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp_high

    def get_auto_heat_delta(self) -> float:
        """Return auto mode heat delta according to preset config."""
        if self._heat_delta is not None:
            return self._heat_delta
        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    def get_auto_cool_delta(self) -> float:
        """Return auto mode cool delta according to preset config."""
        if self._cool_delta is not None:
            return self._cool_delta
        return DEFAULT_PRESET_AUTO_TEMP_DELTA


class PresetController:
    """Coordinator for presets if available."""

    def __init__(self, presets) -> None:
        """Initialize the coordinator."""
        _LOGGER.info("Presets: %s", presets)
        self._thermostat: Thermostat = None
        self._preset: Preset = None
        self._preset_sleep: Preset | None = None
        self._preset_away: Preset | None = None
        self._preset_eco: Preset | None = None
        self._saved_hvac_mode: HVACMode | None = None
        self._saved_target_temp: float = None
        self._saved_target_temp_low: float = None
        self._saved_target_temp_high: float = None

        if presets.get(PRESET_SLEEP) is not None:
            self._preset_sleep = Preset(presets.get(PRESET_SLEEP))
        if presets.get(PRESET_AWAY) is not None:
            self._preset_away = Preset(presets.get(PRESET_AWAY))
        if presets.get(PRESET_ECO) is not None:
            self._preset_eco = Preset(presets.get(PRESET_ECO))

    def set_thermostat(self, thermostat: Thermostat) -> None:
        """Set parent universal thermostat entity."""
        self._thermostat = thermostat

        if self._preset_sleep is not None:
            self._thermostat.preset_modes.append(PRESET_SLEEP)
        if self._preset_away is not None:
            self._thermostat.preset_modes.append(PRESET_AWAY)
        if self._preset_eco is not None:
            self._thermostat.preset_modes.append(PRESET_ECO)

    def set_preset(self, preset_mode) -> None:
        """Set preset."""
        if preset_mode == PRESET_SLEEP:
            self._preset = self._preset_sleep
        elif preset_mode == PRESET_AWAY:
            self._preset = self._preset_away
        elif preset_mode == PRESET_ECO:
            self._preset = self._preset_eco
        else:
            self._preset = None

    def _save(self) -> None:
        """Save thermostat parameters."""
        self._saved_hvac_mode = self._thermostat.hvac_mode
        self._saved_target_temp = self._thermostat.target_temperature
        self._saved_target_temp_low = self._thermostat.target_temperature_low
        self._saved_target_temp_high = self._thermostat.target_temperature_high

    def _reset(self) -> None:
        """Reset all saved parameters after falling back from preset."""
        self._saved_hvac_mode = None
        self._saved_target_temp = None
        self._saved_target_temp_low = None
        self._saved_target_temp_high = None
        self._preset = None

    def restore_saved(self, saved_state: dict) -> None:
        """Restore saved parameters from state dict."""
        self._saved_hvac_mode = saved_state.get(PRESET_NONE_HVAC_MODE)
        self._saved_target_temp = saved_state.get(PRESET_NONE_TARGET_TEMP)
        self._saved_target_temp_low = saved_state.get(PRESET_NONE_TARGET_TEMP_LOW)
        self._saved_target_temp_high = saved_state.get(PRESET_NONE_TARGET_TEMP_HIGH)

    @property
    def get_saved(self) -> None:
        """Get saved parameters state dict."""
        if None not in (
            self._saved_hvac_mode,
            self._saved_target_temp,
            self._saved_target_temp_low,
            self._saved_target_temp_high,
        ):
            return {
                PRESET_NONE_HVAC_MODE: self._saved_hvac_mode,
                PRESET_NONE_TARGET_TEMP: self._saved_target_temp,
                PRESET_NONE_TARGET_TEMP_LOW: self._saved_target_temp_low,
                PRESET_NONE_TARGET_TEMP_HIGH: self._saved_target_temp_high,
            }

    def set_preset_mode(self, new_preset_mode) -> None:
        """Try to set new preset mode."""
        if new_preset_mode == PRESET_NONE:
            if (
                self._saved_hvac_mode
                and self._saved_hvac_mode != self._thermostat.hvac_mode
            ):
                _LOGGER.info(
                    "HVAC mode was changed. Falling back to %s",
                    self._saved_hvac_mode,
                )
                self._thermostat.hvac_mode = self._saved_hvac_mode

            if (
                self._saved_target_temp
                and self._saved_target_temp != self._thermostat.target_temperature
            ):
                _LOGGER.info(
                    "Target temp was changed. Falling back to %s",
                    self._saved_target_temp,
                )
                self._thermostat.target_temperature = self._saved_target_temp

            if (
                self._saved_target_temp_low
                and self._saved_target_temp_low
                != self._thermostat.target_temperature_low
            ):
                _LOGGER.info(
                    "Target temp low was changed. Falling back to %s",
                    self._saved_target_temp_low,
                )
                self._thermostat.target_temperature_low = self._saved_target_temp_low

            if (
                self._saved_target_temp_high
                and self._saved_target_temp_high
                != self._thermostat.target_temperature_high
            ):
                _LOGGER.info(
                    "Target temp high was changed. Falling back to %s",
                    self._saved_target_temp_high,
                )
                self._thermostat.target_temperature_high = self._saved_target_temp_high

            self._reset()
        else:
            _LOGGER.info("Setting new preset: %s", new_preset_mode)

            if self._thermostat.preset_mode == PRESET_NONE:
                _LOGGER.info("Saving thermostat parameters")
                self._save()

            self.set_preset(new_preset_mode)

            new_hvac_mode = self._get_hvac_mode(self._thermostat.hvac_mode)
            if self._thermostat.hvac_mode != new_hvac_mode:
                _LOGGER.info(
                    "Preset %s needs HVAC mode to be changed to %s",
                    new_preset_mode,
                    new_hvac_mode,
                )
                self._thermostat.hvac_mode = new_hvac_mode
                self._thermostat.set_support_flags()

            if (
                self._thermostat.supported_features
                & ClimateEntityFeature.TARGET_TEMPERATURE
            ):
                self._thermostat.target_temperature = self._get_target_temp(
                    self._thermostat.hvac_mode, self._thermostat.target_temperature
                )
            elif (
                self._thermostat.supported_features
                & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            ):
                self._thermostat.target_temperature_low = self._get_target_temp_low(
                    self._thermostat.target_temperature_low
                )
                self._thermostat.target_temperature_high = self._get_target_temp_high(
                    self._thermostat.target_temperature_high
                )

        self._thermostat.preset_mode = new_preset_mode

    def _get_hvac_mode(self, hvac_mode: HVACMode):
        """Return current preset HVAC mode."""
        if self._saved_hvac_mode:
            return self._preset.get_hvac_mode(self._saved_hvac_mode)
        return self._preset.get_hvac_mode(hvac_mode)

    def _get_target_temp(self, hvac_mode: HVACMode, target_temp: float):
        """Return current preset new target temp."""
        if self._saved_target_temp:
            return self._preset.get_target_temp(hvac_mode, self._saved_target_temp)
        return self._preset.get_target_temp(hvac_mode, target_temp)

    def _get_target_temp_low(self, target_temp_low: float):
        """Return current preset new low target temp."""
        if self._saved_target_temp_low:
            return self._preset.get_target_temp_low(self._saved_target_temp_low)
        return self._preset.get_target_temp_low(target_temp_low)

    def _get_target_temp_high(self, target_temp_high: float):
        """Return current preset new high target temp."""
        if self._saved_target_temp_low:
            return self._preset.get_target_temp_high(self._saved_target_temp_high)
        return self._preset.get_target_temp_high(target_temp_high)

    @property
    def auto_heat_delta(self) -> float:
        """Return current preset new auto heat delta."""
        if self._preset is not None and self._thermostat.hvac_mode == HVACMode.AUTO:
            return self._preset.get_auto_heat_delta()

        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    @property
    def auto_cool_delta(self) -> float:
        """Return current preset new auto cool delta."""
        if self._preset is not None and self._thermostat.hvac_mode == HVACMode.AUTO:
            return self._preset.get_auto_cool_delta()

        return DEFAULT_PRESET_AUTO_TEMP_DELTA
