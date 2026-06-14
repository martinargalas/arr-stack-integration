"""Config flow — dynamic step selection."""
import base64
import logging
import socket
from urllib.parse import urlparse
import aiohttp
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

from homeassistant import config_entries
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS,
    CONF_SAB_URL, CONF_SAB_KEY,
    CONF_NZBGET_URL, CONF_NZBGET_USER, CONF_NZBGET_PASS,
    CONF_DELUGE_URL, CONF_DELUGE_PASS,
    CONF_RTORRENT_URL, CONF_RTORRENT_USER, CONF_RTORRENT_PASS,
    CONF_RADARR_URL, CONF_RADARR_KEY,
    CONF_RADARR2_URL, CONF_RADARR2_KEY,
    CONF_SONARR_URL, CONF_SONARR_KEY,
    CONF_SONARR2_URL, CONF_SONARR2_KEY,
    CONF_SEERR_URL, CONF_SEERR_KEY,
    CONF_SEERR_FAMILY_EMAIL, CONF_SEERR_FAMILY_PASS,
    CONF_BAZARR_URL, CONF_BAZARR_KEY,
    CONF_PLEX_TOKEN, CONF_PLEX_URL, PLEX_CLIENT_ID,
    CONF_EMBY_URL, CONF_EMBY_KEY,
    CONF_TAUTULLI_URL, CONF_TAUTULLI_KEY,
    CONF_JELLYSTAT_URL, CONF_JELLYSTAT_KEY,
    CONF_TRAKT_CLIENT_ID, CONF_TRAKT_CLIENT_SECRET,
    CONF_TRAKT_ACCESS_TOKEN, CONF_TRAKT_REFRESH_TOKEN, CONF_TRAKT_EXPIRES_AT,
    TRAKT_API_BASE,
    CONF_PROWLARR_URL, CONF_PROWLARR_KEY,
    CONF_SKIP_SSL_VERIFY,
)


# ── Pomocné funkce pro chyby ─────────────────────────────────────────────────

