"""HTTP proxy view — přeposílá requesty z karty na lokální služby (server-side, žádný CORS)."""
import asyncio
import base64
import itertools
import logging
import xmlrpc.client as _xmlrpc
from urllib.parse import quote
import aiohttp
from aiohttp import web
import yarl

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# In-memory cache for Tracearr admin JWT tokens: entry_id → {"access": str, "refresh": str}
_tracearr_token_cache: dict = {}

async def _tracearr_get_access_token(http: aiohttp.ClientSession, tracearr_url: str, entry_id: str, refresh_token: str, ssl=None, hass=None, plex_token: str = "") -> str | None:
    """Return valid Tracearr admin access token, refreshing if needed."""
    import time, json as _json
    cached = _tracearr_token_cache.get(entry_id, {})
    # Bootstrap from config-stored access token (survives HA restarts)
    if not cached.get("access") and hass:
        entries = hass.config_entries.async_entries("arr_stack")
        if entries:
            stored_access = entries[0].data.get("tracearr_access_token", "")
            if stored_access:
                cached = {"access": stored_access, "refresh": cached.get("refresh", refresh_token)}
                _tracearr_token_cache[entry_id] = cached
    access = cached.get("access", "")
    # Decode JWT exp without verifying signature
    if access:
        try:
            payload = access.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            import base64 as _b64
            exp = _json.loads(_b64.b64decode(payload)).get("exp", 0)
            if exp - time.time() > 60:
                return access
        except Exception:
            pass

    def _persist_tokens(hass, data: dict, refresh_token: str) -> None:
        if not hass:
            return
        entries = hass.config_entries.async_entries("arr_stack")
        if not entries:
            return
        new_refresh = data.get("refreshToken", refresh_token)
        update = {"tracearr_access_token": data["accessToken"]}
        if new_refresh != refresh_token:
            update["tracearr_refresh_token"] = new_refresh
        hass.config_entries.async_update_entry(entries[0], data={**entries[0].data, **update})
        return new_refresh

    # Try JWT refresh first
    cur_refresh = cached.get("refresh", refresh_token)
    if cur_refresh:
        try:
            async with http.post(
                f"{tracearr_url}/api/v1/auth/refresh",
                json={"refreshToken": cur_refresh},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=ssl,
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    new_refresh = data.get("refreshToken", cur_refresh)
                    _tracearr_token_cache[entry_id] = {"access": data["accessToken"], "refresh": new_refresh}
                    _persist_tokens(hass, data, cur_refresh)
                    return data["accessToken"]
        except Exception as e:
            _LOGGER.warning("Tracearr token refresh failed: %s", e)

    # Fallback: re-auth via Plex token (auto-recovers when Plex session expires)
    if plex_token:
        for body in [{"authToken": plex_token}, {"plexToken": plex_token}, {"token": plex_token}]:
            try:
                async with http.post(
                    f"{tracearr_url}/api/v1/auth/plex",
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("accessToken"):
                            new_refresh = data.get("refreshToken", "")
                            _tracearr_token_cache[entry_id] = {"access": data["accessToken"], "refresh": new_refresh}
                            _persist_tokens(hass, data, new_refresh)
                            _LOGGER.info("Tracearr: re-authenticated via Plex token")
                            return data["accessToken"]
            except Exception:
                pass

    return None

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
    CONF_TRACEARR_URL, CONF_TRACEARR_KEY, CONF_TRACEARR_REFRESH_TOKEN,
    CONF_TRAKT_CLIENT_ID, CONF_TRAKT_CLIENT_SECRET,
    CONF_TRAKT_ACCESS_TOKEN, CONF_TRAKT_REFRESH_TOKEN, CONF_TRAKT_EXPIRES_AT,
    TRAKT_API_BASE, TRAKT_API_VER,
    CONF_PROWLARR_URL, CONF_PROWLARR_KEY,
    CONF_SKIP_SSL_VERIFY,
)

async def _plex_detect_server(session: aiohttp.ClientSession, token: str) -> str:
    """Auto-detect reachable Plex server URL for given token."""
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
                    for c in local + remote:
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
                    candidates = local + remote
                    if candidates:
                        return candidates[0].get("uri", "").rstrip("/")
    except Exception:
        pass
    return ""


# qBit v5 → v4 fallback endpoint mapa
QBIT_ENDPOINTS = {
    "pause":     ("/api/v2/torrents/stop",   "/api/v2/torrents/pause"),
    "resume":    ("/api/v2/torrents/start",  "/api/v2/torrents/resume"),
    "pauseAll":  ("/api/v2/torrents/stop",   "/api/v2/torrents/pause"),
    "resumeAll": ("/api/v2/torrents/start",  "/api/v2/torrents/resume"),
    "delete":    ("/api/v2/torrents/delete", "/api/v2/torrents/delete"),
}


class ArrStackProxyView(HomeAssistantView):
    """Proxy /api/arr_stack/{service}/{path} → lokální služby."""

    url = "/api/arr_stack/{service}/{path:.*}"
    name = "api:arr_stack:proxy"
    requires_auth = True

    def __init__(self, hass) -> None:
        self._hass = hass
        # Dedikovaná session pro qBit — potřebuje cookie jar pro session auth
        self._qbit_session: aiohttp.ClientSession | None = None
        # Session pro admin Overseerr požadavky — potřebuje cookie jar pro CSRF token
        self._seerr_admin_session: aiohttp.ClientSession | None = None
        # Session pro rodinný Overseerr účet
        self._seerr_family_session: aiohttp.ClientSession | None = None
        # Cache pro auto-detekovanou Plex URL (když user nezadal manuální)
        self._plex_url_cache: str | None = None
        # Cache pro Trakt recommendations (TTL 30 min)
        self._trakt_cache: list | None = None
        self._trakt_cache_ts: float = 0.0

    @property
    def _cfg(self) -> dict:
        """Čte aktuální config dynamicky — aktualizuje se bez restartu HA."""
        return self._hass.data.get(DOMAIN, {}).get("config", {})

    # ── Session helpers ──────────────────────────────────────────────────

    async def _qbit_sess(self) -> aiohttp.ClientSession:
        """Vrátí (nebo vytvoří) aiohttp session s cookie jar pro qBit."""
        if self._qbit_session is None or self._qbit_session.closed:
            self._qbit_session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._qbit_session

    async def _qbit_login(self, session: aiohttp.ClientSession, ssl=None) -> None:
        """Přihlásí se do qBit (nastaví session cookie)."""
        url = f"{self._cfg.get(CONF_QBIT_URL, '')}/api/v2/auth/login"
        async with session.post(url, data={
            "username": self._cfg.get(CONF_QBIT_USER, ""),
            "password": self._cfg.get(CONF_QBIT_PASS, ""),
        }, ssl=ssl) as r:
            await r.read()

    def _csrf_from_jar(self, session: aiohttp.ClientSession) -> tuple[dict, dict]:
        """Extrahuje XSRF-TOKEN a _csrf z cookie jaru — vrátí (extra_headers, cookies)."""
        csrf_token = ""
        _csrf_value = ""
        for cookie in session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                csrf_token = cookie.value
            if cookie.key == "_csrf":
                _csrf_value = cookie.value
        hdrs = {**({"X-XSRF-TOKEN": csrf_token} if csrf_token else {})}
        cookies = {}
        if csrf_token:
            cookies["XSRF-TOKEN"] = csrf_token
        if _csrf_value:
            cookies["_csrf"] = _csrf_value
        return hdrs, cookies

    async def _seerr_admin_sess(self) -> aiohttp.ClientSession:
        """Vrátí (nebo vytvoří) aiohttp session s cookie jar pro admin Overseerr mutace."""
        if self._seerr_admin_session is None or self._seerr_admin_session.closed:
            self._seerr_admin_session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._seerr_admin_session

    async def _seerr_csrf_hdrs(self, base: str, api_key: str, ssl) -> tuple[dict, dict]:
        """Vrátí (headers, cookies) pro Overseerr POST/PUT/DELETE s CSRF ochranou.

        Overseerr double-submit cookie pattern: GET nastaví XSRF-TOKEN + _csrf cookies,
        POST musí posílat oba cookies explicitně + X-XSRF-TOKEN header (aiohttp neposílá
        Secure-flagged cookies automaticky přes HTTP).
        """
        sess = await self._seerr_admin_sess()
        hdrs_get = {"X-Api-Key": api_key, "Accept": "application/json"}
        try:
            async with sess.get(f"{base}/api/v1/auth/me", headers=hdrs_get, ssl=ssl) as _:
                pass
        except Exception:
            pass
        csrf_token = ""
        _csrf_value = ""
        for cookie in sess.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                csrf_token = cookie.value
            if cookie.key == "_csrf":
                _csrf_value = cookie.value
        hdrs = {
            "X-Api-Key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            **({"X-XSRF-TOKEN": csrf_token} if csrf_token else {}),
        }
        cookies = {}
        if csrf_token:
            cookies["XSRF-TOKEN"] = csrf_token
        if _csrf_value:
            cookies["_csrf"] = _csrf_value
        return hdrs, cookies

    async def _seerr_family_sess(self, ssl=None) -> aiohttp.ClientSession:
        """Vrátí (nebo vytvoří) aiohttp session s cookie jar pro rodinný Overseerr účet."""
        if self._seerr_family_session is None or self._seerr_family_session.closed:
            self._seerr_family_session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
            await self._seerr_family_login(self._seerr_family_session, ssl=ssl)
        return self._seerr_family_session

    async def _seerr_family_login(self, session: aiohttp.ClientSession, ssl=None) -> None:
        """Přihlásí se do Overseerr jako rodinný účet (nastaví session cookie)."""
        base = self._cfg.get(CONF_SEERR_URL, "")
        # GET first to get CSRF cookies — Overseerr double-submit cookie pattern
        csrf_token = ""
        _csrf_value = ""
        try:
            async with session.get(f"{base}/api/v1/auth/me", ssl=ssl) as _:
                pass
            for cookie in session.cookie_jar:
                if cookie.key == "XSRF-TOKEN":
                    csrf_token = cookie.value
                if cookie.key == "_csrf":
                    _csrf_value = cookie.value
        except Exception:
            pass
        login_hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
        req_cookies = {}
        if csrf_token:
            login_hdrs["X-XSRF-TOKEN"] = csrf_token
            req_cookies["XSRF-TOKEN"] = csrf_token
        if _csrf_value:
            req_cookies["_csrf"] = _csrf_value
        async with session.post(f"{base}/api/v1/auth/local", json={
            "email": self._cfg[CONF_SEERR_FAMILY_EMAIL],
            "password": self._cfg[CONF_SEERR_FAMILY_PASS],
        }, headers=login_hdrs, cookies=req_cookies if req_cookies else None, ssl=ssl) as r:
            await r.read()

    # ── Router ───────────────────────────────────────────────────────────

    async def get(self, request: web.Request, service: str, path: str) -> web.Response:
        return await self._handle(request, service, path, "GET")

    async def post(self, request: web.Request, service: str, path: str) -> web.Response:
        return await self._handle(request, service, path, "POST")

    async def put(self, request: web.Request, service: str, path: str) -> web.Response:
        return await self._handle(request, service, path, "PUT")

    async def patch(self, request: web.Request, service: str, path: str) -> web.Response:
        return await self._handle(request, service, path, "PATCH")

    async def delete(self, request: web.Request, service: str, path: str) -> web.Response:
        return await self._handle(request, service, path, "DELETE")

    async def _handle(
        self, request: web.Request, service: str, path: str, method: str
    ) -> web.Response:
        try:
            return await self._route(request, service, path, method)
        except aiohttp.ClientConnectorError as exc:
            _LOGGER.error("arr_stack connection error [%s/%s]: %s", service, path, exc)
            return web.json_response({"error": f"Nelze se připojit: {exc}"}, status=503)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("arr_stack error [%s/%s]: %s", service, path, exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def _route(
        self, request: web.Request, service: str, path: str, method: str
    ) -> web.Response:
        debug = bool(request.query.get("_debug"))
        if debug:
            _LOGGER.debug("arr_stack → %s/%s [%s]", service, path, method)
        cfg = self._cfg
        http = async_get_clientsession(self._hass)
        ssl = False if cfg.get(CONF_SKIP_SSL_VERIFY) else None

        # ════════════════════════════════════════════
        # Capabilities — which services are configured
        # ════════════════════════════════════════════
        if service == "capabilities":
            seerr_url = cfg.get(CONF_SEERR_URL, '').lower()
            seerr_type = 'jellyseerr' if 'jelly' in seerr_url else 'overseerr'
            return web.json_response({
                "qbit":       bool(cfg.get(CONF_QBIT_URL)),
                "sabnzbd":    bool(cfg.get(CONF_SAB_URL)),
                "nzbget":     bool(cfg.get(CONF_NZBGET_URL)),
                "deluge":     bool(cfg.get(CONF_DELUGE_URL)),
                "rtorrent":   bool(cfg.get(CONF_RTORRENT_URL)),
                "radarr2":    bool(cfg.get(CONF_RADARR2_URL)),
                "sonarr2":    bool(cfg.get(CONF_SONARR2_URL)),
                "bazarr":     bool(cfg.get(CONF_BAZARR_URL)),
                "overseerr":  bool(cfg.get(CONF_SEERR_URL)),
                "plex":       bool(cfg.get(CONF_PLEX_TOKEN)),
                "tautulli":   bool(cfg.get(CONF_TAUTULLI_URL)),
                "jellystat":  bool(cfg.get(CONF_JELLYSTAT_URL)),
                "tracearr":   bool(cfg.get(CONF_TRACEARR_URL)),
                "trakt":      bool(cfg.get(CONF_TRAKT_CLIENT_ID)),
                "prowlarr":   bool(cfg.get(CONF_PROWLARR_URL)),
                "seerrType":  seerr_type,
            })

        # ════════════════════════════════════════════
        # qBittorrent
        # ════════════════════════════════════════════
        if service == "qbit":
            if not cfg.get(CONF_QBIT_URL):
                return web.json_response({"error": "qBittorrent not configured"}, status=503)
            qs = await self._qbit_sess()
            await self._qbit_login(qs, ssl=ssl)

            if path == "torrents":
                url = f"{cfg[CONF_QBIT_URL]}/api/v2/torrents/info?filter=all"
                if debug: _LOGGER.debug("arr_stack qbit → GET %s", url)
                async with qs.get(url, ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack qbit ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "transfer":
                async with qs.get(
                    f"{cfg[CONF_QBIT_URL]}/api/v2/transfer/info",
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "maindata":
                async with qs.get(
                    f"{cfg[CONF_QBIT_URL]}/api/v2/sync/maindata",
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "action" and method == "POST":
                body = await request.json()
                action = body.get("action", "")
                hash_ = body.get("hash", "all")
                delete_files = str(body.get("deleteFiles", False)).lower()

                if action not in QBIT_ENDPOINTS:
                    return web.json_response({"error": "unknown action"}, status=400)

                v5ep, v4ep = QBIT_ENDPOINTS[action]
                data = (
                    {"hashes": hash_, "deleteFiles": delete_files}
                    if action == "delete"
                    else {"hashes": "all" if action in ("pauseAll", "resumeAll") else hash_}
                )

                async with qs.post(
                    f"{cfg[CONF_QBIT_URL]}{v5ep}", data=data,
                    ssl=ssl,
                ) as r:
                    if r.status == 404 and v4ep != v5ep:
                        async with qs.post(
                            f"{cfg[CONF_QBIT_URL]}{v4ep}", data=data,
                            ssl=ssl,
                        ) as r2:
                            return web.json_response({"ok": r2.status == 200})
                    return web.json_response({"ok": r.status == 200})

        # ════════════════════════════════════════════
        # SABnzbd
        # ════════════════════════════════════════════
        elif service == "sabnzbd":
            base = cfg.get(CONF_SAB_URL, "")
            if not base:
                return web.json_response({"error": "SABnzbd not configured"}, status=503)
            key = cfg.get(CONF_SAB_KEY, "")

            if path == "queue":
                if debug: _LOGGER.debug("arr_stack sabnzbd → GET %s/api?mode=queue (apikey=REDACTED)", base)
                async with http.get(f"{base}/api?mode=queue&output=json&apikey={key}", ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack sabnzbd ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "history":
                async with http.get(
                    f"{base}/api?mode=history&output=json&limit=50&apikey={key}",
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "status":
                async with http.get(f"{base}/api?mode=status&output=json&apikey={key}", ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "action" and method == "POST":
                body = await request.json()
                mode = body.get("mode", "")
                name = body.get("name", "")
                nzo_id = body.get("nzo_id", "")
                url = f"{base}/api?mode={mode}&output=json&apikey={key}"
                if name:
                    url += f"&name={name}"
                if nzo_id:
                    url += f"&value={nzo_id}"
                async with http.get(url, ssl=ssl) as r:
                    return web.json_response({"ok": r.status == 200})

        # ════════════════════════════════════════════
        # NZBGet
        # ════════════════════════════════════════════
        elif service == "nzbget":
            base = cfg.get(CONF_NZBGET_URL, "").rstrip("/")
            if not base:
                return web.json_response({"error": "NZBGet not configured"}, status=503)
            nzbget_user = cfg.get(CONF_NZBGET_USER, "") or "nzbget"
            nzbget_pass = cfg.get(CONF_NZBGET_PASS, "") or ""
            _nzbget_creds = f"{nzbget_user}:{nzbget_pass}"
            _nzbget_auth_header = base64.b64encode(_nzbget_creds.encode('utf-8')).decode('ascii')
            _nzbget_headers = {"Authorization": f"Basic {_nzbget_auth_header}"}
            rpc_url = f"{base}/jsonrpc"

            async def _nzbget_rpc(rpc_method, params=None):
                async with http.post(
                    rpc_url,
                    json={"method": rpc_method, "params": params or []},
                    headers=_nzbget_headers,
                    ssl=ssl,
                ) as r:
                    return await r.json()

            if path == "queue":
                if debug: _LOGGER.debug("arr_stack nzbget → listgroups")
                data = await _nzbget_rpc("listgroups", [0])
                if debug: _LOGGER.debug("arr_stack nzbget ← listgroups %s items", len(data.get("result") or []))
                return web.json_response(data)

            if path == "status":
                data = await _nzbget_rpc("status")
                return web.json_response(data)

            if path == "history":
                data = await _nzbget_rpc("history", [False])
                return web.json_response(data)

            if path == "action" and method == "POST":
                body = await request.json()
                mode = body.get("mode", "")
                nzbid = body.get("id")

                if mode == "pause":
                    data = await _nzbget_rpc("pausedownload")
                elif mode == "resume":
                    data = await _nzbget_rpc("resumedownload")
                elif mode in ("group_pause", "group_resume", "group_delete", "group_redownload"):
                    cmd_map = {"group_pause": "GroupPause", "group_resume": "GroupResume", "group_delete": "GroupDelete", "group_redownload": "HistoryRedownload"}
                    data = await _nzbget_rpc("editqueue", [cmd_map[mode], "", [int(nzbid)]])
                else:
                    return web.json_response({"error": "unknown mode"}, status=400)
                return web.json_response({"ok": data.get("result", False)})

        # ════════════════════════════════════════════
        # Deluge
        # ════════════════════════════════════════════
        elif service == "deluge":
            base     = cfg.get(CONF_DELUGE_URL, "").rstrip("/")
            password = cfg.get(CONF_DELUGE_PASS, "") or ""
            rpc_url  = f"{base}/json"

            async def _deluge_rpc(method, params=None, *, _session):
                async with _session.post(
                    rpc_url,
                    json={"method": method, "params": params or [], "id": 1},
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    return await r.json()

            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(cookie_jar=jar) as http:
                await _deluge_rpc("auth.login", [password], _session=http)

                if path == "queue":
                    fields = ["name", "state", "progress", "download_payload_rate",
                              "upload_payload_rate", "total_size", "total_done",
                              "num_seeds", "num_peers", "eta", "hash"]
                    data = await _deluge_rpc("core.get_torrents_status", [{}, fields], _session=http)
                    raw = data.get("result") or {}
                    torrents = [{"hash": h, **v} for h, v in raw.items()]
                    return web.json_response(torrents)

                elif path == "status":
                    data = await _deluge_rpc("core.get_transfer_info", [], _session=http)
                    return web.json_response(data.get("result") or {})

                elif path == "action":
                    body = await request.json()
                    mode = body.get("action", "")
                    torrent_id = body.get("id", "")

                    if mode == "global_pause":
                        await _deluge_rpc("core.pause_all_torrents", [], _session=http)
                    elif mode == "global_resume":
                        await _deluge_rpc("core.resume_all_torrents", [], _session=http)
                    elif mode == "pause" and torrent_id:
                        await _deluge_rpc("core.pause_torrent", [[torrent_id]], _session=http)
                    elif mode == "resume" and torrent_id:
                        await _deluge_rpc("core.resume_torrent", [[torrent_id]], _session=http)
                    elif mode == "delete" and torrent_id:
                        await _deluge_rpc("core.remove_torrent", [torrent_id, False], _session=http)
                    elif mode == "delete_files" and torrent_id:
                        await _deluge_rpc("core.remove_torrent", [torrent_id, True], _session=http)
                    else:
                        return web.json_response({"error": "unknown mode"}, status=400)
                    return web.json_response({"ok": True})

        # ════════════════════════════════════════════
        # rTorrent (via ruTorrent XMLRPC)
        # ════════════════════════════════════════════
        elif service == "rtorrent":
            base = cfg.get(CONF_RTORRENT_URL, "").rstrip("/")
            if not base:
                return web.json_response({"error": "rTorrent not configured"}, status=503)
            rpc_url = f"{base}/RPC2"
            user    = cfg.get(CONF_RTORRENT_USER, "") or ""
            passwd  = cfg.get(CONF_RTORRENT_PASS, "") or ""
            auth    = aiohttp.BasicAuth(user, passwd) if user else None

            async def _rpc(method, params=()):
                body = _xmlrpc.dumps(tuple(params), method)
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        rpc_url,
                        data=body,
                        headers={"Content-Type": "text/xml"},
                        auth=auth,
                        ssl=ssl,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as r:
                        raw = await r.read()
                        return _xmlrpc.loads(raw)[0][0]

            if path == "queue":
                fields = [
                    "d.hash=", "d.name=", "d.size_bytes=", "d.completed_bytes=",
                    "d.down.rate=", "d.up.rate=", "d.is_active=", "d.is_open=",
                    "d.is_hash_checking=", "d.message=", "d.peers_connected=",
                    "d.peers_not_connected=",
                ]
                rows = await _rpc("d.multicall2", ["", "main"] + fields)
                torrents = []
                for row in rows:
                    h, name, size, done, dl, ul, active, is_open, checking, message, peers_c, peers_nc = row
                    pct = round(done * 100 / size) if size > 0 else 0
                    remaining = (size - done)
                    eta = int(remaining / dl) if dl > 0 else 0
                    if checking:
                        state = "Checking"
                    elif message and not active:
                        state = "Error"
                    elif not is_open or (not active and not checking):
                        state = "Paused"
                    elif done >= size and size > 0:
                        state = "Seeding"
                    else:
                        state = "Downloading"
                    torrents.append({
                        "hash":                 h,
                        "name":                 name,
                        "progress":             pct,
                        "download_payload_rate": dl,
                        "upload_payload_rate":   ul,
                        "total_size":            size,
                        "total_done":            done,
                        "eta":                   eta,
                        "num_peers":             peers_c + peers_nc,
                        "num_seeds":             peers_c,
                        "state":                 state,
                        "message":               message,
                    })
                return web.json_response(torrents)

            elif path == "status":
                result = await _rpc("system.multicall", [[
                    {"methodName": "throttle.global_down.rate", "params": []},
                    {"methodName": "throttle.global_up.rate",   "params": []},
                ]])
                dl_rate = result[0][0] if result else 0
                ul_rate = result[1][0] if len(result) > 1 else 0
                return web.json_response({
                    "download_rate": dl_rate,
                    "upload_rate":   ul_rate,
                    "free_space":    0,
                })

            elif path == "action":
                body_data = await request.json()
                mode      = body_data.get("action", "")
                hash_id   = body_data.get("id", "")
                if mode == "global_pause":
                    rows = await _rpc("d.multicall2", ["", "main", "d.hash="])
                    for (h,) in rows:
                        await _rpc("d.pause", [h])
                elif mode == "global_resume":
                    rows = await _rpc("d.multicall2", ["", "main", "d.hash="])
                    for (h,) in rows:
                        await _rpc("d.resume", [h])
                elif mode == "pause" and hash_id:
                    await _rpc("d.pause", [hash_id])
                elif mode == "resume" and hash_id:
                    await _rpc("d.resume", [hash_id])
                elif mode == "delete" and hash_id:
                    await _rpc("d.erase", [hash_id])
                elif mode == "delete_files" and hash_id:
                    await _rpc("d.delete_tied", [hash_id])
                    await _rpc("d.erase", [hash_id])
                else:
                    return web.json_response({"error": "unknown mode"}, status=400)
                return web.json_response({"ok": True})

        # ════════════════════════════════════════════
        # Radarr
        # ════════════════════════════════════════════
        elif service == "radarr":
            base = cfg.get(CONF_RADARR_URL, "")
            hdrs = {"X-Api-Key": cfg.get(CONF_RADARR_KEY, "")}

            if path == "movies":
                url = f"{base}/api/v3/movie"
                if debug: _LOGGER.debug("arr_stack radarr → GET %s", url)
                async with http.get(url, headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack radarr ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "profiles":
                async with http.get(
                    f"{base}/api/v3/qualityprofile", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "tags":
                async with http.get(f"{base}/api/v3/tag", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "qualitydefs":
                async with http.get(f"{base}/api/v3/qualitydefinition", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "languages":
                async with http.get(f"{base}/api/v3/language", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "rootfolders":
                async with http.get(f"{base}/api/v3/rootfolder", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "diskspace":
                async with http.get(f"{base}/api/v3/diskspace", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "queue":
                incl = request.query.get("includeUnknownMovieItems", "false")
                async with http.get(
                    f"{base}/api/v3/queue?includeMovie=false&pageSize=100&includeUnknownMovieItems={incl}",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            # Interactive Search — live dotaz na všechny indexery (může trvat 10–60s)
            if path == "release" and method == "GET":
                movie_id = request.query.get("movieId", "")
                if not movie_id:
                    return web.json_response({"error": "movieId required"}, status=400)
                timeout = aiohttp.ClientTimeout(total=120)
                async with http.get(
                    f"{base}/api/v3/release",
                    headers=hdrs,
                    params={"movieId": movie_id},
                    timeout=timeout,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "lookup" and method == "GET":
                term = request.query.get("term", "")
                async with http.get(
                    f"{base}/api/v3/movie/lookup",
                    headers=hdrs,
                    params={"term": term},
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Přidá film do Radarru (unmonitored, pro IS u filmů mimo knihovnu)
            if path == "movie" and method == "POST":
                body = await request.json()
                async with http.post(
                    f"{base}/api/v3/movie",
                    headers={**hdrs, "Content-Type": "application/json"},
                    json=body,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            # Smaže film z knihovny
            if path.startswith("movie/") and method == "DELETE":
                movie_id = path.split("/", 1)[1]
                delete_files = request.query.get("deleteFiles", "false")
                add_exclusion = request.query.get("addExclusion", "false")
                async with http.delete(
                    f"{base}/api/v3/movie/{movie_id}",
                    headers=hdrs,
                    params={"deleteFiles": delete_files, "addImportListExclusion": add_exclusion},
                    timeout=aiohttp.ClientTimeout(total=60),
                    ssl=ssl,
                ) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            # Grab — stáhne konkrétní release do download klienta
            if path == "release" and method == "POST":
                body = await request.json()
                async with http.post(
                    f"{base}/api/v3/release",
                    headers={**hdrs, "Content-Type": "application/json"},
                    json=body,
                    ssl=ssl,
                ) as r:
                    body_bytes = await r.read()
                    # Vracíme skutečné tělo odpovědi pro debugging
                    return web.Response(
                        body=body_bytes,
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "history" and method == "GET":
                movie_id = request.query.get("movieId", "")
                async with http.get(f"{base}/api/v3/history/movie", headers=hdrs, params={"movieId": movie_id, "pageSize": "200"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "command" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/command", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)


            if path == "wanted/missing" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "250")
                sort_key  = request.query.get("sortKey", "title")
                sort_dir  = request.query.get("sortDir", "asc")
                sort_dir  = "descending" if sort_dir in ("desc", "descending") else "ascending"
                async with http.get(f"{base}/api/v3/wanted/missing", headers=hdrs, params={"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeMovie": "true"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("movie/") and method == "PUT":
                movie_id = path.split("/", 1)[1]
                body = await request.json()
                async with http.put(f"{base}/api/v3/movie/{movie_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)


            if path == "manualimport" and method == "GET":
                download_id = request.query.get("downloadId", "")
                movie_id    = request.query.get("movieId", "")
                params = {"filterExistingFiles": "false"}
                if download_id: params["downloadId"] = download_id
                if movie_id:    params["movieId"]    = movie_id
                async with http.get(f"{base}/api/v3/manualimport", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "manualimport" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/manualimport", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/history" and method == "GET":
                page       = request.query.get("page", "1")
                page_size  = request.query.get("pageSize", "20")
                sort_key   = request.query.get("sortKey", "date")
                sort_dir   = request.query.get("sortDir", "desc")
                sort_dir   = "descending" if sort_dir in ("desc", "descending") else "ascending"
                event_type = request.query.get("eventType", "")
                _event_map = {"grabbed":2,"downloadFolderImported":3,"downloadFailed":4,"movieFileDeleted":5,"movieFolderImported":6,"movieFileRenamed":7,"episodeFileDeleted":5,"episodeFileRenamed":6,"downloadIgnored":7,"seriesFolderImported":8}
                params = {"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeMovie": "true"}
                if event_type:
                    params["eventType"] = _event_map.get(event_type, event_type)
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/blocklist" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "20")
                async with http.get(f"{base}/api/v3/blocklist", headers=hdrs, params={"page": page, "pageSize": page_size}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("activity/blocklist/") and method == "DELETE":
                bl_id = path.split("/")[-1]
                async with http.delete(f"{base}/api/v3/blocklist/{bl_id}", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("queue/") and method == "DELETE":
                q_id = path.split("/")[-1]
                remove = request.query.get("removeFromClient", "true")
                blocklist_param = request.query.get("blocklist", "false")
                skip = request.query.get("skipRedownload", "false")
                async with http.delete(f"{base}/api/v3/queue/{q_id}", headers=hdrs, params={"removeFromClient": remove, "blocklist": blocklist_param, "skipRedownload": skip}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

        # ════════════════════════════════════════════
        # Sonarr
        # ════════════════════════════════════════════
        elif service == "sonarr":
            base = cfg.get(CONF_SONARR_URL, "")
            hdrs = {"X-Api-Key": cfg.get(CONF_SONARR_KEY, "")}

            if path == "profiles":
                async with http.get(
                    f"{base}/api/v3/qualityprofile", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "tags":
                async with http.get(f"{base}/api/v3/tag", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "qualitydefs":
                async with http.get(f"{base}/api/v3/qualitydefinition", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "languages":
                async with http.get(f"{base}/api/v3/language", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "rootfolders":
                async with http.get(f"{base}/api/v3/rootfolder", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "diskspace":
                async with http.get(f"{base}/api/v3/diskspace", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "queue":
                async with http.get(f"{base}/api/v3/queue?pageSize=200&includeUnknownSeriesItems=false&includeEpisode=true&includeSeries=true", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "series" and method == "GET":
                url = f"{base}/api/v3/series"
                if debug: _LOGGER.debug("arr_stack sonarr → GET %s", url)
                async with http.get(url, headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack sonarr ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "series" and method == "POST":
                body = await request.json()
                async with http.post(
                    f"{base}/api/v3/series",
                    headers={**hdrs, "Content-Type": "application/json"},
                    json=body,
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "lookup" and method == "GET":
                tvdb_id = request.query.get("tvdbId", "")
                term = f"tvdb:{tvdb_id}" if tvdb_id else request.query.get("term", "")
                async with http.get(
                    f"{base}/api/v3/series/lookup",
                    headers=hdrs,
                    params={"term": term},
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "calendar":
                # Přepošli query parametry (start, end) z karty
                params = {**dict(request.query), "includeSeries": "true", "unmonitored": "false"}
                async with http.get(
                    f"{base}/api/v3/calendar", headers=hdrs, params=params,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "episodes" and method == "GET":
                params = {"seriesId": request.query.get("seriesId", "")}
                if request.query.get("seasonNumber"):
                    params["seasonNumber"] = request.query["seasonNumber"]
                async with http.get(f"{base}/api/v3/episode", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "release" and method == "GET":
                timeout = aiohttp.ClientTimeout(total=120)
                params = {k: v for k, v in request.query.items()}
                async with http.get(f"{base}/api/v3/release", headers=hdrs, params=params, timeout=timeout, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "release" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/release", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "history" and method == "GET":
                series_id = request.query.get("seriesId", "")
                async with http.get(f"{base}/api/v3/history/series", headers=hdrs, params={"seriesId": series_id, "pageSize": "200"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "episodefiles" and method == "GET":
                series_id = request.query.get("seriesId", "")
                async with http.get(f"{base}/api/v3/episodefile", headers=hdrs, params={"seriesId": series_id}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "recentimports" and method == "GET":
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params={"pageSize": "100", "sortKey": "date", "sortDir": "desc"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("series/") and method == "PUT":
                series_id = path.split("/", 1)[1]
                body = await request.json()
                async with http.put(f"{base}/api/v3/series/{series_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "command" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/command", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "wanted/missing" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "250")
                sort_key  = request.query.get("sortKey", "airDateUtc")
                sort_dir  = request.query.get("sortDir", "desc")
                sort_dir  = "descending" if sort_dir in ("desc", "descending") else "ascending"
                req_url = f"{base}/api/v3/wanted/missing"
                req_params = {"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeSeries": "true"}
                _LOGGER.debug("arr_stack sonarr wanted/missing → GET %s params=%s", req_url, req_params)
                async with http.get(req_url, headers=hdrs, params=req_params, ssl=ssl) as r:
                    body = await r.read()
                    _LOGGER.debug("arr_stack sonarr wanted/missing ← status=%s body_start=%s", r.status, body[:200])
                    return web.Response(body=body, content_type="application/json", status=r.status)

            # Smaže seriál z knihovny
            if path.startswith("series/") and method == "DELETE":
                series_id = path.split("/", 1)[1]
                delete_files = request.query.get("deleteFiles", "false")
                add_exclusion = request.query.get("addExclusion", "false")
                async with http.delete(
                    f"{base}/api/v3/series/{series_id}",
                    headers=hdrs,
                    params={"deleteFiles": delete_files, "addImportListExclusion": add_exclusion},
                    timeout=aiohttp.ClientTimeout(total=60),
                    ssl=ssl,
                ) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            if path == "manualimport" and method == "GET":
                download_id = request.query.get("downloadId", "")
                series_id   = request.query.get("seriesId", "")
                params = {"filterExistingFiles": "false"}
                if download_id: params["downloadId"] = download_id
                if series_id:   params["seriesId"]   = series_id
                async with http.get(f"{base}/api/v3/manualimport", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "manualimport" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/manualimport", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Activity — global history (paginated)
            if path == "activity/history" and method == "GET":
                page       = request.query.get("page", "1")
                page_size  = request.query.get("pageSize", "20")
                sort_key   = request.query.get("sortKey", "date")
                sort_dir   = request.query.get("sortDir", "desc")
                sort_dir   = "descending" if sort_dir in ("desc", "descending") else "ascending"
                event_type = request.query.get("eventType", "")
                _event_map = {"grabbed":2,"downloadFolderImported":3,"downloadFailed":4,"episodeFileDeleted":5,"episodeFileRenamed":6,"downloadIgnored":7,"seriesFolderImported":8}
                params = {"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeSeries": "true", "includeEpisode": "true"}
                if event_type:
                    params["eventType"] = _event_map.get(event_type, event_type)
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Activity — blocklist
            if path == "activity/blocklist" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "50")
                async with http.get(f"{base}/api/v3/blocklist", headers=hdrs, params={"page": page, "pageSize": page_size, "sortKey": "date", "sortDirection": "descending"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Activity — delete from blocklist
            if path.startswith("activity/blocklist/") and method == "DELETE":
                bl_id = path.split("/", 2)[2]
                async with http.delete(f"{base}/api/v3/blocklist/{bl_id}", headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            # Activity — remove from queue
            if path.startswith("queue/") and method == "DELETE":
                q_id               = path.split("/", 1)[1]
                remove_from_client = request.query.get("removeFromClient", "true")
                blocklist_it       = request.query.get("blocklist", "false")
                skip_redownload    = request.query.get("skipRedownload", "false")
                async with http.delete(
                    f"{base}/api/v3/queue/{q_id}",
                    headers=hdrs,
                    params={"removeFromClient": remove_from_client, "blocklist": blocklist_it, "skipRedownload": skip_redownload},
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=ssl,
                ) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

        # ════════════════════════════════════════════
        # Radarr 2
        # ════════════════════════════════════════════
        elif service == "radarr2":
            if not cfg.get(CONF_RADARR2_URL):
                return web.json_response({"_notConfigured": True})
            base = cfg.get(CONF_RADARR2_URL, "")
            hdrs = {"X-Api-Key": cfg.get(CONF_RADARR2_KEY, "")}

            if path == "movies":
                url = f"{base}/api/v3/movie"
                if debug: _LOGGER.debug("arr_stack radarr2 → GET %s", url)
                async with http.get(url, headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack radarr2 ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "profiles":
                async with http.get(f"{base}/api/v3/qualityprofile", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "tags":
                async with http.get(f"{base}/api/v3/tag", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "qualitydefs":
                async with http.get(f"{base}/api/v3/qualitydefinition", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "languages":
                async with http.get(f"{base}/api/v3/language", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "rootfolders":
                async with http.get(f"{base}/api/v3/rootfolder", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "diskspace":
                async with http.get(f"{base}/api/v3/diskspace", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "queue":
                async with http.get(f"{base}/api/v3/queue?includeMovie=false&pageSize=100", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "release" and method == "GET":
                movie_id = request.query.get("movieId", "")
                if not movie_id:
                    return web.json_response({"error": "movieId required"}, status=400)
                timeout = aiohttp.ClientTimeout(total=120)
                async with http.get(f"{base}/api/v3/release", headers=hdrs, params={"movieId": movie_id}, timeout=timeout, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "movie" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/movie", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("movie/") and method == "DELETE":
                movie_id = path.split("/", 1)[1]
                delete_files = request.query.get("deleteFiles", "false")
                add_exclusion = request.query.get("addExclusion", "false")
                async with http.delete(
                    f"{base}/api/v3/movie/{movie_id}",
                    headers=hdrs,
                    params={"deleteFiles": delete_files, "addImportListExclusion": add_exclusion},
                    timeout=aiohttp.ClientTimeout(total=60),
                    ssl=ssl,
                ) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            if path == "release" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/release", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "history" and method == "GET":
                movie_id = request.query.get("movieId", "")
                async with http.get(f"{base}/api/v3/history/movie", headers=hdrs, params={"movieId": movie_id, "pageSize": "200"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "command" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/command", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "wanted/missing" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "250")
                sort_key  = request.query.get("sortKey", "title")
                sort_dir  = request.query.get("sortDir", "asc")
                sort_dir  = "descending" if sort_dir in ("desc", "descending") else "ascending"
                async with http.get(f"{base}/api/v3/wanted/missing", headers=hdrs, params={"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeMovie": "true"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("movie/") and method == "PUT":
                movie_id = path.split("/", 1)[1]
                body = await request.json()
                async with http.put(f"{base}/api/v3/movie/{movie_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)



            if path == "manualimport" and method == "GET":
                download_id = request.query.get("downloadId", "")
                movie_id    = request.query.get("movieId", "")
                params = {"filterExistingFiles": "false"}
                if download_id: params["downloadId"] = download_id
                if movie_id:    params["movieId"]    = movie_id
                async with http.get(f"{base}/api/v3/manualimport", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "manualimport" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/manualimport", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/history" and method == "GET":
                page       = request.query.get("page", "1")
                page_size  = request.query.get("pageSize", "20")
                sort_key   = request.query.get("sortKey", "date")
                sort_dir   = request.query.get("sortDir", "desc")
                sort_dir   = "descending" if sort_dir in ("desc", "descending") else "ascending"
                event_type = request.query.get("eventType", "")
                _event_map = {"grabbed":2,"downloadFolderImported":3,"downloadFailed":4,"movieFileDeleted":5,"movieFolderImported":6,"movieFileRenamed":7,"episodeFileDeleted":5,"episodeFileRenamed":6,"downloadIgnored":7,"seriesFolderImported":8}
                params = {"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeMovie": "true"}
                if event_type:
                    params["eventType"] = _event_map.get(event_type, event_type)
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/blocklist" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "20")
                async with http.get(f"{base}/api/v3/blocklist", headers=hdrs, params={"page": page, "pageSize": page_size}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("activity/blocklist/") and method == "DELETE":
                bl_id = path.split("/")[-1]
                async with http.delete(f"{base}/api/v3/blocklist/{bl_id}", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("queue/") and method == "DELETE":
                q_id = path.split("/")[-1]
                remove = request.query.get("removeFromClient", "true")
                blocklist_param = request.query.get("blocklist", "false")
                skip = request.query.get("skipRedownload", "false")
                async with http.delete(f"{base}/api/v3/queue/{q_id}", headers=hdrs, params={"removeFromClient": remove, "blocklist": blocklist_param, "skipRedownload": skip}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

        # ════════════════════════════════════════════
        # Sonarr 4K
        # ════════════════════════════════════════════
        elif service == "sonarr2":
            if not cfg.get(CONF_SONARR2_URL):
                return web.json_response({"_notConfigured": True})
            base = cfg.get(CONF_SONARR2_URL, "")
            hdrs = {"X-Api-Key": cfg.get(CONF_SONARR2_KEY, "")}

            if path == "profiles":
                async with http.get(f"{base}/api/v3/qualityprofile", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "tags":
                async with http.get(f"{base}/api/v3/tag", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "qualitydefs":
                async with http.get(f"{base}/api/v3/qualitydefinition", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "languages":
                async with http.get(f"{base}/api/v3/language", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "rootfolders":
                async with http.get(f"{base}/api/v3/rootfolder", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "diskspace":
                async with http.get(f"{base}/api/v3/diskspace", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "queue":
                async with http.get(f"{base}/api/v3/queue?pageSize=200&includeUnknownSeriesItems=false&includeEpisode=true&includeSeries=true", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "series" and method == "GET":
                url = f"{base}/api/v3/series"
                if debug: _LOGGER.debug("arr_stack sonarr2 → GET %s", url)
                async with http.get(url, headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    if debug: _LOGGER.debug("arr_stack sonarr2 ← status=%s len=%s", r.status, len(body))
                    return web.Response(body=body, content_type="application/json", status=r.status)

            if path == "series" and method == "POST":
                body = await request.json()
                async with http.post(
                    f"{base}/api/v3/series",
                    headers={**hdrs, "Content-Type": "application/json"},
                    json=body,
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "release" and method == "GET":
                timeout = aiohttp.ClientTimeout(total=120)
                params = {k: v for k, v in request.query.items()}
                async with http.get(f"{base}/api/v3/release", headers=hdrs, params=params, timeout=timeout, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "release" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/release", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "lookup" and method == "GET":
                tvdb_id = request.query.get("tvdbId", "")
                term = f"tvdb:{tvdb_id}" if tvdb_id else request.query.get("term", "")
                async with http.get(f"{base}/api/v3/series/lookup", headers=hdrs, params={"term": term}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "calendar":
                params = {**dict(request.query), "includeSeries": "true", "unmonitored": "false"}
                async with http.get(f"{base}/api/v3/calendar", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "episodes" and method == "GET":
                params = {"seriesId": request.query.get("seriesId", "")}
                if request.query.get("seasonNumber"):
                    params["seasonNumber"] = request.query["seasonNumber"]
                async with http.get(f"{base}/api/v3/episode", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "episodefiles" and method == "GET":
                series_id = request.query.get("seriesId", "")
                async with http.get(f"{base}/api/v3/episodefile", headers=hdrs, params={"seriesId": series_id}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "history" and method == "GET":
                series_id = request.query.get("seriesId", "")
                async with http.get(f"{base}/api/v3/history/series", headers=hdrs, params={"seriesId": series_id, "pageSize": "200"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "recentimports" and method == "GET":
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params={"pageSize": "100", "sortKey": "date", "sortDir": "desc"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("series/") and method == "PUT":
                series_id = path.split("/", 1)[1]
                body = await request.json()
                async with http.put(f"{base}/api/v3/series/{series_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("series/") and method == "DELETE":
                series_id = path.split("/", 1)[1]
                delete_files = request.query.get("deleteFiles", "false")
                add_exclusion = request.query.get("addExclusion", "false")
                async with http.delete(
                    f"{base}/api/v3/series/{series_id}",
                    headers=hdrs,
                    params={"deleteFiles": delete_files, "addImportListExclusion": add_exclusion},
                    timeout=aiohttp.ClientTimeout(total=60),
                    ssl=ssl,
                ) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            if path == "command" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/command", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "wanted/missing" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "250")
                sort_key  = request.query.get("sortKey", "airDateUtc")
                sort_dir  = request.query.get("sortDir", "desc")
                sort_dir  = "descending" if sort_dir in ("desc", "descending") else "ascending"
                async with http.get(f"{base}/api/v3/wanted/missing", headers=hdrs, params={"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeSeries": "true"}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)


            if path == "manualimport" and method == "GET":
                download_id = request.query.get("downloadId", "")
                series_id   = request.query.get("seriesId", "")
                params = {"filterExistingFiles": "false"}
                if download_id: params["downloadId"] = download_id
                if series_id:   params["seriesId"]   = series_id
                async with http.get(f"{base}/api/v3/manualimport", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "manualimport" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v3/manualimport", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/history" and method == "GET":
                page       = request.query.get("page", "1")
                page_size  = request.query.get("pageSize", "20")
                sort_key   = request.query.get("sortKey", "date")
                sort_dir   = request.query.get("sortDir", "desc")
                sort_dir   = "descending" if sort_dir in ("desc", "descending") else "ascending"
                event_type = request.query.get("eventType", "")
                _event_map = {"grabbed":2,"downloadFolderImported":3,"downloadFailed":4,"movieFileDeleted":5,"movieFolderImported":6,"movieFileRenamed":7,"episodeFileDeleted":5,"episodeFileRenamed":6,"downloadIgnored":7,"seriesFolderImported":8}
                params = {"page": page, "pageSize": page_size, "sortKey": sort_key, "sortDirection": sort_dir, "includeSeries": "true", "includeEpisode": "true"}
                if event_type:
                    params["eventType"] = _event_map.get(event_type, event_type)
                async with http.get(f"{base}/api/v3/history", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "activity/blocklist" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "20")
                async with http.get(f"{base}/api/v3/blocklist", headers=hdrs, params={"page": page, "pageSize": page_size}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("activity/blocklist/") and method == "DELETE":
                bl_id = path.split("/")[-1]
                async with http.delete(f"{base}/api/v3/blocklist/{bl_id}", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path.startswith("queue/") and method == "DELETE":
                q_id = path.split("/")[-1]
                remove = request.query.get("removeFromClient", "true")
                blocklist_param = request.query.get("blocklist", "false")
                skip = request.query.get("skipRedownload", "false")
                async with http.delete(f"{base}/api/v3/queue/{q_id}", headers=hdrs, params={"removeFromClient": remove, "blocklist": blocklist_param, "skipRedownload": skip}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

        # ════════════════════════════════════════════
        # Overseerr
        # ════════════════════════════════════════════
        elif service == "overseerr":
            base = cfg.get(CONF_SEERR_URL, "")
            if not base:
                return web.json_response([], status=200)
            hdrs = {
                "X-Api-Key": cfg.get(CONF_SEERR_KEY, ""),
                "Accept": "application/json",
            }

            if path == "upcoming":
                page = request.query.get("page", "1")
                async with http.get(
                    f"{base}/api/v1/discover/movies/upcoming?page={page}",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "popular":
                page = request.query.get("page", "1")
                async with http.get(
                    f"{base}/api/v1/discover/movies?page={page}",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "trending":
                page = request.query.get("page", "1")
                async with http.get(
                    f"{base}/api/v1/discover/trending?page={page}",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "tv_upcoming":
                page = request.query.get("page", "1")
                async with http.get(
                    f"{base}/api/v1/discover/tv/upcoming?page={page}",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "radarr_settings":
                async with http.get(
                    f"{base}/api/v1/settings/radarr", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "sonarr_settings":
                async with http.get(
                    f"{base}/api/v1/settings/sonarr", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path.startswith("movie/") or path.startswith("tv/"):
                async with http.get(
                    f"{base}/api/v1/{path}", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "pending":
                async with http.get(
                    f"{base}/api/v1/request?filter=pending&take=20",
                    headers=hdrs,
                    ssl=ssl,
                ) as r:
                    data = await r.json()

                # Obohaťte každý request o posterPath + title z Overseerr media endpointu
                async def _enrich(req: dict) -> None:
                    media = req.get("media") or {}
                    tmdb_id = media.get("tmdbId")
                    if not tmdb_id:
                        return
                    # Přeskočit pokud už máme obě pole
                    if media.get("posterPath") and media.get("title"):
                        return
                    ep = "movie" if req.get("type") == "movie" else "tv"
                    try:
                        async with http.get(
                            f"{base}/api/v1/{ep}/{tmdb_id}", headers=hdrs,
                            ssl=ssl,
                        ) as mr:
                            if mr.status == 200:
                                detail = await mr.json()
                                media.setdefault("posterPath",   detail.get("posterPath"))
                                media.setdefault("title",        detail.get("title") or detail.get("name"))
                                media.setdefault("originalTitle", detail.get("originalTitle") or detail.get("originalName"))
                    except Exception:
                        pass

                await asyncio.gather(*[_enrich(r) for r in (data.get("results") or [])])
                return web.json_response(data)

            # Pending requesty family účtu (přes session cookie) — pro non-admin kartu
            if path == "my_pending":
                if not self._cfg.get(CONF_SEERR_FAMILY_EMAIL):
                    return web.json_response({"results": []})
                try:
                    params = {"filter": "all", "take": "100"}
                    hdrs_json = {"Accept": "application/json"}
                    fs = await self._seerr_family_sess(ssl=ssl)
                    async with fs.get(
                        f"{base}/api/v1/request",
                        params=params,
                        headers=hdrs_json,
                        ssl=ssl,
                    ) as r:
                        if r.status == 401:
                            await self._seerr_family_login(fs, ssl=ssl)
                            async with fs.get(
                                f"{base}/api/v1/request",
                                params=params,
                                headers=hdrs_json,
                                ssl=ssl,
                            ) as r2:
                                if r2.status == 200:
                                    return web.Response(body=await r2.read(),
                                                        content_type="application/json")
                                return web.json_response({"results": []})
                        if r.status == 200:
                            return web.Response(body=await r.read(),
                                                content_type="application/json")
                        return web.json_response({"results": []})
                except Exception:
                    return web.json_response({"results": []})

            if path == "request_delete" and method == "POST":
                body = await request.json()
                req_id = body.get("requestId")
                adsess = await self._seerr_admin_sess()
                csrf_hdrs, csrf_cookies = await self._seerr_csrf_hdrs(base, cfg.get(CONF_SEERR_KEY, ""), ssl)
                async with adsess.delete(
                    f"{base}/api/v1/request/{req_id}", headers=csrf_hdrs,
                    cookies=csrf_cookies or None, ssl=ssl,
                ) as r:
                    return web.json_response({"ok": r.status in (200, 204)})

            if path.startswith("request/") and method == "PUT":
                req_id = path.split("/", 1)[1]
                body = await request.json()
                adsess = await self._seerr_admin_sess()
                csrf_hdrs, csrf_cookies = await self._seerr_csrf_hdrs(base, cfg.get(CONF_SEERR_KEY, ""), ssl)
                async with adsess.put(
                    f"{base}/api/v1/request/{req_id}",
                    headers=csrf_hdrs, cookies=csrf_cookies or None,
                    json=body, ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "approve" and method == "POST":
                body = await request.json()
                req_id = body.get("requestId")
                server_settings = {k: v for k, v in body.items() if k != "requestId" and v is not None}
                adsess = await self._seerr_admin_sess()
                csrf_hdrs, csrf_cookies = await self._seerr_csrf_hdrs(base, cfg.get(CONF_SEERR_KEY, ""), ssl)
                # Step 1: update request with server settings if provided
                if server_settings:
                    _LOGGER.debug("arr_stack approve → updating requestId=%s settings=%s", req_id, server_settings)
                    async with adsess.put(
                        f"{base}/api/v1/request/{req_id}",
                        headers=csrf_hdrs, cookies=csrf_cookies or None,
                        json=server_settings, ssl=ssl,
                    ) as r_put:
                        put_status = r_put.status
                        _LOGGER.debug("arr_stack approve → PUT status=%s", put_status)
                # Step 2: approve
                async with adsess.post(
                    f"{base}/api/v1/request/{req_id}/approve",
                    headers=csrf_hdrs, cookies=csrf_cookies or None,
                    json={}, ssl=ssl,
                ) as r:
                    resp_body = await r.read()
                    _LOGGER.debug("arr_stack approve ← status=%s body=%s", r.status, resp_body[:300])
                    return web.Response(
                        body=resp_body,
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "decline" and method == "POST":
                body = await request.json()
                req_id = body.get("requestId")
                adsess = await self._seerr_admin_sess()
                csrf_hdrs, csrf_cookies = await self._seerr_csrf_hdrs(base, cfg.get(CONF_SEERR_KEY, ""), ssl)
                async with adsess.post(
                    f"{base}/api/v1/request/{req_id}/decline",
                    headers=csrf_hdrs, cookies=csrf_cookies or None,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "search":
                body = await request.json()
                query = body.get("query", "")
                page = str(body.get("page", 1))
                url_str = f"{base}/api/v1/search?query={quote(query, safe='')}&page={page}"
                search_url = yarl.URL(url_str, encoded=True)
                async with http.get(search_url, headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            if path == "request" and method == "POST":
                body = await request.json()
                user_mode = body.pop("userMode", None)

                # Rodinný účet — použij session cookie místo admin API klíče
                if user_mode == "family" and self._cfg.get(CONF_SEERR_FAMILY_EMAIL):
                    fs = await self._seerr_family_sess(ssl=ssl)
                    fam_hdrs = {"Accept": "application/json", "Content-Type": "application/json"}
                    csrf_xtra, csrf_ck = self._csrf_from_jar(fs)
                    fam_hdrs.update(csrf_xtra)
                    async with fs.post(
                        f"{base}/api/v1/request",
                        json=body, headers=fam_hdrs,
                        cookies=csrf_ck or None, ssl=ssl,
                    ) as r:
                        if r.status in (401, 403):
                            # Session vypršela nebo CSRF mismatch — znovu přihlásit a zkusit
                            await self._seerr_family_login(fs, ssl=ssl)
                            csrf_xtra2, csrf_ck2 = self._csrf_from_jar(fs)
                            fam_hdrs2 = {"Accept": "application/json", "Content-Type": "application/json"}
                            fam_hdrs2.update(csrf_xtra2)
                            async with fs.post(
                                f"{base}/api/v1/request",
                                json=body, headers=fam_hdrs2,
                                cookies=csrf_ck2 or None, ssl=ssl,
                            ) as r2:
                                return web.Response(
                                    body=await r2.read(),
                                    content_type="application/json",
                                    status=r2.status,
                                )
                        return web.Response(
                            body=await r.read(),
                            content_type="application/json",
                            status=r.status,
                        )

                # Admin — použij API klíč (auto-approve)
                adsess = await self._seerr_admin_sess()
                csrf_hdrs, csrf_cookies = await self._seerr_csrf_hdrs(base, cfg.get(CONF_SEERR_KEY, ""), ssl)
                async with adsess.post(
                    f"{base}/api/v1/request",
                    headers=csrf_hdrs, cookies=csrf_cookies or None,
                    json=body, ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

        # ════════════════════════════════════════════
        # Bazarr (volitelný)
        # ════════════════════════════════════════════
        elif service == "bazarr":
            base = cfg.get(CONF_BAZARR_URL, "")
            if not base:
                return web.json_response({"data": []})
            hdrs = {
                "X-API-KEY": cfg.get(CONF_BAZARR_KEY, ""),
                "Accept": "application/json",
            }

            if path == "movies":
                async with http.get(
                    f"{base}/api/movies?start=0&length=500", headers=hdrs,
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            if path == "episodes":
                series_id = request.query.get("seriesId", "")
                async with http.get(
                    f"{base}/api/episodes",
                    headers=hdrs,
                    params={"seriesid[]": series_id, "start": "0", "length": "500"},
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

        # ════════════════════════════════════════════
        # Plex (volitelný)
        # ════════════════════════════════════════════
        elif service == "plex":
            token = cfg.get(CONF_PLEX_TOKEN, "")
            if not token:
                return web.json_response([], status=200)
            base = cfg.get(CONF_PLEX_URL, "").rstrip("/")
            if not base:
                # No manual URL — lazy auto-detect and cache
                if not self._plex_url_cache:
                    self._plex_url_cache = await _plex_detect_server(
                        async_get_clientsession(self._hass), token
                    )
                base = self._plex_url_cache or ""
            else:
                self._plex_url_cache = None  # manual URL set — invalidate cache
            if not base:
                return web.json_response([], status=200)

            plex_hdrs = {
                "X-Plex-Token":             token,
                "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
                "Accept":                   "application/json",
            }

            # GET plex/image → proxy Plex artwork (no JSON Accept header for images)
            if path == "image" and method == "GET":
                img_path = request.rel_url.query.get("path", "")
                if not img_path:
                    return web.Response(status=400)
                img_hdrs = {
                    "X-Plex-Token":             token,
                    "X-Plex-Client-Identifier": PLEX_CLIENT_ID,
                }
                async with http.get(
                    f"{base}{img_path}",
                    headers=img_hdrs,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    ct = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                    return web.Response(body=await r.read(), content_type=ct, status=r.status)

            # GET plex/clients → /clients (registered players with ports)
            if path == "clients" and method == "GET":
                async with http.get(
                    f"{base}/clients",
                    headers=plex_hdrs,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    return web.Response(
                        body=await r.read(),
                        content_type="application/json",
                        status=r.status,
                    )

            # GET plex/sessions → /status/sessions
            # Injects _thumbUrl (full URL with token) into each session so the card
            # can use artwork directly without an HA-authenticated image proxy.
            if path == "sessions" and method == "GET":
                async with http.get(
                    f"{base}/status/sessions",
                    headers=plex_hdrs,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    data = await r.json()
                    for item in data.get("MediaContainer", {}).get("Metadata", []):
                        thumb = item.get("thumb") or item.get("parentThumb") or item.get("grandparentThumb") or ""
                        item["_thumbUrl"] = f"{base}{thumb}?X-Plex-Token={token}" if thumb else ""
                    return web.json_response(data, status=r.status)

            # POST plex/player → player control (play/pause/seek/stop)
            # Body: { action, machineIdentifier, offset? (ms), playerUrl? }
            if path == "player" and method == "POST":
                body       = await request.json()
                action     = body.get("action", "")   # play | pause | stop | seekTo
                machine_id = body.get("machineIdentifier", "")
                offset     = body.get("offset")        # ms, only for seekTo
                player_url = (body.get("playerUrl") or "").rstrip("/")

                plex_actions = {"play", "pause", "stop", "seekTo", "skipPrevious", "skipNext"}
                if action not in plex_actions:
                    return web.json_response({"error": "unknown action"}, status=400)

                params: dict = {"commandID": "1"}
                if action == "seekTo" and offset is not None:
                    params["offset"] = str(int(offset))
                    params["type"]   = "video"

                if player_url:
                    # Direct Plex Companion — talk directly to client HTTP server
                    direct_hdrs = {
                        "X-Plex-Client-Identifier":        PLEX_CLIENT_ID,
                        "X-Plex-Target-Client-Identifier": machine_id,
                        "X-Plex-Product":                  "Arr Stack Card",
                        "X-Plex-Version":                  "1.0.0",
                        "X-Plex-Platform":                 "Web",
                        "X-Plex-Platform-Version":         "1.0",
                        "X-Plex-Device":                   "Home Assistant",
                        "X-Plex-Device-Name":              "Arr Stack Card",
                        "X-Plex-Provides":                 "controller",
                        "Accept":                          "application/json",
                    }
                    # Subscribe first — required before player accepts commands
                    try:
                        async with http.get(
                            f"{player_url}/player/timeline/subscribe",
                            headers=direct_hdrs,
                            params={"protocol": "http", "port": "32400", "commandID": "0"},
                            timeout=aiohttp.ClientTimeout(total=5),
                            ssl=ssl,
                        ) as sub_r:
                            await sub_r.read()
                    except Exception:
                        pass
                    async with http.get(
                        f"{player_url}/player/playback/{action}",
                        headers=direct_hdrs,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=ssl,
                    ) as r:
                        await r.read()
                        return web.json_response({"ok": r.status < 400, "status": r.status}, status=200)
                else:
                    # Server-relayed via Plex Companion proxy
                    params["X-Plex-Token"] = token
                    target_hdrs = {
                        **plex_hdrs,
                        "X-Plex-Target-Client-Identifier": machine_id,
                    }
                    async with http.get(
                        f"{base}/player/proxy/playback/{action}",
                        headers=target_hdrs,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=ssl,
                    ) as r:
                        await r.read()
                        return web.json_response({"ok": r.status < 400, "status": r.status}, status=200)

            # DELETE plex/session/terminate → terminate session with reason message
            # Body: { sessionId, reason }
            if path == "session/terminate" and method == "DELETE":
                body       = await request.json()
                session_id = body.get("sessionId", "")
                reason     = body.get("reason", "Your session has been terminated by an administrator.")
                if not session_id:
                    return web.json_response({"error": "sessionId required"}, status=400)
                async with http.delete(
                    f"{base}/status/sessions/terminate",
                    headers=plex_hdrs,
                    params={"sessionId": session_id, "reason": reason},
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    await r.read()
                    return web.json_response({"ok": r.status < 400, "status": r.status}, status=200)

            # GET plex/lookup?tmdbId=X or ?tvdbId=X → find Plex item by external ID
            # Tries multiple GUID formats (new agent, old agent) then per-section fallback.
            if path == "lookup" and method == "GET":
                tmdb_id = request.rel_url.query.get("tmdbId")
                tvdb_id = request.rel_url.query.get("tvdbId")
                if not tmdb_id and not tvdb_id:
                    return web.json_response({"error": "tmdbId or tvdbId required"}, status=400)

                async def _plex_search_guid(guid_str):
                    async with http.get(
                        f"{base}/library/all",
                        headers=plex_hdrs,
                        params={"guid": guid_str},
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=ssl,
                    ) as r:
                        d = await r.json(content_type=None)
                        items = d.get("MediaContainer", {}).get("Metadata", [])
                        _LOGGER.debug("arr_stack plex/lookup _search_guid(%s) → %d results", guid_str, len(items))
                        return items

                async def _plex_sections():
                    try:
                        async with http.get(
                            f"{base}/library/sections",
                            headers=plex_hdrs,
                            timeout=aiohttp.ClientTimeout(total=5),
                            ssl=ssl,
                        ) as r:
                            sd = await r.json(content_type=None)
                            return sd.get("MediaContainer", {}).get("Directory", [])
                    except Exception:
                        return []

                async def _plex_search_sections(guids_to_try, section_type=None):
                    """Filter-based search per section (works if Plex supports guid= filter)."""
                    sections = await _plex_sections()
                    for section in sections:
                        if section_type and section.get("type") != section_type:
                            continue
                        key = section.get("key")
                        if not key:
                            continue
                        for g in guids_to_try:
                            try:
                                async with http.get(
                                    f"{base}/library/sections/{key}/all",
                                    headers=plex_hdrs,
                                    params={"guid": g},
                                    timeout=aiohttp.ClientTimeout(total=10),
                                    ssl=ssl,
                                ) as r:
                                    d = await r.json(content_type=None)
                                    items = d.get("MediaContainer", {}).get("Metadata", [])
                                    if items:
                                        sec_title = section.get("title", "")
                                        for it in items:
                                            if not it.get("librarySectionTitle"):
                                                it["librarySectionTitle"] = sec_title
                                        return items
                            except Exception:
                                continue
                    return []

                async def _plex_scan_sections(match_guids, section_type=None):
                    """Brute-force: fetch all items per section, match Guid[] locally."""
                    sections = await _plex_sections()
                    match_set = set(match_guids)
                    for section in sections:
                        if section_type and section.get("type") != section_type:
                            continue
                        key = section.get("key")
                        if not key:
                            continue
                        try:
                            async with http.get(
                                f"{base}/library/sections/{key}/all",
                                headers=plex_hdrs,
                                params={"includeGuids": "1"},
                                timeout=aiohttp.ClientTimeout(total=30),
                                ssl=ssl,
                            ) as r:
                                d = await r.json(content_type=None)
                                sec_title = section.get("title", "")
                                for item in d.get("MediaContainer", {}).get("Metadata", []):
                                    if not item.get("librarySectionTitle"):
                                        item["librarySectionTitle"] = sec_title
                                    # Check primary guid
                                    if item.get("guid", "") in match_set:
                                        return [item]
                                    # Check Guid[] array (new Plex agent)
                                    for g in item.get("Guid", []):
                                        if g.get("id", "") in match_set:
                                            return [item]
                        except Exception:
                            continue
                    return []

                items = []
                if tmdb_id:
                    new_guid  = f"tmdb://{tmdb_id}"
                    old_guid  = f"com.plexapp.agents.themoviedb://{tmdb_id}"
                    old_guid2 = f"com.plexapp.agents.themoviedb://{tmdb_id}?lang=en"
                    all_guids = [new_guid, old_guid, old_guid2]
                    items = await _plex_search_guid(new_guid)
                    if not items:
                        items = await _plex_search_guid(old_guid)
                    if not items:
                        items = await _plex_search_sections(all_guids, section_type="movie")
                    if not items:
                        items = await _plex_scan_sections(all_guids, section_type="movie")
                elif tvdb_id:
                    new_guid  = f"tvdb://{tvdb_id}"
                    old_guid  = f"com.plexapp.agents.thetvdb://{tvdb_id}"
                    old_guid2 = f"com.plexapp.agents.thetvdb://{tvdb_id}?lang=en"
                    all_guids = [new_guid, old_guid, old_guid2]
                    items = await _plex_search_guid(new_guid)
                    if not items:
                        items = await _plex_search_guid(old_guid)
                    if not items:
                        items = await _plex_search_sections(all_guids, section_type="show")
                    if not items:
                        items = await _plex_scan_sections(all_guids, section_type="show")

                if not items:
                    return web.json_response({"error": "not_found"}, status=404)
                item = items[0]
                return web.json_response({
                    "plex_key": f"/library/metadata/{item.get('ratingKey')}",
                    "title": item.get("title"),
                    "library": item.get("librarySectionTitle"),
                    "type": item.get("type"),
                })

            # GET plex/libraries → /library/sections (library names + types)
            if path == "libraries" and method == "GET":
                async with http.get(
                    f"{base}/library/sections",
                    headers=plex_hdrs,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=ssl,
                ) as r:
                    data = await r.json(content_type=None)
                    sections = data.get("MediaContainer", {}).get("Directory", [])
                    return web.json_response([
                        {"key": s.get("key"), "title": s.get("title"), "type": s.get("type")}
                        for s in sections
                    ])

        # ════════════════════════════════════════════
        # TMDB — discover proxy (fallback when Overseerr not configured)
        # ════════════════════════════════════════════
        elif service == "tmdb":
            from .const import TMDB_API_KEY, TMDB_BASE as _TMDB_BASE

            def _tmdb_item(item, force_type=None):
                mt = force_type or item.get("media_type", "movie")
                return {
                    "id":          item.get("id"),
                    "title":       item.get("title") or item.get("name", ""),
                    "name":        item.get("name") or item.get("title", ""),
                    "mediaType":   mt,
                    "posterPath":  item.get("poster_path"),
                    "backdropPath": item.get("backdrop_path"),
                    "releaseDate": item.get("release_date") or item.get("first_air_date", ""),
                    "firstAirDate": item.get("first_air_date", ""),
                    "overview":    item.get("overview", ""),
                    "voteAverage": item.get("vote_average", 0),
                    "voteCount":   item.get("vote_count", 0),
                    "genreIds":    item.get("genre_ids", []),
                }

            def _tmdb_page(data, force_type=None):
                items = [
                    _tmdb_item(r, force_type)
                    for r in data.get("results", [])
                    if (force_type or r.get("media_type", "movie")) in ("movie", "tv")
                ]
                return {
                    "results":      items,
                    "totalPages":   data.get("total_pages", 1),
                    "totalResults": data.get("total_results", 0),
                    "page":         data.get("page", 1),
                }

            base_params = {"api_key": TMDB_API_KEY, "language": "en-US"}
            page = request.rel_url.query.get("page", "1")
            timeout = aiohttp.ClientTimeout(total=10)

            if path == "upcoming" and method == "GET":
                async with http.get(f"{_TMDB_BASE}/movie/upcoming", params={**base_params, "page": page}, timeout=timeout) as r:
                    return web.json_response(_tmdb_page(await r.json(), "movie"))

            if path == "popular" and method == "GET":
                async with http.get(f"{_TMDB_BASE}/movie/popular", params={**base_params, "page": page}, timeout=timeout) as r:
                    return web.json_response(_tmdb_page(await r.json(), "movie"))

            if path == "trending" and method == "GET":
                async with http.get(f"{_TMDB_BASE}/trending/all/week", params={**base_params, "page": page}, timeout=timeout) as r:
                    return web.json_response(_tmdb_page(await r.json()))

            if path == "tv_upcoming" and method == "GET":
                async with http.get(f"{_TMDB_BASE}/tv/on_the_air", params={**base_params, "page": page}, timeout=timeout) as r:
                    return web.json_response(_tmdb_page(await r.json(), "tv"))

            if path == "search" and method == "POST":
                body = await request.json()
                query = body.get("query", "")
                async with http.get(
                    f"{_TMDB_BASE}/search/multi",
                    params={**base_params, "query": query, "include_adult": "false"},
                    timeout=timeout,
                ) as r:
                    return web.json_response(_tmdb_page(await r.json()))

            def _tmdb_cast(d):
                cast = (d.get("credits") or {}).get("cast") or []
                return {"cast": [{
                    "name":        c.get("name", ""),
                    "character":   c.get("character", ""),
                    "profilePath": c.get("profile_path"),
                } for c in cast[:24]]}

            if path.startswith("movie/") and method == "GET":
                movie_id = path[6:]
                async with http.get(f"{_TMDB_BASE}/movie/{movie_id}", params={**base_params, "append_to_response": "credits"}, timeout=timeout) as r:
                    d = await r.json()
                async with http.get(f"{_TMDB_BASE}/movie/{movie_id}/videos", params=base_params, timeout=timeout) as r:
                    v = await r.json()
                trailer = next((x for x in v.get("results", []) if x.get("site") == "YouTube" and x.get("type") == "Trailer"), None) \
                       or next((x for x in v.get("results", []) if x.get("site") == "YouTube"), None)
                return web.json_response({
                    "id":              d.get("id"),
                    "title":           d.get("title", ""),
                    "overview":        d.get("overview", ""),
                    "posterPath":      d.get("poster_path"),
                    "backdropPath":    d.get("backdrop_path"),
                    "releaseDate":     d.get("release_date", ""),
                    "voteAverage":     d.get("vote_average", 0),
                    "genres":          [{"name": g["name"]} for g in d.get("genres", [])],
                    "credits":         _tmdb_cast(d),
                    "youTubeTrailerId": trailer["key"] if trailer else None,
                })

            if path.startswith("tv/") and method == "GET":
                tv_id = path[3:]
                async with http.get(f"{_TMDB_BASE}/tv/{tv_id}", params={**base_params, "append_to_response": "credits"}, timeout=timeout) as r:
                    d = await r.json()
                async with http.get(f"{_TMDB_BASE}/tv/{tv_id}/videos", params=base_params, timeout=timeout) as r:
                    v = await r.json()
                trailer = next((x for x in v.get("results", []) if x.get("site") == "YouTube" and x.get("type") == "Trailer"), None) \
                       or next((x for x in v.get("results", []) if x.get("site") == "YouTube"), None)
                return web.json_response({
                    "id":              d.get("id"),
                    "name":            d.get("name", ""),
                    "overview":        d.get("overview", ""),
                    "posterPath":      d.get("poster_path"),
                    "backdropPath":    d.get("backdrop_path"),
                    "firstAirDate":    d.get("first_air_date", ""),
                    "voteAverage":     d.get("vote_average", 0),
                    "genres":          [{"name": g["name"]} for g in d.get("genres", [])],
                    "numberOfSeasons": d.get("number_of_seasons", 0),
                    "credits":         _tmdb_cast(d),
                    "youTubeTrailerId": trailer["key"] if trailer else None,
                })

        # ════════════════════════════════════════════
        # Tautulli
        # ════════════════════════════════════════════
        elif service == "tautulli":
            tautulli_url = cfg.get(CONF_TAUTULLI_URL, "").rstrip("/")
            for _sfx in ("/api/v2", "/home", "/settings", "/history", "/recently_added"):
                if tautulli_url.endswith(_sfx):
                    tautulli_url = tautulli_url[: -len(_sfx)].rstrip("/")
            tautulli_key = cfg.get(CONF_TAUTULLI_KEY, "")
            if not tautulli_url or not tautulli_key:
                return web.json_response({"error": "Tautulli not configured"}, status=503)

            # ── sharing_ack — persisted via HA Store (not forwarded to Tautulli)
            if path == "sharing_ack":
                from homeassistant.helpers.storage import Store  # noqa: PLC0415
                store = Store(self._hass, 1, "arr_stack.sharing_ack")
                if method == "GET":
                    data = await store.async_load() or {}
                    return web.json_response(data)
                elif method == "POST":
                    body = await request.json()
                    await store.async_save(body)
                    return web.json_response({"ok": True})

            # path is the Tautulli cmd, e.g. "get_activity", "get_history"
            # query params from the card are forwarded alongside apikey + cmd
            params = dict(request.rel_url.query)
            params["apikey"] = tautulli_key
            params["cmd"]    = path

            async with http.get(
                f"{tautulli_url}/api/v2",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=ssl,
            ) as r:
                raw = await r.read()
                ct  = r.headers.get("Content-Type", "application/json").split(";")[0].strip()
                return web.Response(body=raw, content_type=ct, status=r.status)

        # ════════════════════════════════════════════
        # Jellystat
        # ════════════════════════════════════════════
        elif service == "jellystat":
            jellystat_url = cfg.get(CONF_JELLYSTAT_URL, "").rstrip("/")
            jellystat_key = cfg.get(CONF_JELLYSTAT_KEY, "")
            if not jellystat_url or not jellystat_key:
                return web.json_response({"error": "Jellystat not configured"}, status=503)

            params = dict(request.rel_url.query)
            headers = {
                "x-api-token": jellystat_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # stats/ routes live at /stats/... not /api/stats/...
            if path.startswith("stats/"):
                target_url = f"{jellystat_url}/{path}"
            else:
                target_url = f"{jellystat_url}/api/{path}"
            if method == "GET":
                async with http.get(
                    target_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)
            elif method == "POST":
                body = await request.read()
                async with http.post(
                    target_url,
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

        # ════════════════════════════════════════════
        # Tracearr
        # ════════════════════════════════════════════
        elif service == "tracearr":
            tracearr_url = cfg.get(CONF_TRACEARR_URL, "").rstrip("/")
            tracearr_key = cfg.get(CONF_TRACEARR_KEY, "")
            if not tracearr_url or not tracearr_key:
                return web.json_response({"error": "Tracearr not configured"}, status=503)

            # Library, stats and rules endpoints require admin JWT; public endpoints use the public key
            is_library = path.startswith("v1/library") or path.startswith("v1/stats") or path.startswith("v1/rules")
            if is_library:
                refresh_token = cfg.get(CONF_TRACEARR_REFRESH_TOKEN, "")
                entry_id = next(iter(self._hass.config_entries.async_entries("arr_stack")), None)
                entry_id_str = entry_id.entry_id if entry_id else "default"
                plex_token = cfg.get(CONF_PLEX_TOKEN, "")
                admin_token = await _tracearr_get_access_token(http, tracearr_url, entry_id_str, refresh_token, ssl=ssl, hass=self._hass, plex_token=plex_token)
                if not admin_token:
                    return web.json_response({"error": "Tracearr admin token unavailable — set tracearr_refresh_token in config"}, status=503)
                auth_header = f"Bearer {admin_token}"
            else:
                auth_header = f"Bearer {tracearr_key}"

            params = dict(request.rel_url.query)
            headers = {
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            target_url = f"{tracearr_url}/api/{path}"
            if method == "GET":
                async with http.get(
                    target_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    raw = await r.read()
                    ct = r.headers.get("Content-Type", "application/json").split(";")[0].strip()
                    return web.Response(body=raw, content_type=ct, status=r.status)
            elif method == "POST":
                body = await request.read()
                async with http.post(
                    target_url,
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    raw = await r.read()
                    ct = r.headers.get("Content-Type", "application/json").split(";")[0].strip()
                    return web.Response(body=raw, content_type=ct, status=r.status)
            elif method == "PATCH":
                body = await request.read()
                async with http.patch(
                    target_url,
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    raw = await r.read()
                    ct = r.headers.get("Content-Type", "application/json").split(";")[0].strip()
                    return web.Response(body=raw, content_type=ct, status=r.status)
            elif method == "DELETE":
                async with http.delete(
                    target_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=ssl,
                ) as r:
                    raw = await r.read()
                    ct = r.headers.get("Content-Type", "application/json").split(";")[0].strip()
                    return web.Response(body=raw, content_type=ct, status=r.status)

        # ════════════════════════════════════════════
        # System
        # ════════════════════════════════════════════
        elif service == "system":
            if path == "publicip":
                for url in ["https://api.ipify.org", "https://checkip.amazonaws.com"]:
                    try:
                        async with http.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                            ip = (await r.text()).strip()
                            if ip:
                                return web.json_response({"ip": ip})
                    except Exception:
                        continue
                return web.json_response({"ip": None})

        elif service == "trakt":
            return await self._handle_trakt(request, path, method, cfg, http, ssl)

        # ════════════════════════════════════════════
        # Prowlarr
        # ════════════════════════════════════════════
        elif service == "prowlarr":
            if not cfg.get(CONF_PROWLARR_URL):
                return web.json_response({"_notConfigured": True})
            base = cfg.get(CONF_PROWLARR_URL, "").rstrip("/")
            hdrs = {"X-Api-Key": cfg.get(CONF_PROWLARR_KEY, "")}

            # Indexer list (includes embedded status)
            if path == "indexers" and method == "GET":
                async with http.get(f"{base}/api/v1/indexer", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # App profiles
            if path == "appprofiles" and method == "GET":
                async with http.get(f"{base}/api/v1/appprofile", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Indexer status (errors)
            if path == "indexerstatus" and method == "GET":
                async with http.get(f"{base}/api/v1/indexerstatus", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Indexer stats (for charts)
            if path == "indexerstats" and method == "GET":
                params = {}
                if request.query.get("startDate"): params["startDate"] = request.query["startDate"]
                if request.query.get("endDate"):   params["endDate"]   = request.query["endDate"]
                async with http.get(f"{base}/api/v1/indexerstats", headers=hdrs, params=params, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # History
            if path == "history" and method == "GET":
                page      = request.query.get("page", "1")
                page_size = request.query.get("pageSize", "100")
                params = {"page": page, "pageSize": page_size, "sortKey": "date", "sortDirection": "descending"}
                if request.query.get("indexerId"): params["indexerId"] = request.query["indexerId"]
                if request.query.get("eventType"): params["eventType"] = request.query["eventType"]
                try:
                    async with http.get(f"{base}/api/v1/history", headers=hdrs, params=params, ssl=ssl) as r:
                        if r.status != 200:
                            return web.json_response({"records": [], "totalRecords": 0})
                        return web.Response(body=await r.read(), content_type="application/json", status=200)
                except Exception:
                    return web.json_response({"records": [], "totalRecords": 0})

            # History delete
            if path.startswith("history/") and method == "DELETE":
                h_id = path.split("/", 1)[1]
                async with http.delete(f"{base}/api/v1/history/{h_id}", headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            # Indexer schema (all available indexer definitions for Add)
            if path == "indexer/schema" and method == "GET":
                async with http.get(f"{base}/api/v1/indexer/schema", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Single indexer (for Edit — returns config + field values)
            if path.startswith("indexer/") and not path.startswith("indexer/schema") and method == "GET":
                idx_id = path.split("/", 1)[1]
                async with http.get(f"{base}/api/v1/indexer/{idx_id}", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Create indexer
            if path == "indexer" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v1/indexer", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Update indexer
            if path.startswith("indexer/") and method == "PUT":
                idx_id = path.split("/", 1)[1]
                body = await request.json()
                body.pop("_status", None)  # strip client-side field
                async with http.put(f"{base}/api/v1/indexer/{idx_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Delete indexer
            if path.startswith("indexer/") and method == "DELETE":
                idx_id = path.split("/", 1)[1]
                async with http.delete(f"{base}/api/v1/indexer/{idx_id}", headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            # Test indexer — id=0 or absent → new config test; id>0 → test existing by ID
            # Note: Prowlarr has no POST /api/v1/indexer/{id}/test → fetch config first, then test
            # Always returns 200 so JS can read error messages (HA callApi drops body on non-200)
            if path == "idxtest" and method == "POST":
                import json as _json
                idx_id = request.query.get("id", "0")
                if idx_id and idx_id != "0":
                    async with http.get(f"{base}/api/v1/indexer/{idx_id}", headers=hdrs, ssl=ssl) as r_get:
                        idx_config = await r_get.json()
                    idx_config.pop("_status", None)
                    async with http.post(f"{base}/api/v1/indexer/test", headers={**hdrs, "Content-Type": "application/json"}, json=idx_config, ssl=ssl) as r:
                        resp_body = await r.read()
                else:
                    body = await request.json()
                    body.pop("_status", None)
                    body["id"] = 0
                    async with http.post(f"{base}/api/v1/indexer/test", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                        resp_body = await r.read()
                # Always 200 — include ok flag + errors for JS to display
                if r.status in (200, 204) and not resp_body.strip():
                    return web.json_response({"ok": True})
                try:
                    errs = _json.loads(resp_body)
                    if isinstance(errs, list):
                        return web.json_response({"ok": False, "errors": errs})
                    return web.json_response({"ok": True})
                except Exception:
                    return web.json_response({"ok": False, "errors": [{"errorMessage": resp_body.decode(errors="replace")}]})

            # Test all indexers
            if path == "idxtestall" and method == "POST":
                json_hdrs = {**hdrs, "Content-Type": "application/json"}
                async with http.post(f"{base}/api/v1/indexer/testall", headers=json_hdrs, data=b"{}", ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Applications list
            if path == "applications" and method == "GET":
                async with http.get(f"{base}/api/v1/applications", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Applications schema (all implementation types)
            if path == "applications/schema" and method == "GET":
                async with http.get(f"{base}/api/v1/applications/schema", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Create application
            if path == "applications" and method == "POST":
                body = await request.json()
                async with http.post(f"{base}/api/v1/applications", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Update application
            if path.startswith("applications/") and method == "PUT":
                app_id = path.split("/", 1)[1]
                body = await request.json()
                async with http.put(f"{base}/api/v1/applications/{app_id}", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Delete application
            if path.startswith("applications/") and method == "DELETE":
                app_id = path.split("/", 1)[1]
                async with http.delete(f"{base}/api/v1/applications/{app_id}", headers=hdrs, ssl=ssl) as r:
                    body = await r.read()
                    return web.json_response({}, status=r.status) if not body.strip() else web.Response(body=body, content_type="application/json", status=r.status)

            # Test application — always returns 200 + {ok, errors}
            if path == "apptest" and method == "POST":
                import json as _json2
                body = await request.json()
                async with http.post(f"{base}/api/v1/applications/test", headers={**hdrs, "Content-Type": "application/json"}, json=body, ssl=ssl) as r:
                    resp_body = await r.read()
                if r.status in (200, 204) and not resp_body.strip():
                    return web.json_response({"ok": True})
                try:
                    errs = _json2.loads(resp_body)
                    if isinstance(errs, list):
                        return web.json_response({"ok": False, "errors": errs})
                    return web.json_response({"ok": True})
                except Exception:
                    return web.json_response({"ok": False, "errors": [{"errorMessage": resp_body.decode(errors="replace")}]})

            # Sync application — force push indexers to specific app
            if path.startswith("appsync/") and method == "POST":
                app_id = int(path.split("/", 1)[1])
                async with http.post(f"{base}/api/v1/command", headers={**hdrs, "Content-Type": "application/json"}, json={"name": "ApplicationIndexerSync", "applicationIds": [app_id]}, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

            # Indexer categories (for syncCategories tree in app form)
            if path == "categories" and method == "GET":
                async with http.get(f"{base}/api/v1/indexer/categories", headers=hdrs, ssl=ssl) as r:
                    return web.Response(body=await r.read(), content_type="application/json", status=r.status)

        elif service == "jellyfin":
            try:
                jf_entries = self._hass.config_entries.async_entries("jellyfin")
                if not jf_entries:
                    return web.json_response({"_notConfigured": True})
                entry = jf_entries[0]
                server_url = (entry.data.get("url") or "").rstrip("/")
                # Token not in entry.data — extract from api_client (JellyfinClient)
                api_token = ""
                runtime = getattr(entry, "runtime_data", None)
                if runtime is not None:
                    client = getattr(runtime, "api_client", None)
                    if client is not None:
                        try:
                            cfg = getattr(client, "config", None)
                            if cfg:
                                d = getattr(cfg, "data", {})
                                api_token = d.get("auth.token") or d.get("auth-token") or ""
                            if not api_token:
                                creds = getattr(getattr(client, "auth", None), "credentials", None)
                                if creds:
                                    servers = creds.get_credentials().get("Servers", [])
                                    if servers:
                                        api_token = servers[0].get("AccessToken", "")
                        except Exception:
                            pass
                # coordinator stored in entry.runtime_data (HA 2024+ pattern)
                sessions = []
                if runtime is not None:
                    raw = getattr(runtime, "data", None)
                    if raw is not None:
                        if hasattr(raw, "sessions"):
                            s = raw.sessions
                            sessions = list(s.values()) if isinstance(s, dict) else list(s or [])
                        elif isinstance(raw, dict):
                            if "sessions" in raw:
                                sessions = raw["sessions"]
                            else:
                                vals = list(raw.values())
                                if vals and isinstance(vals[0], dict):
                                    sessions = vals

                if path == "sessions":
                    active = [s for s in sessions if s.get("NowPlayingItem")]
                    return web.json_response({"sessions": active, "server_url": server_url, "api_token": api_token})
                if path == "stop":
                    body = {}
                    try:
                        body = await request.json()
                    except Exception:
                        pass
                    session_id = body.get("session_id", "")
                    message    = (body.get("message") or "").strip()
                    if not session_id:
                        return web.json_response({"error": "missing session_id"}, status=400)
                    async with aiohttp.ClientSession() as session_http:
                        headers = {"X-Emby-Token": api_token, "Content-Type": "application/json"} if api_token else {"Content-Type": "application/json"}
                        import json as _json
                        if message:
                            msg_url = f"{server_url}/Sessions/{session_id}/Message"
                            msg_body = _json.dumps({"Header": "Upozornění", "Text": message, "TimeoutMs": 5000})
                            async with session_http.post(msg_url, headers=headers, data=msg_body, timeout=aiohttp.ClientTimeout(total=5)):
                                pass
                        stop_url = f"{server_url}/Sessions/{session_id}/Playing/Stop"
                        async with session_http.post(stop_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            return web.json_response({"ok": resp.status < 300}, status=200)
            except Exception as exc:
                _LOGGER.warning("arr_stack jellyfin sessions error: %s", exc)
                return web.json_response({"error": str(exc)}, status=502)

        elif service == "kodi":
            kodi_entries = self._hass.config_entries.async_entries("kodi")
            kodi_entry   = kodi_entries[0] if kodi_entries else None
            kodi_host    = (kodi_entry.data.get("host") or "") if kodi_entry else ""
            kodi_port    = kodi_entry.data.get("http_port") or kodi_entry.data.get("port") or 8080 if kodi_entry else 8080
            kodi_user    = (kodi_entry.data.get("username") or "") if kodi_entry else ""
            kodi_pass    = (kodi_entry.data.get("password") or "") if kodi_entry else ""
            kodi_url     = f"http://{kodi_host}:{kodi_port}/jsonrpc" if kodi_host else ""

            if path == "sessions":
                try:
                    from homeassistant.helpers import entity_registry as er
                    ent_reg = er.async_get(self._hass)
                    kodi_ids = [
                        e.entity_id for e in ent_reg.entities.values()
                        if e.platform == "kodi" and e.domain == "media_player" and not e.disabled_by
                    ]
                    sessions = []
                    for eid in kodi_ids:
                        state = self._hass.states.get(eid)
                        if state and state.state in ("playing", "paused"):
                            attrs = {}
                            for k, v in state.attributes.items():
                                attrs[k] = str(v) if hasattr(v, 'isoformat') else v
                            sessions.append({
                                "entity_id": eid,
                                "state": state.state,
                                "attributes": attrs,
                            })
                    return web.json_response({"sessions": sessions, "known_ids": kodi_ids})
                except Exception as exc:
                    _LOGGER.warning("arr_stack kodi sessions error: %s", exc)
                    return web.json_response({"sessions": []})

            if path == "stop":
                body = {}
                try:
                    body = await request.json()
                except Exception:
                    pass
                entity_id = body.get("entity_id", "")
                message   = (body.get("message") or "").strip()
                try:
                    import json as _json
                    auth = aiohttp.BasicAuth(kodi_user, kodi_pass) if kodi_user else None
                    headers = {"Content-Type": "application/json"}
                    async with aiohttp.ClientSession() as session_http:
                        if message and kodi_url:
                            notify_body = _json.dumps({
                                "jsonrpc": "2.0", "id": 1, "method": "GUI.ShowNotification",
                                "params": {"title": "Upozornění", "message": message, "displaytime": 5000}
                            })
                            async with session_http.post(kodi_url, data=notify_body, headers=headers, auth=auth, timeout=aiohttp.ClientTimeout(total=5)):
                                pass
                    # Stop via HA service
                    if entity_id:
                        await self._hass.services.async_call(
                            "media_player", "media_stop", {"entity_id": entity_id}, blocking=False
                        )
                    return web.json_response({"ok": True})
                except Exception as exc:
                    _LOGGER.warning("arr_stack kodi stop error: %s", exc)
                    return web.json_response({"ok": False, "error": str(exc)})

        elif service == "emby":
            try:
                emby_url = (cfg.get(CONF_EMBY_URL) or "").rstrip("/")
                emby_key = cfg.get(CONF_EMBY_KEY) or ""
                if not emby_url or not emby_key:
                    return web.json_response({"_notConfigured": True})
                import json as _json
                if path == "sessions":
                    async with aiohttp.ClientSession() as session_http:
                        async with session_http.get(
                            f"{emby_url}/Sessions?api_key={emby_key}",
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            data = await resp.json()
                            active = [s for s in data if s.get("NowPlayingItem")]
                            return web.json_response({"sessions": active, "server_url": emby_url, "api_token": emby_key})
                if path == "stop":
                    body = {}
                    try:
                        body = await request.json()
                    except Exception:
                        pass
                    session_id = body.get("session_id", "")
                    message    = (body.get("message") or "").strip()
                    if not session_id:
                        return web.json_response({"error": "missing session_id"}, status=400)
                    async with aiohttp.ClientSession() as session_http:
                        headers = {"Content-Type": "application/json"}
                        if message:
                            msg_url  = f"{emby_url}/Sessions/{session_id}/Message?api_key={emby_key}"
                            msg_body = _json.dumps({"Header": "Upozornění", "Text": message, "TimeoutMs": 5000})
                            async with session_http.post(msg_url, headers=headers, data=msg_body, timeout=aiohttp.ClientTimeout(total=5)):
                                pass
                        stop_url = f"{emby_url}/Sessions/{session_id}/Playing/Stop?api_key={emby_key}"
                        async with session_http.post(stop_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            return web.json_response({"ok": resp.status < 300}, status=200)
            except Exception as exc:
                _LOGGER.warning("arr_stack emby error: %s", exc)
                return web.json_response({"error": str(exc)}, status=502)

        return web.json_response({"error": "unknown service or path"}, status=404)

    # ── Trakt proxy ───────────────────────────────────────────────────────────

    async def _trakt_access_token(self, cfg: dict, session: aiohttp.ClientSession) -> str | None:
        """Return a valid Trakt access token, refreshing if needed. Persists updated tokens to config entry."""
        import time
        access_token  = cfg.get(CONF_TRAKT_ACCESS_TOKEN, "")
        refresh_token = cfg.get(CONF_TRAKT_REFRESH_TOKEN, "")
        client_id     = cfg.get(CONF_TRAKT_CLIENT_ID, "")
        client_secret = cfg.get(CONF_TRAKT_CLIENT_SECRET, "")
        expires_at    = cfg.get(CONF_TRAKT_EXPIRES_AT, 0)

        if not access_token or not client_id:
            return None

        # Refresh if expiring within 1 day
        if time.time() < expires_at - 86400:
            return access_token

        if not refresh_token or not client_secret:
            return access_token  # can't refresh, use as-is and hope for the best

        try:
            async with session.post(
                f"{TRAKT_API_BASE}/oauth/token",
                json={
                    "refresh_token": refresh_token,
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "redirect_uri":  "urn:ietf:wg:oauth:2.0:oob",
                    "grant_type":    "refresh_token",
                },
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    tok = await resp.json()
                    new_access  = tok["access_token"]
                    new_refresh = tok["refresh_token"]
                    new_expires = int(time.time()) + tok.get("expires_in", 604800)
                    # Persist to config entry
                    for entry in self._hass.config_entries.async_entries(DOMAIN):
                        new_data = dict(entry.data)
                        new_data[CONF_TRAKT_ACCESS_TOKEN]  = new_access
                        new_data[CONF_TRAKT_REFRESH_TOKEN] = new_refresh
                        new_data[CONF_TRAKT_EXPIRES_AT]    = new_expires
                        self._hass.config_entries.async_update_entry(entry, data=new_data)
                        cfg.update({
                            CONF_TRAKT_ACCESS_TOKEN:  new_access,
                            CONF_TRAKT_REFRESH_TOKEN: new_refresh,
                            CONF_TRAKT_EXPIRES_AT:    new_expires,
                        })
                        break
                    return new_access
        except Exception as e:
            _LOGGER.warning("arr_stack Trakt token refresh failed: %s", e)
        return access_token

    async def _handle_trakt(self, request, path: str, method: str, cfg: dict, session: aiohttp.ClientSession, ssl) -> web.Response:
        token = await self._trakt_access_token(cfg, session)
        if not token:
            return web.json_response({"error": "Trakt not configured"}, status=503)

        client_id = cfg.get(CONF_TRAKT_CLIENT_ID, "")
        headers = {
            "Content-Type":      "application/json",
            "Authorization":     f"Bearer {token}",
            "trakt-api-version": TRAKT_API_VER,
            "trakt-api-key":     client_id,
        }

        # GET /trakt/recommendations  →  mixed movies + shows
        if path == "recommendations" and method == "GET":
            import time as _time
            _TRAKT_CACHE_TTL = 1800  # 30 minut
            if self._trakt_cache is not None and (_time.monotonic() - self._trakt_cache_ts) < _TRAKT_CACHE_TTL:
                return web.json_response(self._trakt_cache)
            limit = int(request.query.get("limit", 40))
            try:
                movie_url = f"{TRAKT_API_BASE}/recommendations/movies?limit={limit}&extended=full"
                show_url  = f"{TRAKT_API_BASE}/recommendations/shows?limit={limit}&extended=full"
                async with session.get(movie_url, headers=headers, ssl=ssl, timeout=aiohttp.ClientTimeout(total=15)) as rm, \
                           session.get(show_url,  headers=headers, ssl=ssl, timeout=aiohttp.ClientTimeout(total=15)) as rs:
                    movies = await rm.json() if rm.status == 200 else []
                    shows  = await rs.json() if rs.status == 200 else []
                # Normalise to unified format
                movie_items = []
                for m in (movies if isinstance(movies, list) else []):
                    movie = m.get("movie", m)
                    ids   = movie.get("ids", {})
                    movie_items.append({
                        "mediaType":  "movie",
                        "id":         ids.get("tmdb"),
                        "title":      movie.get("title", ""),
                        "releaseDate": str(movie.get("year", "")),
                        "voteAverage": movie.get("rating"),
                        "posterPath":  None,
                        "overview":    movie.get("overview", ""),
                        "_traktSlug":  ids.get("slug"),
                    })
                show_items = []
                for s in (shows if isinstance(shows, list) else []):
                    show = s.get("show", s)
                    ids  = show.get("ids", {})
                    show_items.append({
                        "mediaType":  "tv",
                        "id":         ids.get("tmdb"),
                        "tvdbId":     ids.get("tvdb"),
                        "title":      show.get("title", ""),
                        "releaseDate": str(show.get("year", "")),
                        "voteAverage": show.get("rating"),
                        "posterPath":  None,
                        "overview":    show.get("overview", ""),
                        "_traktSlug":  ids.get("slug"),
                    })
                # Interleave movies and shows so they alternate in the result
                result = []
                for pair in itertools.zip_longest(movie_items, show_items):
                    result.extend(x for x in pair if x is not None)
                # Filter items without tmdb id
                result = [r for r in result if r.get("id")]
                # Enrich with TMDB poster paths
                result = await self._enrich_trakt_posters(result, session, ssl)
                self._trakt_cache = result
                self._trakt_cache_ts = _time.monotonic()
                return web.json_response(result)
            except Exception as e:
                _LOGGER.error("arr_stack Trakt recommendations error: %s", e)
                return web.json_response({"error": str(e)}, status=502)

        # DELETE /trakt/recommendations/{movies|shows}/{id}  →  hide from recommendations
        if path.startswith("recommendations/") and method == "DELETE":
            try:
                rest = path[len("recommendations/"):]  # e.g. "movies/the-dark-knight-2008"
                self._trakt_cache = None
                async with session.delete(
                    f"{TRAKT_API_BASE}/recommendations/{rest}",
                    headers=headers,
                    ssl=ssl,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status in (200, 201, 204):
                        return web.json_response({"ok": True})
                    return web.json_response({"error": await r.text()}, status=r.status)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=502)

        # POST /trakt/history  →  mark movie or show as watched
        if path == "history" and method == "POST":
            try:
                body      = await request.json()
                media_type = body.get("mediaType", "movie")
                slug      = body.get("slug")
                tmdb_id   = body.get("tmdbId")
                ids_obj   = {}
                if slug:    ids_obj["slug"] = slug
                if tmdb_id: ids_obj["tmdb"] = tmdb_id
                if media_type == "tv":
                    payload = {"shows": [{"ids": ids_obj}]}
                else:
                    payload = {"movies": [{"ids": ids_obj}]}
                async with session.post(
                    f"{TRAKT_API_BASE}/sync/history",
                    headers=headers,
                    json=payload,
                    ssl=ssl,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    # Clear recommendations cache so this item won't reappear
                    self._trakt_cache = None
                    if r.status in (200, 201):
                        return web.json_response({"ok": True})
                    return web.json_response({"error": await r.text()}, status=r.status)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=502)

        # POST /trakt/rate  →  rate movie or show (rating 1-10)
        if path == "rate" and method == "POST":
            try:
                body       = await request.json()
                media_type = body.get("mediaType", "movie")
                slug       = body.get("slug")
                tmdb_id    = body.get("tmdbId")
                rating     = int(body.get("rating", 8))
                ids_obj: dict = {}
                if slug:    ids_obj["slug"] = slug
                if tmdb_id: ids_obj["tmdb"] = tmdb_id
                if media_type == "tv":
                    payload = {"shows": [{"ids": ids_obj, "rating": rating}]}
                else:
                    payload = {"movies": [{"ids": ids_obj, "rating": rating}]}
                async with session.post(
                    f"{TRAKT_API_BASE}/sync/ratings",
                    headers=headers,
                    json=payload,
                    ssl=ssl,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status in (200, 201):
                        return web.json_response({"ok": True})
                    return web.json_response({"error": await r.text()}, status=r.status)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=502)

        return web.json_response({"error": "unknown trakt path"}, status=404)

    async def _enrich_trakt_posters(self, items: list, session: aiohttp.ClientSession, ssl) -> list:
        """Batch-fetch poster_path from TMDB for Trakt items."""
        from .const import TMDB_API_KEY, TMDB_BASE as _TMDB_BASE
        timeout = aiohttp.ClientTimeout(total=10)

        async def fetch_poster(item):
            tmdb_id = item.get("id")
            if not tmdb_id:
                return item
            media_type = "movie" if item.get("mediaType") == "movie" else "tv"
            url = f"{_TMDB_BASE}/{media_type}/{tmdb_id}"
            try:
                async with session.get(url, params={"api_key": TMDB_API_KEY}, ssl=ssl, timeout=timeout) as r:
                    if r.status == 200:
                        data = await r.json()
                        item = dict(item)
                        item["posterPath"] = data.get("poster_path")
                        item["voteAverage"] = item.get("voteAverage") or data.get("vote_average")
                        item["overview"] = item.get("overview") or data.get("overview", "")
            except Exception:
                pass
            return item

        import asyncio
        return list(await asyncio.gather(*[fetch_poster(i) for i in items]))


