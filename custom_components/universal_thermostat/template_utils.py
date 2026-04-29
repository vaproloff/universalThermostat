"""Templates render utils."""

import logging

from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template


def render_float(
    value: Template | float | None,
    default: float | None,
    *,
    owner: str | None = None,
    field: str | None = None,
    logger: logging.Logger | None = None,
) -> float | None:
    """Render template-like value to float or return default."""
    if value is None:
        return float(default)

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value.async_render(parse_result=False))
    except (TemplateError, TypeError, ValueError, AttributeError) as err:
        logger.warning(
            "%s: unable to render %s as float: %s. Falling back to %s. Error: %s",
            owner,
            field,
            value,
            default,
            err,
        )
        return float(default) if default is not None else None


def get_template_entities(
    value: Template | float | None,
    *,
    owner: str | None = None,
    field: str | None = None,
    logger: logging.Logger | None = None,
) -> list[str]:
    """Return entities referenced by template-like value."""
    if not isinstance(value, Template):
        return []

    try:
        info: RenderInfo = value.async_render_to_info()
    except (TemplateError, TypeError) as err:
        logger.warning(
            "%s: unable to inspect entities for %s template: %s. Error: %s",
            owner,
            field,
            value,
            err,
        )
        return []

    return list(info.entities)
