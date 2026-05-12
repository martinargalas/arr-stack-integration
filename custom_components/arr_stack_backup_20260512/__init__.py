"""Arr Stack — HTTP proxy integrace pro arr-stack-card."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .views import ArrStackProxyView


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Spustí proxy view po načtení config entry."""
    hass.http.register_view(ArrStackProxyView(hass, dict(entry.data)))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
