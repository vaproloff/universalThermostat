"""Templates render utils."""

from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template


def render_float(value: Template | float | None, default: float) -> float:
    """Render template-like value to float or return default."""
    if value is None:
        return float(default)

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value.async_render(parse_result=False))
    except (TemplateError, TypeError, ValueError, AttributeError):
        return float(default)


def get_template_entities(value: Template | float | None) -> list[str]:
    """Return entities referenced by template-like value."""
    if not isinstance(value, Template):
        return []

    try:
        info: RenderInfo = value.async_render_to_info()
    except (TemplateError, TypeError):
        return []

    return list(info.entities)
