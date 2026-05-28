"""Config flow — 5 kroků s ověřením přístupu ke každé službě."""
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS,
    CONF_SAB_URL, CONF_SAB_KEY,
    CONF_RADARR_URL, CONF_RADARR_KEY,
    CONF_RADARR2_URL, CONF_RADARR2_KEY,
    CONF_SONARR_URL, CONF_SONARR_KEY,
    CONF_SONARR2_URL, CONF_SONARR2_KEY,
    CONF_SEERR_URL, CONF_SEERR_KEY,
    CONF_SEERR_FAMILY_EMAIL, CONF_SEERR_FAMILY_PASS,
    CONF_BAZARR_URL, CONF_BAZARR_KEY,
    CONF_PLEX_TOKEN, CONF_PLEX_URL, PLEX_CLIENT_ID,
    CONF_TAUTULLI_URL, CONF_TAUTULLI_KEY,
    CONF_JELLYSTAT_URL, CONF_JELLYSTAT_KEY,
    CONF_SKIP_SSL_VERIFY,
)


# ── Pomocné funkce pro chyby ─────────────────────────────────────────────────

def _url_error(url: str) -> str | None:
    """Vrátí chybový kód pokud URL chybí schéma nebo je jinak zjevně špatná."""
    if not url.startswith(("http://", "https://")):
        return "invalid_url"
    return None

def _map_exc(e: Exception) -> str:
    if isinstance(e, aiohttp.InvalidURL):
        return "invalid_url"
    if isinstance(e, aiohttp.ClientConnectorError):
        return "cannot_connect"
    if isinstance(e, aiohttp.ServerTimeoutError):
        return "timeout"
    if isinstance(e, aiohttp.ClientSSLError):
        return "ssl_error"
    return "unknown"


# ── Validační funkce ─────────────────────────────────────────────────────────

