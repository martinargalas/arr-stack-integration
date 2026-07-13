"""Arr Stack — HTTP proxy integrace pro arr-stack-card."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, CONF_DEBUG_LOGGING
from .views import ArrStackProxyView

# Sdílený package logger — nastavením úrovně tady se řídí i moduly, které volají
# logging.getLogger(__name__) (views.py apod., protože __name__ v podmodulu
# dědí efektivní úroveň od nadřazeného loggeru "custom_components.arr_stack").
_PKG_LOGGER = logging.getLogger(__package__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Aktualizuj config — view ho čte dynamicky, žádný restart není potřeba
    hass.data[DOMAIN]["config"] = dict(entry.data)

    # "Enable debug logging" v integraci — nastaví úroveň loggeru bez nutnosti
    # editovat configuration.yaml. Vypnutím se vrátí na výchozí (NOTSET → dědí od root).
    _PKG_LOGGER.setLevel(logging.DEBUG if entry.data.get(CONF_DEBUG_LOGGING) else logging.NOTSET)

    # View zaregistruj jen jednou (hass.data se maže při restartu HA)
    if not hass.data[DOMAIN].get("view_registered"):
        hass.http.register_view(ArrStackProxyView(hass))
        hass.data[DOMAIN]["view_registered"] = True

    # Po restartu smažeme případný starý repair issue
    ir.async_delete_issue(hass, DOMAIN, "restart_required")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
