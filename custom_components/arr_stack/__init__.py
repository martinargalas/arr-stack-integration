"""Arr Stack — HTTP proxy integrace pro arr-stack-card."""
from homeassistant.components.persistent_notification import async_create as pn_create
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .views import ArrStackProxyView


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Spustí proxy view po načtení config entry."""
    hass.http.register_view(ArrStackProxyView(hass, dict(entry.data)))

    pn_create(
        hass,
        "Arr Stack settings were saved. **Restart Home Assistant** to apply the changes.",
        title="Arr Stack — Restart required",
        notification_id="arr_stack_restart_required",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
