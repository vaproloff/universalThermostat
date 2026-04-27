"""Config flow for the Universal Thermostat integration."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.climate import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
)
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import callback, split_entity_id
from homeassistant.helpers import selector

from . import DOMAIN
from .config_schema import SUPPORTED_TARGET_DOMAINS, SUPPORTED_WINDOW_DOMAINS
from .const import (
    ATTR_TIMEOUT,
    CONF_AUTO_COOL_DELTA,
    CONF_AUTO_HEAT_DELTA,
    CONF_AUTO_MODE_DISABLED,
    CONF_CLIMATE_TEMP_DELTA,
    CONF_COLD_TOLERANCE,
    CONF_COOLER,
    CONF_HEAT_COOL_DISABLED,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_IGNORE_WINDOWS,
    CONF_INVERTED,
    CONF_KEEP_ALIVE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PID_MAX,
    CONF_PID_MIN,
    CONF_PID_SAMPLE_PERIOD,
    CONF_PID_SWITCH_ENTITY_ID,
    CONF_PID_SWITCH_INVERTED,
    CONF_PRESET_COOL_DELTA,
    CONF_PRESET_COOL_TARGET_TEMP,
    CONF_PRESET_HEAT_DELTA,
    CONF_PRESET_HEAT_TARGET_TEMP,
    CONF_PRESET_TARGET_TEMP,
    CONF_PRESET_TEMP_DELTA,
    CONF_PRESETS,
    CONF_PWM_SWITCH_PERIOD,
    CONF_SENSOR,
    CONF_WINDOWS,
    CTRL_CFG_CLIMATE_PID,
    CTRL_CFG_CLIMATE_SWITCH,
    CTRL_CFG_NUMBER_PID,
    CTRL_CFG_PWM_SWITCH,
    CTRL_CFG_SWITCH,
    DEFAULT_AUTO_COOL_DELTA,
    DEFAULT_AUTO_HEAT_DELTA,
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_HOT_TOLERANCE,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    PRESET_TYPE_HEAT_COOL_DELTAS,
    PRESET_TYPE_TARGET_TEMPS,
    PRESET_TYPE_TEMP_DELTA,
)

CLEAR_FIELD_PREFIX = "clear_"


class UniversalThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Universal Thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow lifecycle properties."""
        self._draft: dict[str, Any] = {
            CONF_NAME: None,
            CONF_SENSOR: None,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return UniversalThermostatOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            self._draft[CONF_NAME] = user_input[CONF_NAME]
            self._draft[CONF_SENSOR] = user_input[CONF_SENSOR]

            await self.async_set_unique_id(
                f"{self._draft[CONF_SENSOR]}_{self._draft[CONF_NAME]}"
            )
            self._abort_if_unique_id_configured()

            return await self.async_step_options_notice()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=self._draft[CONF_NAME] or DEFAULT_NAME,
                    ): str,
                    vol.Required(
                        CONF_SENSOR, default=self._draft[CONF_SENSOR]
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=[SENSOR_DOMAIN])
                    ),
                }
            ),
        )

    async def async_step_options_notice(self, user_input: dict[str, Any] | None = None):
        """Inform the user that options must be configured next."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._draft[CONF_NAME],
                data=self._draft,
            )

        return self.async_show_form(
            step_id="options_notice",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._draft[CONF_NAME],
                "sensor": self._draft[CONF_SENSOR],
            },
        )


class UniversalThermostatOptionsFlow(config_entries.OptionsFlow):
    """Handle an option flow for Universal Thermostat."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._draft: dict[str, Any] = {
            CONF_NAME: config_entry.data[CONF_NAME],
            CONF_SENSOR: config_entry.data[CONF_SENSOR],
            CONF_MIN_TEMP: config_entry.options.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP),
            CONF_MAX_TEMP: config_entry.options.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP),
            CONF_HEATER: [
                dict(controller)
                for controller in config_entry.options.get(CONF_HEATER, [])
            ],
            CONF_COOLER: [
                dict(controller)
                for controller in config_entry.options.get(CONF_COOLER, [])
            ],
            CONF_HEAT_COOL_DISABLED: config_entry.options.get(
                CONF_HEAT_COOL_DISABLED, False
            ),
            CONF_AUTO_MODE_DISABLED: config_entry.options.get(
                CONF_AUTO_MODE_DISABLED, False
            ),
            CONF_AUTO_COOL_DELTA: config_entry.options.get(
                CONF_AUTO_COOL_DELTA, DEFAULT_AUTO_COOL_DELTA
            ),
            CONF_AUTO_HEAT_DELTA: config_entry.options.get(
                CONF_AUTO_HEAT_DELTA, DEFAULT_AUTO_HEAT_DELTA
            ),
            CONF_WINDOWS: [
                dict(window) for window in config_entry.options.get(CONF_WINDOWS, [])
            ],
            CONF_PRESETS: {
                preset: dict(config)
                for preset, config in config_entry.options.get(CONF_PRESETS, {}).items()
            },
        }

        self._cur_ctrl_type: str | None = None
        self._cur_controller: dict[str, Any] = {}
        self._cur_ctrl_cfg_type = None
        self._cur_ctrl_index: int | None = None
        self._cur_window: dict[str, Any] = {}
        self._cur_window_index: int | None = None
        self._cur_preset_name: str | None = None
        self._cur_preset_type: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage Universal Thermostat options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input["action"]

            if action == "thermostat_settings":
                return await self.async_step_thermostat_settings()
            if action == "controllers_menu":
                return await self.async_step_controllers_menu()
            if action == "windows_menu":
                return await self.async_step_windows_menu()
            if action == "presets_menu":
                return await self.async_step_presets_menu()

            if action == "save":
                if not self._draft[CONF_HEATER] and not self._draft[CONF_COOLER]:
                    errors["base"] = "no_controllers"
                else:
                    return self.async_create_entry(
                        title="",
                        data={
                            key: value
                            for key, value in self._draft.items()
                            if key not in (CONF_NAME, CONF_SENSOR)
                        },
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                "thermostat_settings",
                                "controllers_menu",
                                "windows_menu",
                                "presets_menu",
                                "save",
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="options_action_selector",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "name": self._draft[CONF_NAME],
                "sensor": self._draft[CONF_SENSOR],
                "heaters": self._format_entities(self._draft[CONF_HEATER]),
                "coolers": self._format_entities(self._draft[CONF_COOLER]),
                "windows": self._format_entities(self._draft[CONF_WINDOWS]),
                "presets": self._format_presets(),
            },
        )

    async def async_step_thermostat_settings(
        self, user_input: dict[str, Any] | None = None
    ):
        """Manage general thermostat settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            min_temp = user_input[CONF_MIN_TEMP]
            max_temp = user_input[CONF_MAX_TEMP]

            if min_temp >= max_temp:
                errors["base"] = "invalid_temp_range"
            else:
                self._draft[CONF_MIN_TEMP] = min_temp
                self._draft[CONF_MAX_TEMP] = max_temp
                self._draft[CONF_HEAT_COOL_DISABLED] = user_input[
                    CONF_HEAT_COOL_DISABLED
                ]
                self._draft[CONF_AUTO_MODE_DISABLED] = user_input[
                    CONF_AUTO_MODE_DISABLED
                ]
                self._draft[CONF_AUTO_COOL_DELTA] = user_input.get(
                    CONF_AUTO_COOL_DELTA, DEFAULT_AUTO_COOL_DELTA
                )
                self._draft[CONF_AUTO_HEAT_DELTA] = user_input.get(
                    CONF_AUTO_HEAT_DELTA, DEFAULT_AUTO_HEAT_DELTA
                )

                return await self.async_step_init()

        return self.async_show_form(
            step_id="thermostat_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MIN_TEMP, default=self._draft[CONF_MIN_TEMP]
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=100, step=1.0)
                    ),
                    vol.Required(
                        CONF_MAX_TEMP, default=self._draft[CONF_MAX_TEMP]
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=100, step=1.0)
                    ),
                    vol.Required(
                        CONF_HEAT_COOL_DISABLED,
                        default=self._draft[CONF_HEAT_COOL_DISABLED],
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_AUTO_MODE_DISABLED,
                        default=self._draft[CONF_AUTO_MODE_DISABLED],
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_AUTO_COOL_DELTA,
                        default=self._draft[CONF_AUTO_COOL_DELTA],
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=50, step=0.1)
                    ),
                    vol.Optional(
                        CONF_AUTO_HEAT_DELTA,
                        default=self._draft[CONF_AUTO_HEAT_DELTA],
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=50, step=0.1)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_controllers_menu(
        self, user_input: dict[str, Any] | None = None
    ):
        """Manage controller actions."""
        if user_input is not None:
            action = user_input["action"]

            if action == "add":
                return await self.async_step_controller_add()
            if action == "edit":
                return await self.async_step_controller_edit()
            if action == "remove":
                return await self.async_step_controller_remove()
            return await self.async_step_init()

        options = ["add"]
        if self._draft[CONF_HEATER] or self._draft[CONF_COOLER]:
            options.append("edit")
            options.append("remove")

        options.append("done")

        return self.async_show_form(
            step_id="controllers_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controllers_menu_selector",
                        )
                    ),
                }
            ),
            description_placeholders={
                "heaters": self._format_entities(self._draft[CONF_HEATER]),
                "coolers": self._format_entities(self._draft[CONF_COOLER]),
            },
        )

    async def async_step_controller_add(self, user_input: dict[str, Any] | None = None):
        """Add a heater or cooler entity."""
        if user_input is not None:
            entity_id = user_input[CONF_ENTITY_ID]
            self._cur_ctrl_type = user_input["controller_type"]
            self._cur_controller = {CONF_ENTITY_ID: entity_id}

            current_domain = split_entity_id(entity_id)[0]
            if current_domain in (NUMBER_DOMAIN, INPUT_NUMBER_DOMAIN):
                self._cur_ctrl_cfg_type = CTRL_CFG_NUMBER_PID
                return await self.async_step_controller_config()

            return await self.async_step_controller_mode()

        return self.async_show_form(
            step_id="controller_add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SUPPORTED_TARGET_DOMAINS)
                    ),
                    vol.Required("controller_type"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[CONF_HEATER, CONF_COOLER],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controller_add_selector",
                        )
                    ),
                }
            ),
        )

    async def async_step_controller_mode(
        self, user_input: dict[str, Any] | None = None
    ):
        """Choose controller mode depending on entity domain."""
        ctrl_domain = split_entity_id(self._cur_controller[CONF_ENTITY_ID])[0]

        if user_input is not None:
            mode = user_input["controller_mode"]

            if ctrl_domain in (SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN):
                if mode == CTRL_CFG_SWITCH:
                    self._cur_ctrl_cfg_type = CTRL_CFG_SWITCH
                else:
                    self._cur_ctrl_cfg_type = CTRL_CFG_PWM_SWITCH

            elif ctrl_domain == CLIMATE_DOMAIN:
                if mode == CTRL_CFG_CLIMATE_SWITCH:
                    self._cur_ctrl_cfg_type = CTRL_CFG_CLIMATE_SWITCH
                else:
                    self._cur_ctrl_cfg_type = CTRL_CFG_CLIMATE_PID

            return await self.async_step_controller_config()

        options: list[dict[str, str]] = []
        if ctrl_domain in (SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN):
            options = [CTRL_CFG_SWITCH, CTRL_CFG_PWM_SWITCH]
        elif ctrl_domain == CLIMATE_DOMAIN:
            options = [CTRL_CFG_CLIMATE_SWITCH, CTRL_CFG_CLIMATE_PID]

        return self.async_show_form(
            step_id="controller_mode",
            data_schema=vol.Schema(
                {
                    vol.Required("controller_mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controller_mode_selector",
                        )
                    )
                }
            ),
            description_placeholders={
                "current_entity_id": self._cur_controller[CONF_ENTITY_ID],
                "controller_type": self._cur_ctrl_type,
            },
        )

    async def async_step_controller_config(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure selected controller."""
        if user_input is not None:
            controller = dict(self._cur_controller)
            controller.update(user_input)
            controller = self._clear_fields(controller)

            if self._cur_ctrl_index is None:
                self._draft[self._cur_ctrl_type].append(controller)
            else:
                self._draft[self._cur_ctrl_type][self._cur_ctrl_index] = controller

            self._cur_ctrl_type = None
            self._cur_controller = {}
            self._cur_ctrl_index = None
            self._cur_ctrl_cfg_type = None

            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config",
            data_schema=vol.Schema(self._get_current_ctrl_schema()),
            description_placeholders={
                "current_entity_id": self._cur_controller[CONF_ENTITY_ID],
                "controller_type": self._cur_ctrl_type,
                "controller_config_type": self._cur_ctrl_cfg_type,
            },
        )

    async def async_step_controller_edit(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit a heater or cooler entity."""
        if user_input is not None:
            controller_type, index = user_input["controller"].split(":")
            self._cur_ctrl_type = controller_type
            self._cur_ctrl_index = int(index)
            self._cur_controller = dict(
                self._draft[controller_type][self._cur_ctrl_index]
            )
            return await self.async_step_controller_config()

        return self.async_show_form(
            step_id="controller_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("controller"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._get_ctrl_list_options(),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_controller_remove(
        self, user_input: dict[str, Any] | None = None
    ):
        """Remove a heater or cooler entity."""
        if user_input is not None:
            controller_type, index = user_input["controller"].split(":")
            self._draft[controller_type].pop(int(index))

            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("controller"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._get_ctrl_list_options(),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_windows_menu(self, user_input: dict[str, Any] | None = None):
        """Manage window actions."""
        if user_input is not None:
            action = user_input["action"]

            if action == "add":
                return await self.async_step_window_add()
            if action == "edit":
                return await self.async_step_window_edit()
            if action == "remove":
                return await self.async_step_window_remove()
            return await self.async_step_init()

        options = ["add"]
        if self._draft[CONF_WINDOWS]:
            options.append("edit")
            options.append("remove")

        options.append("done")

        return self.async_show_form(
            step_id="windows_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="windows_menu_selector",
                        )
                    ),
                }
            ),
            description_placeholders={
                "windows": self._format_entities(self._draft[CONF_WINDOWS]),
            },
        )

    async def async_step_window_add(self, user_input: dict[str, Any] | None = None):
        """Add a window entity."""
        if user_input is not None:
            self._draft[CONF_WINDOWS].append(user_input)
            return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="window_add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SUPPORTED_WINDOW_DOMAINS)
                    ),
                    vol.Required(
                        CONF_INVERTED, default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(ATTR_TIMEOUT): vol.Any(
                        None,
                        selector.DurationSelector(
                            selector.DurationSelectorConfig(allow_negative=False)
                        ),
                    ),
                }
            ),
        )

    async def async_step_window_edit(self, user_input: dict[str, Any] | None = None):
        """Edit a window entity."""
        if user_input is not None:
            self._cur_window_index = int(user_input["window"])
            self._cur_window = dict(self._draft[CONF_WINDOWS][self._cur_window_index])
            return await self.async_step_window_config()

        return self.async_show_form(
            step_id="window_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("window"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": str(index),
                                    "label": window[CONF_ENTITY_ID],
                                }
                                for index, window in enumerate(
                                    self._draft[CONF_WINDOWS]
                                )
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_window_config(self, user_input: dict[str, Any] | None = None):
        """Configure selected window."""
        if user_input is not None:
            window = dict(self._draft[CONF_WINDOWS][self._cur_window_index])
            window.update(user_input)
            window = self._clear_fields(window)
            self._draft[CONF_WINDOWS][self._cur_window_index] = window

            self._cur_window = {}
            self._cur_window_index = None

            return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="window_config",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENTITY_ID, default=self._cur_window[CONF_ENTITY_ID]
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            read_only=True,
                        )
                    ),
                    vol.Required(
                        CONF_INVERTED,
                        default=self._draft[CONF_WINDOWS][self._cur_window_index].get(
                            CONF_INVERTED, False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        ATTR_TIMEOUT,
                        default=self._draft[CONF_WINDOWS][self._cur_window_index].get(
                            ATTR_TIMEOUT, None
                        ),
                    ): vol.Any(
                        None,
                        selector.DurationSelector(
                            selector.DurationSelectorConfig(allow_negative=False)
                        ),
                    ),
                    **self._clear_flag_schema(self._cur_window, ATTR_TIMEOUT),
                }
            ),
        )

    async def async_step_window_remove(self, user_input: dict[str, Any] | None = None):
        """Remove a window entity."""
        if user_input is not None:
            self._draft[CONF_WINDOWS].pop(int(user_input["window"]))

            return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="window_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("window"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": str(index),
                                    "label": window[CONF_ENTITY_ID],
                                }
                                for index, window in enumerate(
                                    self._draft[CONF_WINDOWS]
                                )
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_presets_menu(self, user_input: dict[str, Any] | None = None):
        """Manage preset actions."""
        if user_input is not None:
            action = user_input["action"]

            if action == "add":
                return await self.async_step_preset_add()
            if action == "edit":
                return await self.async_step_preset_edit()
            if action == "remove":
                return await self.async_step_preset_remove()
            return await self.async_step_init()

        options = ["add"]
        if self._draft[CONF_PRESETS]:
            options.append("edit")
            options.append("remove")

        options.append("done")

        return self.async_show_form(
            step_id="presets_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="presets_menu_selector",
                        )
                    ),
                }
            ),
            description_placeholders={
                "presets": self._format_presets(),
            },
        )

    async def async_step_preset_add(self, user_input: dict[str, Any] | None = None):
        """Add a preset."""
        errors: dict[str, str] = {}

        if user_input is not None:
            preset_name = user_input["preset_name"]
            if preset_name in self._draft["presets"]:
                errors["preset_name"] = "preset_exists"
            else:
                self._cur_preset_name = preset_name
                self._cur_preset_type = user_input["preset_type"]
                self._draft[CONF_PRESETS][self._cur_preset_name] = {}

                return await self.async_step_preset_config()

        return self.async_show_form(
            step_id="preset_add",
            data_schema=vol.Schema(
                {
                    vol.Required("preset_name"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                PRESET_ECO,
                                PRESET_AWAY,
                                PRESET_BOOST,
                                PRESET_COMFORT,
                                PRESET_SLEEP,
                                PRESET_ACTIVITY,
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="preset_name_selector",
                        )
                    ),
                    vol.Required("preset_type"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                PRESET_TYPE_TEMP_DELTA,
                                PRESET_TYPE_HEAT_COOL_DELTAS,
                                PRESET_TYPE_TARGET_TEMPS,
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="preset_type_selector",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_preset_config(self, user_input: dict[str, Any] | None = None):
        """Configure temp_delta preset."""
        errors: dict[str, str] = {}

        if user_input is not None:
            preset_cfg = dict(self._draft[CONF_PRESETS][self._cur_preset_name])
            preset_cfg.update(user_input)
            preset_cfg = self._clear_fields(preset_cfg)

            if self._cur_preset_type == PRESET_TYPE_TARGET_TEMPS and not any(
                preset_cfg.get(field) is not None
                for field in (
                    CONF_PRESET_TARGET_TEMP,
                    CONF_PRESET_HEAT_TARGET_TEMP,
                    CONF_PRESET_COOL_TARGET_TEMP,
                )
            ):
                errors["base"] = "preset_target_required"
            else:
                self._draft[CONF_PRESETS][self._cur_preset_name] = preset_cfg

                self._cur_preset_name = None
                self._cur_preset_type = None

                return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="preset_config",
            data_schema=vol.Schema(self._get_current_preset_schema()),
            description_placeholders={"current_preset": self._cur_preset_name},
            errors=errors,
        )

    async def async_step_preset_edit(self, user_input: dict[str, Any] | None = None):
        """Edit a preset."""
        if user_input is not None:
            self._cur_preset_name = user_input["preset_name"]
            return await self.async_step_preset_config()

        return self.async_show_form(
            step_id="preset_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("preset_name"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(self._draft[CONF_PRESETS].keys()),
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="preset_name_selector",
                        )
                    )
                }
            ),
        )

    async def async_step_preset_remove(self, user_input: dict[str, Any] | None = None):
        """Remove a preset."""
        if user_input is not None:
            self._draft[CONF_PRESETS].pop(user_input["preset"], None)
            return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="preset_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("preset"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(self._draft[CONF_PRESETS].keys()),
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="preset_type_selector",
                        )
                    )
                }
            ),
        )

    def _get_current_ctrl_schema(self) -> dict:
        """Return schema for currently selected controller config type."""
        if self._cur_ctrl_cfg_type is None:
            domain = split_entity_id(self._cur_controller[CONF_ENTITY_ID])[0]
            if domain in (SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN):
                if CONF_PID_KP in self._cur_controller:
                    self._cur_ctrl_cfg_type = CTRL_CFG_PWM_SWITCH
                else:
                    self._cur_ctrl_cfg_type = CTRL_CFG_SWITCH

            elif domain == CLIMATE_DOMAIN:
                if CONF_PID_KP in self._cur_controller:
                    self._cur_ctrl_cfg_type = CTRL_CFG_CLIMATE_PID
                else:
                    self._cur_ctrl_cfg_type = CTRL_CFG_CLIMATE_SWITCH
            else:
                self._cur_ctrl_cfg_type = CTRL_CFG_NUMBER_PID

        if self._cur_ctrl_cfg_type == CTRL_CFG_SWITCH:
            return self._build_switch_ctrl_schema()

        if self._cur_ctrl_cfg_type == CTRL_CFG_PWM_SWITCH:
            return self._build_pwm_switch_ctrl_schema()

        if self._cur_ctrl_cfg_type == CTRL_CFG_CLIMATE_SWITCH:
            return self._build_climate_ctrl_schema()

        if self._cur_ctrl_cfg_type == CTRL_CFG_CLIMATE_PID:
            return self._build_climate_pid_ctrl_schema()

        if self._cur_ctrl_cfg_type == CTRL_CFG_NUMBER_PID:
            return self._build_number_pid_ctrl_schema()

        raise ValueError(
            f"Unsupported controller config type: {self._cur_ctrl_cfg_type}"
        )

    def _common_ctrl_schema(self) -> dict:
        """Return common controller fields."""
        return {
            vol.Required(
                CONF_INVERTED,
                default=self._cur_controller.get(CONF_INVERTED, False),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_IGNORE_WINDOWS,
                default=self._cur_controller.get(CONF_IGNORE_WINDOWS, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_KEEP_ALIVE,
                default=self._cur_controller.get(CONF_KEEP_ALIVE, None),
            ): selector.DurationSelector(
                selector.DurationSelectorConfig(allow_negative=False)
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_KEEP_ALIVE),
        }

    def _pid_schema(self) -> dict:
        return {
            vol.Required(
                CONF_PID_KP,
                default=self._cur_controller.get(CONF_PID_KP, DEFAULT_PID_KP),
            ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
            vol.Required(
                CONF_PID_KI,
                default=self._cur_controller.get(CONF_PID_KI, DEFAULT_PID_KI),
            ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.001)),
            vol.Required(
                CONF_PID_KD,
                default=self._cur_controller.get(CONF_PID_KD, DEFAULT_PID_KD),
            ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
            vol.Optional(
                CONF_PID_SAMPLE_PERIOD,
                default=self._cur_controller.get(CONF_PID_SAMPLE_PERIOD, None),
            ): selector.DurationSelector(
                selector.DurationSelectorConfig(allow_negative=False)
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_PID_SAMPLE_PERIOD),
        }

    def _pid_limits_schema(self) -> dict:
        return {
            vol.Optional(
                CONF_PID_MIN, default=self._cur_controller.get(CONF_PID_MIN, None)
            ): vol.Any(
                None, selector.NumberSelector(selector.NumberSelectorConfig(step=1.0))
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_PID_MIN),
            vol.Optional(
                CONF_PID_MAX, default=self._cur_controller.get(CONF_PID_MAX, None)
            ): vol.Any(
                None, selector.NumberSelector(selector.NumberSelectorConfig(step=1.0))
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_PID_MAX),
        }

    def _build_switch_ctrl_schema(self) -> dict:
        return {
            **self._common_ctrl_schema(),
            vol.Required(
                CONF_COLD_TOLERANCE,
                default=self._cur_controller.get(
                    CONF_COLD_TOLERANCE, DEFAULT_COLD_TOLERANCE
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=20, step=0.1)
            ),
            vol.Required(
                CONF_HOT_TOLERANCE,
                default=self._cur_controller.get(
                    CONF_HOT_TOLERANCE, DEFAULT_HOT_TOLERANCE
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=20, step=0.1)
            ),
            vol.Optional(
                CONF_MIN_DUR, default=self._cur_controller.get(CONF_MIN_DUR, None)
            ): vol.Any(
                None,
                selector.DurationSelector(
                    selector.DurationSelectorConfig(allow_negative=False)
                ),
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_MIN_DUR),
        }

    def _build_pwm_switch_ctrl_schema(self) -> dict:
        return {
            **self._common_ctrl_schema(),
            **self._pid_schema(),
            vol.Required(
                CONF_PWM_SWITCH_PERIOD,
                default=self._cur_controller.get(CONF_PWM_SWITCH_PERIOD, None),
            ): selector.DurationSelector(
                selector.DurationSelectorConfig(allow_negative=False)
            ),
        }

    def _build_climate_ctrl_schema(self) -> dict:
        return {
            **self._common_ctrl_schema(),
            vol.Required(
                CONF_COLD_TOLERANCE,
                default=self._cur_controller.get(
                    CONF_COLD_TOLERANCE, DEFAULT_COLD_TOLERANCE
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=20, step=0.1)
            ),
            vol.Required(
                CONF_HOT_TOLERANCE,
                default=self._cur_controller.get(
                    CONF_HOT_TOLERANCE, DEFAULT_HOT_TOLERANCE
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=20, step=0.1)
            ),
            vol.Optional(
                CONF_CLIMATE_TEMP_DELTA,
                default=self._cur_controller.get(CONF_CLIMATE_TEMP_DELTA, None),
            ): vol.Any(
                None,
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
                ),
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_CLIMATE_TEMP_DELTA),
            vol.Optional(
                CONF_MIN_DUR, default=self._cur_controller.get(CONF_MIN_DUR, None)
            ): selector.DurationSelector(
                selector.DurationSelectorConfig(allow_negative=False)
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_MIN_DUR),
        }

    def _build_climate_pid_ctrl_schema(self) -> dict:
        return {
            **self._common_ctrl_schema(),
            **self._pid_schema(),
            **self._pid_limits_schema(),
        }

    def _build_number_pid_ctrl_schema(self) -> dict:
        return {
            **self._common_ctrl_schema(),
            **self._pid_schema(),
            **self._pid_limits_schema(),
            vol.Optional(
                CONF_PID_SWITCH_ENTITY_ID,
                default=self._cur_controller.get(CONF_PID_SWITCH_ENTITY_ID, None),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=[SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]
                )
            ),
            **self._clear_flag_schema(self._cur_controller, CONF_PID_SWITCH_ENTITY_ID),
            vol.Required(
                CONF_PID_SWITCH_INVERTED,
                default=self._cur_controller.get(CONF_PID_SWITCH_INVERTED, False),
            ): selector.BooleanSelector(),
        }

    def _get_current_preset_schema(self) -> dict:
        """Return schema for currently selected preset type."""
        if self._cur_preset_type is None:
            preset_cfg = self._draft[CONF_PRESETS][self._cur_preset_name]
            if CONF_PRESET_TEMP_DELTA in preset_cfg:
                self._cur_preset_type = PRESET_TYPE_TEMP_DELTA
            elif CONF_PRESET_COOL_DELTA in preset_cfg:
                self._cur_preset_type = PRESET_TYPE_HEAT_COOL_DELTAS
            else:
                self._cur_preset_type = PRESET_TYPE_TARGET_TEMPS

        if self._cur_preset_type == PRESET_TYPE_TEMP_DELTA:
            return self._build_temp_delta_preset_schema()

        if self._cur_preset_type == PRESET_TYPE_HEAT_COOL_DELTAS:
            return self._build_heat_cool_deltas_preset_schema()

        if self._cur_preset_type == PRESET_TYPE_TARGET_TEMPS:
            return self._build_target_temps_preset_schema()

        raise ValueError(f"Unsupported preset config type: {self._cur_preset_type}")

    def _build_temp_delta_preset_schema(self) -> dict:
        return {
            vol.Required(
                CONF_PRESET_TEMP_DELTA,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_TEMP_DELTA, "0.0"
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
            )
        }

    def _build_heat_cool_deltas_preset_schema(self) -> dict:
        return {
            vol.Required(
                CONF_PRESET_HEAT_DELTA,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_HEAT_DELTA, "0.0"
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
            ),
            vol.Required(
                CONF_PRESET_COOL_DELTA,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_COOL_DELTA, "0.0"
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
            ),
        }

    def _build_target_temps_preset_schema(self) -> dict:
        return {
            vol.Optional(
                CONF_PRESET_TARGET_TEMP,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_TARGET_TEMP, None
                ),
            ): vol.Any(
                None,
                selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
            ),
            **self._clear_flag_schema(
                self._draft[CONF_PRESETS][self._cur_preset_name],
                CONF_PRESET_TARGET_TEMP,
            ),
            vol.Optional(
                CONF_PRESET_HEAT_TARGET_TEMP,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_HEAT_TARGET_TEMP, None
                ),
            ): vol.Any(
                None,
                selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
            ),
            **self._clear_flag_schema(
                self._draft[CONF_PRESETS][self._cur_preset_name],
                CONF_PRESET_HEAT_TARGET_TEMP,
            ),
            vol.Optional(
                CONF_PRESET_COOL_TARGET_TEMP,
                default=self._draft[CONF_PRESETS][self._cur_preset_name].get(
                    CONF_PRESET_COOL_TARGET_TEMP, None
                ),
            ): vol.Any(
                None,
                selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
            ),
            **self._clear_flag_schema(
                self._draft[CONF_PRESETS][self._cur_preset_name],
                CONF_PRESET_COOL_TARGET_TEMP,
            ),
        }

    def _clear_flag_schema(self, ctrl: dict, key: str) -> dict:
        """Return schema for clearing a controller field."""
        if key not in ctrl:
            return {}
        return {
            vol.Optional(f"{CLEAR_FIELD_PREFIX}{key}", default=False): (
                selector.BooleanSelector()
            )
        }

    def _clear_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Remove clear flags from user input and return fields to clear."""
        flags = {flag for flag in data if flag.startswith(CLEAR_FIELD_PREFIX)}
        for flag in flags:
            if data[flag]:
                data.pop(flag.removeprefix(CLEAR_FIELD_PREFIX), None)
            data.pop(flag, None)
        return data

    def _get_ctrl_list_options(self) -> list[dict[str, str]]:
        """Return controller selector options."""
        options = []
        for controller_type in (CONF_HEATER, CONF_COOLER):
            options.extend(
                {
                    "value": (f"{controller_type}:{index}"),
                    "label": f"{controller[CONF_ENTITY_ID]} ({controller_type})",
                }
                for index, controller in enumerate(self._draft[controller_type])
            )
        return options

    def _format_entities(self, items: list[dict[str, Any]]) -> str:
        """Format entity list for descriptions."""
        if not items:
            return "—"
        return "\n".join(f"- {item['entity_id']}" for item in items)

    def _format_presets(self) -> str:
        """Format presets list for descriptions."""
        if not self._draft["presets"]:
            return "—"
        return "\n".join(f"- {name}" for name in self._draft["presets"])