async def _test_qbit(session: aiohttp.ClientSession, url: str, user: str, password: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    try:
        base = url.rstrip('/')
        async with session.post(
            f"{base}/api/v2/auth/login",
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
        return _map_exc(e)


async def _test_sabnzbd(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    try:
        async with session.get(
            f"{url.rstrip('/')}/api",
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
        return _map_exc(e)


async def _test_arr(session: aiohttp.ClientSession, url: str, key: str, name: str, ssl=None) -> str | None:
    if err := _url_error(url):
        return err
    try:
        async with session.get(
            f"{url.rstrip('/')}/api/v3/system/status",
            headers={"X-Api-Key": key},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status == 200:
                return None
            if r.status == 401:
                return f"{name}_bad_key"
            if r.status == 404:
                return f"{name}_wrong_port"
            return f"{name}_error"
    except Exception as e:
        return _map_exc(e)


async def _test_overseerr(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if err := _url_error(url):
        return err
    try:
        async with session.get(
            f"{url.rstrip('/')}/api/v1/settings/about",
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
        return _map_exc(e)


async def _test_overseerr_family(
    session: aiohttp.ClientSession, url: str, email: str, password: str, ssl=None
) -> str | None:
    if not email or not password:
        return None
    try:
        async with session.post(
            f"{url.rstrip('/')}/api/v1/auth/local",
            json={"email": email, "password": password},
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status in (401, 403):
                return "seerr_family_bad_credentials"
            if r.status != 200:
                return "seerr_family_login_failed"
            data = await r.json()
            if data.get("permissions", 0) & 2:
                return "seerr_family_is_admin"
            return None
    except Exception as e:
        return _map_exc(e)


async def _test_tautulli(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    try:
        async with session.get(
            f"{url.rstrip('/')}/api/v2",
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
        return _map_exc(e)


async def _test_jellystat(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    try:
        # Just verify server is reachable — Jellystat API endpoint paths vary by version
        async with session.get(
            url.rstrip('/'),
            headers={"x-api-token": key, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=ssl,
        ) as r:
            if r.status < 500:
                return None
            return "jellystat_error"
    except Exception as e:
        return _map_exc(e)


async def _test_bazarr(session: aiohttp.ClientSession, url: str, key: str, ssl=None) -> str | None:
    if not url:
        return None
    if err := _url_error(url):
        return err
    try:
        async with session.get(
            f"{url.rstrip('/')}/api/system/status",
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
        return _map_exc(e)


# ── Config Flow ──────────────────────────────────────────────────────────────

class ArrStackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow s ověřením přístupu."""

    VERSION = 1
    single_config_entry = True

    def __init__(self):
        self._data: dict = {}
        self._reconfigure_entry = None
        self._plex_pin_id: int | None = None
        self._plex_pin_code: str | None = None

    async def async_step_reconfigure(self, user_input=None):
        self._reconfigure_entry = self._get_reconfigure_entry()
        self._data = dict(self._reconfigure_entry.data)
        return await self.async_step_user()

    # ── Krok 0: Global Settings ───────────────────────────────────────────────

    async def async_step_user(self, user_input=None):
        if not self._reconfigure_entry and self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._data[CONF_SKIP_SSL_VERIFY] = user_input.get(CONF_SKIP_SSL_VERIFY, False)
            return await self.async_step_downloads()

        schema = vol.Schema({
            vol.Optional(CONF_SKIP_SSL_VERIFY, default=self._data.get(CONF_SKIP_SSL_VERIFY, False)): bool,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors={},
            last_step=False,
        )

    # ── Krok 1: qBittorrent + SABnzbd (volitelné) ────────────────────────────

    async def async_step_downloads(self, user_input=None):
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
            else:
                err = await _test_sabnzbd(
                    session,
                    user_input.get(CONF_SAB_URL, ""),
                    user_input.get(CONF_SAB_KEY, ""),
                    ssl=ssl,
                )
                if err:
                    errors[CONF_SAB_URL] = err

            if not errors:
                for key in [CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS, CONF_SAB_URL, CONF_SAB_KEY]:
                    self._data[key] = user_input.get(key, "")
                return await self.async_step_media()

        schema = vol.Schema({
            vol.Optional(CONF_QBIT_URL):  str,
            vol.Optional(CONF_QBIT_USER): str,
            vol.Optional(CONF_QBIT_PASS): str,
            vol.Optional(CONF_SAB_URL):   str,
            vol.Optional(CONF_SAB_KEY):   str,
        })
        suggested = self._data if self._data else {
            CONF_QBIT_URL:  "http://192.168.1.x:8080",
            CONF_QBIT_USER: "admin",
            CONF_SAB_URL:   "http://192.168.1.x:8080",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="downloads",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ── Krok 2: Radarr + Sonarr (povinné) ────────────────────────────────────

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
                return await self.async_step_quality()

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
            last_step=False,
        )

    # ── Krok 3: Radarr 4K + Sonarr 4K (volitelné) ────────────────────────────

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
                return await self.async_step_discovery()

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
            last_step=False,
        )

    # ── Krok 4: Overseerr (volitelný) + family účet + Bazarr (volitelné) ────

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
                err = await _test_bazarr(
                    session,
                    user_input.get(CONF_BAZARR_URL, ""),
                    user_input.get(CONF_BAZARR_KEY, ""),
                    ssl=ssl,
                )
                if err:
                    errors[CONF_BAZARR_URL] = err

            if not errors:
                self._data.update(user_input)
                for key in [CONF_SEERR_URL, CONF_SEERR_KEY, CONF_SEERR_FAMILY_EMAIL, CONF_SEERR_FAMILY_PASS, CONF_BAZARR_URL, CONF_BAZARR_KEY]:
                    self._data[key] = user_input.get(key, "")
                return await self.async_step_plex()

        schema = vol.Schema({
            vol.Optional(CONF_SEERR_URL):          str,
            vol.Optional(CONF_SEERR_KEY):          str,
            vol.Optional(CONF_SEERR_FAMILY_EMAIL): str,
            vol.Optional(CONF_SEERR_FAMILY_PASS):  str,
            vol.Optional(CONF_BAZARR_URL):         str,
            vol.Optional(CONF_BAZARR_KEY):         str,
        })
        suggested = self._data if self._data else {
            CONF_SEERR_URL:   "http://192.168.1.x:5055",
            CONF_BAZARR_URL:  "http://192.168.1.x:6767",
        }
        schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(
            step_id="discovery",
            data_schema=schema,
            errors=errors,
            last_step=False,
        )

    # ── Krok 5: Plex (volitelné) ─────────────────────────────────────────────

    async def async_step_plex(self, user_input=None):
        errors = {}

        if user_input is not None:
            if user_input.get("skip_plex"):
                self._data[CONF_PLEX_TOKEN] = ""
                self._data[CONF_PLEX_URL]   = ""
                return await self.async_step_jellyfin()

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
                    # Store manual URL as-is (empty = auto-detect at proxy time)
                    self._data[CONF_PLEX_URL] = manual_url
                else:
                    errors["base"] = "plex_not_authenticated"
                    self._plex_pin_id = None
                if not errors:
                    return await self.async_step_jellyfin()

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

        schema = vol.Schema({
            vol.Optional("plex_server_url"): str,
            vol.Optional("skip_plex", default=False): bool,
        })
        schema = self.add_suggested_values_to_schema(schema, {
            "plex_server_url": self._data.get(CONF_PLEX_URL, ""),
        })
        return self.async_show_form(
            step_id="plex",
            data_schema=schema,
            errors=errors,
            description_placeholders={"plex_section": plex_section},
            last_step=False,
        )

    # ── Krok 6: Tautulli + Jellystat (volitelné) ────────────────────────────

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
                return self._finish_flow()

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
            last_step=True,
        )

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
                        # Local-first, then others — but test reachability from this HA instance
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
                        # All probes failed — return first candidate as-is (better than nothing)
                        if candidates:
                            return candidates[0].get("uri", "").rstrip("/")
        except Exception:
            pass
        return ""