def _url_error(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        return "invalid_url"
    return None

def _log_exc(service: str, url: str, e: Exception) -> str:
    """Log connection exception with actionable detail, return error key."""
    err_str = str(e)
    if isinstance(e, aiohttp.ClientConnectorError):
        dns_markers = ("nodename nor servname", "Name or service not known", "getaddrinfo failed", "Temporary failure in name resolution")
        if any(m in err_str for m in dns_markers):
            parsed = urlparse(url)
            hostname = parsed.hostname or url
            port = parsed.port or parsed.scheme

            # OS-level error detail
            os_err = getattr(e, "os_error", None)
            os_detail = ""
            if os_err:
                errno_val = getattr(os_err, "errno", None)
                strerror = getattr(os_err, "strerror", None)
                if errno_val and strerror:
                    os_detail = f" [errno {errno_val}: {strerror}]"
                elif strerror:
                    os_detail = f" [{strerror}]"

            # .local domains need mDNS which doesn't work in Docker
            local_hint = (
                " '.local' domains use mDNS which does not work inside Docker containers —"
                " use an IP address or a regular DNS name instead."
                if hostname.endswith(".local") else ""
            )

            _LOGGER.warning(
                "arr_stack [%s] DNS resolution failed — cannot resolve hostname '%s' (port %s).%s"
                " Home Assistant's DNS server does not know this name."
                " Fixes: (1) use an IP address instead of a domain name,"
                " (2) set a local DNS server in your Docker Compose (dns: key),"
                " (3) add a hosts entry in HA's /etc/hosts via a customisation."
                " Full URL tested: %s%s",
                service, hostname, port, local_hint, url, os_detail,
            )
        elif "Connection refused" in err_str:
            _LOGGER.warning(
                "arr_stack [%s] connection refused at %s — "
                "service is not running or the port is wrong. Detail: %s",
                service, url, e,
            )
        elif "Network unreachable" in err_str or "No route to host" in err_str:
            _LOGGER.warning(
                "arr_stack [%s] network unreachable for %s — "
                "check firewall rules or VLAN routing between HA and the service. Detail: %s",
                service, url, e,
            )
        elif "timed out" in err_str or "ConnectTimeoutError" in type(e).__name__:
            _LOGGER.warning(
                "arr_stack [%s] connection timed out for %s — "
                "host exists but is not responding (firewall drop, wrong IP?). Detail: %s",
                service, url, e,
            )
        else:
            _LOGGER.warning("arr_stack [%s] cannot connect to %s — %s: %s", service, url, type(e).__name__, e)
        return "cannot_connect"
    if isinstance(e, aiohttp.ClientSSLError):
        _LOGGER.warning(
            "arr_stack [%s] SSL error for %s — "
            "if using a self-signed certificate, enable 'Skip SSL certificate verification' "
            "in Global Settings. Detail: %s",
            service, url, e,
        )
        return "ssl_error"
    if isinstance(e, aiohttp.ServerTimeoutError):
        _LOGGER.warning(
            "arr_stack [%s] server timeout for %s (8 s) — "
            "service is reachable but not responding in time.",
            service, url,
        )
        return "timeout"
    if isinstance(e, aiohttp.InvalidURL):
        _LOGGER.warning("arr_stack [%s] invalid URL '%s' — %s", service, url, e)
        return "invalid_url"
    _LOGGER.error(
        "arr_stack [%s] unexpected error for %s — %s: %s",
        service, url, type(e).__name__, e,
    )
    return "unknown"


# ── Validační funkce ─────────────────────────────────────────────────────────

async def _test_qbit(session: aiohttp.ClientSession, url: str, user: str, password: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api/v2/auth/login"
    _LOGGER.debug("arr_stack [qbittorrent] testing connection → %s", test_url)
    try:
        base = url.rstrip('/')
        async with session.post(
            test_url,
            data={"username": user, "password": password},
            headers={"Origin": base, "Referer": base + "/"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            text = await r.text()
            if r.status in (200, 204) or text.strip().lower() in ("ok.", "ok"):
                return None
            if text.strip() == "Fails." or r.status == 403 and "Fails" in text:
                return "qbit_bad_credentials"
            if r.status == 403 or "Forbidden" in text:
                return "qbit_forbidden"
            if r.status == 401 or "Unauthorized" in text:
                return "qbit_bad_credentials"
            return "qbit_login_failed"
    except Exception as e:
        return _log_exc("qbittorrent", test_url, e)


async def _test_sabnzbd(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api"
    _LOGGER.debug("arr_stack [sabnzbd] testing connection → %s", test_url)
    try:
        async with session.get(
            test_url,
            params={"mode": "version", "output": "json", "apikey": key},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 200:
                data = await r.json()
                if data.get("version"):
                    return None
            if r.status == 403:
                return "sabnzbd_bad_key"
            return "sabnzbd_bad_key"
    except Exception as e:
        return _log_exc("sabnzbd", test_url, e)


async def _test_nzbget(session: aiohttp.ClientSession, url: str, user: str, password: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    rpc_url = f"{url.rstrip('/')}/jsonrpc"
    _LOGGER.debug("arr_stack [nzbget] testing connection → %s", rpc_url)
    try:
        creds = f"{user or 'nzbget'}:{password or ''}"
        auth_header = base64.b64encode(creds.encode('utf-8')).decode('ascii')
        headers = {"Authorization": f"Basic {auth_header}"}
        async with session.post(
            rpc_url,
            json={"method": "version", "params": []},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 401:
                _LOGGER.warning("arr_stack [nzbget] HTTP 401 at %s — wrong username/password", rpc_url)
                return "invalid_auth"
            if r.status != 200:
                _LOGGER.warning("arr_stack [nzbget] HTTP %s at %s", r.status, rpc_url)
                return "cannot_connect"
            data = await r.json()
            if "result" not in data:
                return "cannot_connect"
            return None
    except Exception as e:
        return _log_exc("nzbget", rpc_url, e)


async def _test_deluge(session: aiohttp.ClientSession, url: str, password: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    rpc_url = f"{url.rstrip('/')}/json"
    _LOGGER.debug("arr_stack [deluge] testing connection → %s", rpc_url)
    try:
        async with session.post(
            rpc_url,
            json={"method": "auth.login", "params": [password or ""], "id": 1},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 401:
                return "invalid_auth"
            if r.status != 200:
                return "cannot_connect"
            data = await r.json()
            if data.get("result") is False:
                return "invalid_auth"
            return None
    except Exception as e:
        return _log_exc("deluge", rpc_url, e)


async def _test_rtorrent(session: aiohttp.ClientSession, url: str, user: str, password: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    import xmlrpc.client as xmlrpc
    rpc_url = f"{url.rstrip('/')}/RPC2"
    _LOGGER.debug("arr_stack [rtorrent] testing connection → %s", rpc_url)
    try:
        body = xmlrpc.dumps((), "system.listMethods")
        auth = aiohttp.BasicAuth(user, password) if user else None
        async with session.post(
            rpc_url,
            data=body,
            headers={"Content-Type": "text/xml"},
            auth=auth,
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 401:
                return "invalid_auth"
            if r.status not in (200, 201):
                return "cannot_connect"
            return None
    except Exception as e:
        return _log_exc("rtorrent", rpc_url, e)


async def _test_arr(session: aiohttp.ClientSession, url: str, key: str, name: str, ssl=None) -> str | None:
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api/v3/system/status"
    _LOGGER.debug("arr_stack [%s] testing connection → %s (ssl_verify=%s)", name, test_url, ssl)
    try:
        async with session.get(
            test_url,
            headers={"X-Api-Key": key},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            _LOGGER.debug("arr_stack [%s] response status=%s", name, r.status)
            if r.status == 200:
                return None
            if r.status == 401:
                _LOGGER.warning("arr_stack [%s] API key rejected (HTTP 401) for %s", name, test_url)
                return f"{name}_bad_key"
            if r.status == 404:
                _LOGGER.warning(
                    "arr_stack [%s] HTTP 404 for %s — wrong base URL or port (got HTML instead of API response?)",
                    name, test_url,
                )
                return f"{name}_wrong_port"
            _LOGGER.warning("arr_stack [%s] unexpected HTTP %s for %s", name, r.status, test_url)
            return f"{name}_error"
    except Exception as e:
        return _log_exc(name, test_url, e)


async def _test_overseerr(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api/v1/settings/about"
    _LOGGER.debug("arr_stack [overseerr] testing connection → %s", test_url)
    try:
        async with session.get(
            test_url,
            headers={"X-Api-Key": key, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 200:
                return None
            if r.status == 401:
                return "overseerr_bad_key"
            if r.status == 404:
                return "overseerr_wrong_port"
            return "overseerr_error"
    except Exception as e:
        return _log_exc("overseerr", test_url, e)


async def _test_overseerr_family(
    session: aiohttp.ClientSession, url: str, email: str, password: str, ssl=None
) -> str | None:
    if not email or not password:
        return None
    base = url.rstrip("/")
    login_url = f"{base}/api/v1/auth/local"
    payload = {"email": email, "password": password}
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=timeout,
        ) as sess:
            hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
            # GET first to get CSRF cookies — Overseerr double-submit cookie pattern
            _csrf_value = None
            async with sess.get(f"{base}/api/v1/auth/me", ssl=ssl) as _:
                pass
            csrf_token = None
            for c in sess.cookie_jar:
                if c.key == "XSRF-TOKEN":
                    csrf_token = c.value
                if c.key == "_csrf":
                    _csrf_value = c.value
            # Explicitly pass cookies — aiohttp may not resend Secure-flagged cookies over http
            req_cookies = {}
            if csrf_token:
                hdrs["X-XSRF-TOKEN"] = csrf_token
                req_cookies["XSRF-TOKEN"] = csrf_token
            if _csrf_value:
                req_cookies["_csrf"] = _csrf_value
            async with sess.post(login_url, json=payload, headers=hdrs,
                                 cookies=req_cookies if req_cookies else None, ssl=ssl) as r:
                if r.status in (401, 403):
                    return "seerr_family_bad_credentials"
                if r.status != 200:
                    return "seerr_family_login_failed"
                body = await r.json()
            if body.get("permissions", 0) & 2:
                return "seerr_family_is_admin"
            return None
    except Exception as e:
        return _log_exc("overseerr_family", login_url, e)


async def _test_tautulli(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api/v2"
    _LOGGER.debug("arr_stack [tautulli] testing connection → %s", test_url)
    try:
        async with session.get(
            test_url,
            params={"apikey": key, "cmd": "get_activity"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 200:
                data = await r.json()
                if data.get("response", {}).get("result") == "success":
                    return None
                return "tautulli_bad_key"
            if r.status in (401, 403):
                return "tautulli_bad_key"
            if r.status == 404:
                return "tautulli_wrong_port"
            return "tautulli_error"
    except Exception as e:
        return _log_exc("tautulli", test_url, e)


async def _test_jellystat(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    test_url = url.rstrip('/')
    _LOGGER.debug("arr_stack [jellystat] testing connection → %s", test_url)
    try:
        async with session.get(
            test_url,
            headers={"x-api-token": key, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status < 500:
                return None
            return "jellystat_error"
    except Exception as e:
        return _log_exc("jellystat", test_url, e)


async def _test_bazarr(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    test_url = f"{url.rstrip('/')}/api/system/status"
    _LOGGER.debug("arr_stack [bazarr] testing connection → %s", test_url)
    try:
        async with session.get(
            test_url,
            headers={"X-API-KEY": key, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 200:
                return None
            if r.status == 401:
                return "bazarr_bad_key"
            if r.status == 404:
                return "bazarr_wrong_port"
            return "bazarr_error"
    except Exception as e:
        return _log_exc("bazarr", test_url, e)


# ── Config Flow ──────────────────────────────────────────────────────────────

# All configurable step groups in order
_ALL_STEPS = ['media', 'torrents', 'usenet', 'quality', 'bazarr', 'discovery', 'plex', 'jellyfin', 'trakt', 'prowlarr']


class ArrStackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow with dynamic step selection."""

    VERSION = 1
    single_config_entry = True

    def __init__(self):
        self._data: dict = {}
        self._reconfigure_entry = None
        self._plex_pin_id: int | None = None
        self._plex_pin_code: str | None = None
        self._step_queue: list = []

    # ── Queue helper ─────────────────────────────────────────────────────────

    async def _next_step(self):
        if not self._step_queue:
            return self._finish_flow()
        step = self._step_queue.pop(0)
        return await getattr(self, f'async_step_{step}')()

    # ── Krok 0: Global Settings ───────────────────────────────────────────────

    async def async_step_reconfigure(self, user_input=None):
        self._reconfigure_entry = self._get_reconfigure_entry()
        self._data = dict(self._reconfigure_entry.data)
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        if not self._reconfigure_entry and self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._data[CONF_SKIP_SSL_VERIFY] = user_input.get(CONF_SKIP_SSL_VERIFY, False)
            return await self.async_step_service_selection()

        schema = vol.Schema({
            vol.Optional(CONF_SKIP_SSL_VERIFY, default=self._data.get(CONF_SKIP_SSL_VERIFY, False)): bool,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors={},
            last_step=False,
        )

    # ── Krok 1: Výběr služeb ─────────────────────────────────────────────────

    async def async_step_service_selection(self, user_input=None):
        if user_input is not None:
            # media is always included — mandatory
            optional_steps = ['torrents', 'usenet', 'quality', 'bazarr', 'discovery', 'plex', 'jellyfin', 'trakt', 'prowlarr']
            selected = ['media'] + [s for s in optional_steps if user_input.get(f'enable_{s}', False)]
            # preserve order from _ALL_STEPS
            self._step_queue = [s for s in _ALL_STEPS if s in selected]
            return await self._next_step()

        # Derive defaults from existing data
        d = self._data
        schema = vol.Schema({
            vol.Optional('enable_torrents',  default=bool(d.get(CONF_QBIT_URL) or d.get(CONF_DELUGE_URL) or d.get(CONF_RTORRENT_URL))): bool,
            vol.Optional('enable_usenet',    default=bool(d.get(CONF_SAB_URL) or d.get(CONF_NZBGET_URL))): bool,
            vol.Optional('enable_quality',   default=bool(d.get(CONF_RADARR2_URL) or d.get(CONF_SONARR2_URL))): bool,
            vol.Optional('enable_bazarr',    default=bool(d.get(CONF_BAZARR_URL))): bool,
            vol.Optional('enable_discovery', default=bool(d.get(CONF_SEERR_URL))): bool,
            vol.Optional('enable_plex',      default=bool(d.get(CONF_PLEX_TOKEN) or d.get(CONF_EMBY_URL))): bool,
            vol.Optional('enable_jellyfin',  default=bool(d.get(CONF_TAUTULLI_URL) or d.get(CONF_JELLYSTAT_URL))): bool,
            vol.Optional('enable_trakt',     default=bool(d.get(CONF_TRAKT_CLIENT_ID))): bool,
            vol.Optional('enable_prowlarr',  default=bool(d.get(CONF_PROWLARR_URL))): bool,
        })
        return self.async_show_form(
            step_id="service_selection",
            data_schema=schema,
            errors={},
            last_step=False,
        )

    # ── Torrent clients: qBittorrent + Deluge + rTorrent ─────────────────────

    async def async_step_torrents(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            err = await _test_qbit(
                session,
                user_input.get(CONF_QBIT_URL, ""),
                user_input.get(CONF_QBIT_USER, ""),
                user_input.get(CONF_QBIT_PASS, ""),
                ssl=ssl,
            )
            if err:
                errors[CONF_QBIT_URL] = err

            if not errors:
                err = await _test_deluge(
                    session,
                    user_input.get(CONF_DELUGE_URL, ""),
                    user_input.get(CONF_DELUGE_PASS, ""),
                    ssl=ssl,
                )
                if err:
                    errors[CONF_DELUGE_URL] = err

            if not errors:
                err = await _test_rtorrent(
                    session,
                    user_input.get(CONF_RTORRENT_URL, ""),
                    user_input.get(CONF_RTORRENT_USER, ""),
                    user_input.get(CONF_RTORRENT_PASS, ""),
                    ssl=ssl,
                )
                if err:
                    errors[CONF_RTORRENT_URL] = err

            if not errors:
                for key in [CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS,
                             CONF_DELUGE_URL, CONF_DELUGE_PASS,
                             CONF_RTORRENT_URL, CONF_RTORRENT_USER, CONF_RTORRENT_PASS]:
                    self._data[key] = user_input.get(key, "")
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_QBIT_URL):      str,
            vol.Optional(CONF_QBIT_USER):     str,
            vol.Optional(CONF_QBIT_PASS):     str,
            vol.Optional(CONF_DELUGE_URL):    str,
            vol.Optional(CONF_DELUGE_PASS):   str,
            vol.Optional(CONF_RTORRENT_URL):  str,
            vol.Optional(CONF_RTORRENT_USER): str,
            vol.Optional(CONF_RTORRENT_PASS): str,
        })
        suggested = self._data if self._data else {
            CONF_QBIT_URL:      "http://192.168.1.x:8081",
            CONF_QBIT_USER:     "admin",
            CONF_DELUGE_URL:    "http://192.168.1.x:8112",
            CONF_RTORRENT_URL:  "http://192.168.1.x:9080",
            CONF_RTORRENT_USER: "",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="torrents",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Usenet clients: SABnzbd + NZBGet ─────────────────────────────────────

    async def async_step_usenet(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            err = await _test_sabnzbd(
                session,
                user_input.get(CONF_SAB_URL, ""),
                user_input.get(CONF_SAB_KEY, ""),
                ssl=ssl,
            )
            if err:
                errors[CONF_SAB_URL] = err

            if not errors:
                err = await _test_nzbget(
                    session,
                    user_input.get(CONF_NZBGET_URL, ""),
                    user_input.get(CONF_NZBGET_USER, ""),
                    user_input.get(CONF_NZBGET_PASS, ""),
                    ssl=ssl,
                )
                if err:
                    errors[CONF_NZBGET_URL] = err

            if not errors:
                for key in [CONF_SAB_URL, CONF_SAB_KEY,
                             CONF_NZBGET_URL, CONF_NZBGET_USER, CONF_NZBGET_PASS]:
                    self._data[key] = user_input.get(key, "")
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_SAB_URL):      str,
            vol.Optional(CONF_SAB_KEY):      str,
            vol.Optional(CONF_NZBGET_URL):   str,
            vol.Optional(CONF_NZBGET_USER):  str,
            vol.Optional(CONF_NZBGET_PASS):  str,
        })
        suggested = self._data if self._data else {
            CONF_SAB_URL:    "http://192.168.1.x:8089",
            CONF_NZBGET_URL: "http://192.168.1.x:6789",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="usenet",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Media: Radarr + Sonarr ────────────────────────────────────────────────

    async def async_step_media(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            err = await _test_arr(session, user_input[CONF_RADARR_URL], user_input[CONF_RADARR_KEY], "radarr", ssl=ssl)
            if err:
                errors[CONF_RADARR_URL] = err
            else:
                err = await _test_arr(session, user_input[CONF_SONARR_URL], user_input[CONF_SONARR_KEY], "sonarr", ssl=ssl)
                if err:
                    errors[CONF_SONARR_URL] = err

            if not errors:
                self._data.update(user_input)
                return await self._next_step()

        schema = vol.Schema({
            vol.Required(CONF_RADARR_URL): str,
            vol.Required(CONF_RADARR_KEY): str,
            vol.Required(CONF_SONARR_URL): str,
            vol.Required(CONF_SONARR_KEY): str,
        })
        suggested = self._data if self._data else {
            CONF_RADARR_URL: "http://192.168.1.x:7878",
            CONF_SONARR_URL: "http://192.168.1.x:8989",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="media",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Quality: Radarr 2 + Sonarr 2 + Bazarr ────────────────────────────────

    async def async_step_quality(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            radarr4k_url = user_input.get(CONF_RADARR2_URL, "").strip()
            radarr4k_key = user_input.get(CONF_RADARR2_KEY, "").strip()
            sonarr4k_url = user_input.get(CONF_SONARR2_URL, "").strip()
            sonarr4k_key = user_input.get(CONF_SONARR2_KEY, "").strip()

            if radarr4k_url:
                err = await _test_arr(session, radarr4k_url, radarr4k_key, "radarr2", ssl=ssl)
                if err:
                    errors[CONF_RADARR2_URL] = err

            if not errors and sonarr4k_url:
                err = await _test_arr(session, sonarr4k_url, sonarr4k_key, "sonarr2", ssl=ssl)
                if err:
                    errors[CONF_SONARR2_URL] = err

            if not errors:
                self._data[CONF_RADARR2_URL] = radarr4k_url
                self._data[CONF_RADARR2_KEY] = radarr4k_key
                self._data[CONF_SONARR2_URL] = sonarr4k_url
                self._data[CONF_SONARR2_KEY] = sonarr4k_key
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_RADARR2_URL): str,
            vol.Optional(CONF_RADARR2_KEY): str,
            vol.Optional(CONF_SONARR2_URL): str,
            vol.Optional(CONF_SONARR2_KEY): str,
        })
        suggested = self._data if self._data else {}
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="quality",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Discovery: Overseerr + family + Bazarr ────────────────────────────────

    async def async_step_discovery(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            seerr_url = user_input.get(CONF_SEERR_URL, "").strip()
            seerr_key = user_input.get(CONF_SEERR_KEY, "").strip()

            if seerr_url and seerr_key:
                err = await _test_overseerr(session, seerr_url, seerr_key, ssl=ssl)
                if err:
                    errors[CONF_SEERR_URL] = err
                else:
                    err = await _test_overseerr_family(
                        session,
                        seerr_url,
                        user_input.get(CONF_SEERR_FAMILY_EMAIL, ""),
                        user_input.get(CONF_SEERR_FAMILY_PASS, ""),
                        ssl=ssl,
                    )
                    if err:
                        errors[CONF_SEERR_FAMILY_EMAIL] = err

            if not errors:
                for key in [CONF_SEERR_URL, CONF_SEERR_KEY, CONF_SEERR_FAMILY_EMAIL, CONF_SEERR_FAMILY_PASS]:
                    self._data[key] = user_input.get(key, "")
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_SEERR_URL):          str,
            vol.Optional(CONF_SEERR_KEY):          str,
            vol.Optional(CONF_SEERR_FAMILY_EMAIL): str,
            vol.Optional(CONF_SEERR_FAMILY_PASS):  str,
        })
        suggested = self._data if self._data else {
            CONF_SEERR_URL: "http://192.168.1.x:5055",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="discovery",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Bazarr ───────────────────────────────────────────────────────────────

    async def async_step_bazarr(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            err = await _test_bazarr(
                session,
                user_input.get(CONF_BAZARR_URL, ""),
                user_input.get(CONF_BAZARR_KEY, ""),
                ssl=ssl,
            )
            if err:
                errors[CONF_BAZARR_URL] = err

            if not errors:
                self._data[CONF_BAZARR_URL] = user_input.get(CONF_BAZARR_URL, "")
                self._data[CONF_BAZARR_KEY] = user_input.get(CONF_BAZARR_KEY, "")
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_BAZARR_URL): str,
            vol.Optional(CONF_BAZARR_KEY): str,
        })
        suggested = self._data if self._data else {
            CONF_BAZARR_URL: "http://192.168.1.x:6767",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="bazarr",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Plex ─────────────────────────────────────────────────────────────────

    async def async_step_plex(self, user_input=None):
        errors = {}

        if user_input is not None:
            # Save Emby regardless of Plex skip
            self._data[CONF_EMBY_URL] = (user_input.get(CONF_EMBY_URL) or "").strip().rstrip("/")
            self._data[CONF_EMBY_KEY] = (user_input.get(CONF_EMBY_KEY) or "").strip()

            if user_input.get("skip_plex") == "skip":
                # Preserve existing token if already configured
                if not self._data.get(CONF_PLEX_TOKEN):
                    self._data[CONF_PLEX_URL] = ""
                return await self._next_step()

            manual_url = (user_input.get("plex_server_url") or "").strip().rstrip("/")
            if manual_url and _url_error(manual_url):
                errors["plex_server_url"] = "invalid_url"
                self._plex_pin_id = None
            elif self._plex_pin_id:
                token, server_url = await self._poll_plex_pin()
                if token:
                    self._data[CONF_PLEX_TOKEN] = token
                    self._data[CONF_PLEX_URL] = manual_url or server_url or ""
                elif self._data.get(CONF_PLEX_TOKEN):
                    self._data[CONF_PLEX_URL] = manual_url
                else:
                    errors["base"] = "plex_not_authenticated"
                    self._plex_pin_id = None
                if not errors:
                    return await self._next_step()

        try:
            pin_id, pin_code = await self._create_plex_pin()
            self._plex_pin_id   = pin_id
            self._plex_pin_code = pin_code
            auth_url = (
                f"https://app.plex.tv/auth#?clientID={PLEX_CLIENT_ID}"
                f"&code={pin_code}"
                f"&context%5Bdevice%5D%5Bproduct%5D=Arr+Stack+Card"
            )
        except Exception:
            errors["base"] = "plex_pin_failed"
            auth_url = "https://plex.tv"

        plex_section = (
            f"1. [Open Plex authentication]({auth_url})\n"
            f"2. Sign in and authorise **Arr Stack Card**\n"
            f"3. Return here and click **Submit**"
        )

        from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
        skip_default = "skip" if self._data.get(CONF_PLEX_TOKEN) else "setup"
        schema = vol.Schema({
            vol.Optional("skip_plex", default=skip_default): SelectSelector(
                SelectSelectorConfig(
                    options=["setup", "skip"],
                    translation_key="skip_plex",
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Optional("plex_server_url"): str,
            vol.Optional(CONF_EMBY_URL): str,
            vol.Optional(CONF_EMBY_KEY): str,
        })
        schema = self.add_suggested_values_to_schema(schema, {
            "plex_server_url": self._data.get(CONF_PLEX_URL, ""),
            CONF_EMBY_URL: self._data.get(CONF_EMBY_URL, ""),
            CONF_EMBY_KEY: self._data.get(CONF_EMBY_KEY, ""),
        })
        return self.async_show_form(
            step_id="plex",
            data_schema=schema,
            errors=errors,
            description_placeholders={"plex_section": plex_section},
            last_step=len(self._step_queue) == 0,
        )

    # ── Tautulli + Jellystat ─────────────────────────────────────────────────

    async def async_step_jellyfin(self, user_input=None):
        errors = {}
        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            tautulli_url  = user_input.get(CONF_TAUTULLI_URL, "")
            tautulli_key  = user_input.get(CONF_TAUTULLI_KEY, "")
            jellystat_url = user_input.get(CONF_JELLYSTAT_URL, "")
            jellystat_key = user_input.get(CONF_JELLYSTAT_KEY, "")

            err = await _test_tautulli(session, tautulli_url, tautulli_key, ssl=ssl)
            if err:
                errors[CONF_TAUTULLI_URL] = err

            if not errors:
                err = await _test_jellystat(session, jellystat_url, jellystat_key, ssl=ssl)
                if err:
                    errors[CONF_JELLYSTAT_URL] = err

            if not errors:
                self._data[CONF_TAUTULLI_URL]  = tautulli_url
                self._data[CONF_TAUTULLI_KEY]  = tautulli_key
                self._data[CONF_JELLYSTAT_URL] = jellystat_url
                self._data[CONF_JELLYSTAT_KEY] = jellystat_key
                return await self._next_step()

        schema = vol.Schema({
            vol.Optional(CONF_TAUTULLI_URL):  str,
            vol.Optional(CONF_TAUTULLI_KEY):  str,
            vol.Optional(CONF_JELLYSTAT_URL): str,
            vol.Optional(CONF_JELLYSTAT_KEY): str,
        })
        ui = user_input or {}
        suggested = {
            CONF_TAUTULLI_URL:  ui.get(CONF_TAUTULLI_URL)  or self._data.get(CONF_TAUTULLI_URL, ""),
            CONF_TAUTULLI_KEY:  ui.get(CONF_TAUTULLI_KEY)  or self._data.get(CONF_TAUTULLI_KEY, ""),
            CONF_JELLYSTAT_URL: ui.get(CONF_JELLYSTAT_URL) or self._data.get(CONF_JELLYSTAT_URL, ""),
            CONF_JELLYSTAT_KEY: ui.get(CONF_JELLYSTAT_KEY) or self._data.get(CONF_JELLYSTAT_KEY, ""),
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="jellyfin",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Trakt OAuth ───────────────────────────────────────────────────────────

    async def async_step_trakt(self, user_input=None):
        errors = {}

        if user_input is not None:
            client_id     = (user_input.get(CONF_TRAKT_CLIENT_ID) or "").strip()
            client_secret = (user_input.get(CONF_TRAKT_CLIENT_SECRET) or "").strip()

            if not client_id:
                return await self._next_step()

            # Credentials unchanged and token already present → skip re-auth
            if (client_id == self._data.get(CONF_TRAKT_CLIENT_ID, '').strip()
                    and self._data.get(CONF_TRAKT_ACCESS_TOKEN)):
                return await self._next_step()

            if not client_secret:
                errors[CONF_TRAKT_CLIENT_SECRET] = "trakt_secret_required"
            else:
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{TRAKT_API_BASE}/oauth/device/code",
                        json={"client_id": client_id},
                        headers={
                            "Content-Type": "application/json",
                            "trakt-api-version": "2",
                            "trakt-api-key": client_id,
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status != 200:
                            errors[CONF_TRAKT_CLIENT_ID] = "trakt_device_code_failed"
                        else:
                            dc = await resp.json()
                            self._trakt_device_code = dc
                            self._trakt_client_id     = client_id
                            self._trakt_client_secret = client_secret
                            return await self.async_step_trakt_poll()
                except Exception:
                    errors[CONF_TRAKT_CLIENT_ID] = "trakt_connection_error"

        schema = vol.Schema({
            vol.Optional(CONF_TRAKT_CLIENT_ID):     str,
            vol.Optional(CONF_TRAKT_CLIENT_SECRET): str,
        })
        ui = user_input or {}
        schema = self.add_suggested_values_to_schema(schema, {
            CONF_TRAKT_CLIENT_ID:     ui.get(CONF_TRAKT_CLIENT_ID) or self._data.get(CONF_TRAKT_CLIENT_ID, ""),
            CONF_TRAKT_CLIENT_SECRET: ui.get(CONF_TRAKT_CLIENT_SECRET) or self._data.get(CONF_TRAKT_CLIENT_SECRET, ""),
        })
        return self.async_show_form(
            step_id="trakt",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
            description_placeholders={
                "trakt_apps_url": "https://trakt.tv/oauth/applications/new",
            },
        )

    async def async_step_trakt_poll(self, user_input=None):
        import time
        errors = {}
        dc = getattr(self, "_trakt_device_code", None)
        if not dc:
            return await self.async_step_trakt()

        client_id     = self._trakt_client_id
        client_secret = self._trakt_client_secret

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                async with session.post(
                    f"{TRAKT_API_BASE}/oauth/device/token",
                    json={
                        "code":          dc["device_code"],
                        "client_id":     client_id,
                        "client_secret": client_secret,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "trakt-api-version": "2",
                        "trakt-api-key": client_id,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        tok = await resp.json()
                        self._data[CONF_TRAKT_CLIENT_ID]     = client_id
                        self._data[CONF_TRAKT_CLIENT_SECRET] = client_secret
                        self._data[CONF_TRAKT_ACCESS_TOKEN]  = tok["access_token"]
                        self._data[CONF_TRAKT_REFRESH_TOKEN] = tok["refresh_token"]
                        self._data[CONF_TRAKT_EXPIRES_AT]    = int(time.time()) + tok.get("expires_in", 604800)
                        return self._finish_flow()
                    elif resp.status == 400:
                        errors["base"] = "trakt_not_authorized"
                    elif resp.status == 410:
                        errors["base"] = "trakt_code_expired"
                    else:
                        errors["base"] = "trakt_poll_error"
            except Exception:
                errors["base"] = "trakt_connection_error"

        user_code  = dc.get("user_code", "")
        verify_url = dc.get("verification_url", "https://trakt.tv/activate")
        return self.async_show_form(
            step_id="trakt_poll",
            data_schema=vol.Schema({}),
            errors=errors,
            last_step=True,
            description_placeholders={
                "user_code":  user_code,
                "verify_url": verify_url,
            },
        )

    # ── Prowlarr ──────────────────────────────────────────────────────────────

    async def async_step_prowlarr(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = (user_input.get(CONF_PROWLARR_URL) or "").strip().rstrip("/")
            key = (user_input.get(CONF_PROWLARR_KEY) or "").strip()
            if url:
                err = _url_error(url)
                if err:
                    errors[CONF_PROWLARR_URL] = err
                else:
                    try:
                        session = async_get_clientsession(self.hass)
                        ssl = False if self._data.get(CONF_SKIP_SSL_VERIFY) else None
                        async with session.get(
                            f"{url}/api/v1/indexer",
                            headers={"X-Api-Key": key},
                            timeout=aiohttp.ClientTimeout(total=10),
                            ssl=ssl,
                        ) as r:
                            if r.status not in (200, 201):
                                errors[CONF_PROWLARR_URL] = "cannot_connect"
                    except Exception as e:
                        errors[CONF_PROWLARR_URL] = _map_exc(e)
            if not errors:
                self._data[CONF_PROWLARR_URL] = url or ""
                self._data[CONF_PROWLARR_KEY] = key
                return await self._next_step()

        d = self._data
        ui = user_input or {}
        schema = vol.Schema({
            vol.Optional(CONF_PROWLARR_URL, default=ui.get(CONF_PROWLARR_URL) or d.get(CONF_PROWLARR_URL, "")): str,
            vol.Optional(CONF_PROWLARR_KEY, default=ui.get(CONF_PROWLARR_KEY) or d.get(CONF_PROWLARR_KEY, "")): str,
        })
        return self.async_show_form(
            step_id="prowlarr",
            data_schema=schema,
            errors=errors,
            last_step=len(self._step_queue) == 0,
        )

    # ── Finish ────────────────────────────────────────────────────────────────

    def _finish_flow(self):
        if self._reconfigure_entry is not None:
            self.hass.config_entries.async_update_entry(
                self._reconfigure_entry, data=dict(self._data)
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self._reconfigure_entry.entry_id)
            )
            return self.async_abort(reason="reconfigure_successful")
        return self.async_create_entry(title="Arr Stack", data=self._data)

    # ── Plex helpers ──────────────────────────────────────────────────────────

    async def _create_plex_pin(self) -> tuple[int, str]:
        session = async_get_clientsession(self.hass)
        headers = {
            "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
            "X-Plex-Product":           "Arr Stack Card",
            "Accept":                   "application/json",
        }
        async with session.post(
            "https://plex.tv/api/v2/pins",
            headers=headers,
            data={"strong": "true"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
            return int(data["id"]), str(data["code"])

    async def _poll_plex_pin(self) -> tuple[str | None, str | None]:
        session = async_get_clientsession(self.hass)
        headers = {
            "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
            "Accept":                   "application/json",
        }
        async with session.get(
            f"https://plex.tv/api/v2/pins/{self._plex_pin_id}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
            token = data.get("authToken")
            if not token:
                return None, None
            server_url = await self._get_plex_server(token)
            return token, server_url

    async def _get_plex_username(self, token: str) -> str:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                "https://plex.tv/api/v2/user",
                headers={
                    "X-Plex-Token":             token,
                    "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
                    "Accept":                   "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                data = await r.json()
                return data.get("username") or data.get("title") or ""
        except Exception:
            return ""

    async def _get_plex_server(self, token: str) -> str:
        session = async_get_clientsession(self.hass)
        headers = {
            "X-Plex-Token":             token,
            "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
            "Accept":                   "application/json",
        }
        try:
            async with session.get(
                "https://plex.tv/api/v2/resources?includeHttps=1&includeRelay=0&includeIPv6=0",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                resources = await r.json()
                for res in resources:
                    if res.get("product") == "Plex Media Server":
                        conns = res.get("connections", [])
                        local  = [c for c in conns if c.get("local") and not c.get("relay")]
                        remote = [c for c in conns if not c.get("local") and not c.get("relay")]
                        candidates = local + remote
                        for c in candidates:
                            uri = c.get("uri", "").rstrip("/")
                            if not uri:
                                continue
                            try:
                                async with session.get(
                                    f"{uri}/",
                                    headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=4),
                                    allow_redirects=False,
                                ) as probe:
                                    if probe.status < 500:
                                        return uri
                            except Exception:
                                continue
                        if candidates:
                            return candidates[0].get("uri", "").rstrip("/")
        except Exception:
            pass
        return ""
