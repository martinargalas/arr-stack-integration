# Arr Stack Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/martinargalas/arr-stack-integration?cacheSeconds=0)](https://github.com/martinargalas/arr-stack-integration/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-brightgreen.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Discord](https://img.shields.io/discord/1503764189057908798?logo=discord&label=chat&color=5865F2&logoColor=white)](https://discord.gg/WVCyejJfKd)

<a href="https://buymeacoffee.com/argii" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>

<a href="https://discord.gg/WVCyejJfKd" target="_blank"><img src="https://img.shields.io/badge/Join%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord" height="50"></a>

A Home Assistant custom integration that acts as a secure server-side proxy between the [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) and your local media services.

### Supported services

<p><img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/radarr.png" height="36" title="Radarr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/sonarr.png" height="36" title="Sonarr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/bazarr.png" height="36" title="Bazarr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/qbittorrent.png" height="36" title="qBittorrent"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/deluge.png" height="36" title="Deluge"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/rutorrent.png" height="36" title="rTorrent"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/sabnzbd.png" height="36" title="SABnzbd"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/nzbget.png" height="36" title="NZBGet"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/overseerr.png" height="36" title="Overseerr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellyseerr.png" height="36" title="Jellyseerr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/tmdb.png" height="36" title="TMDB"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/prowlarr.png" height="36" title="Prowlarr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/maintainerr.png" height="36" title="Maintainerr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/plex.png" height="36" title="Plex"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellyfin.png" height="36" title="Jellyfin"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/emby.png" height="36" title="Emby"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/kodi.png" height="36" title="Kodi"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/tautulli.png" height="36" title="Tautulli"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellystat.png" height="36" title="Jellystat"/> <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/tracearr.svg" height="36" title="Tracearr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/trakt.png" height="36" title="Trakt"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/suggest-arr.png" height="36" title="SuggestArr"/></p>

---

> [!IMPORTANT]
> ### Your own TMDB API key — needed by 1 September 2026
>
> **If you use Seerr (Overseerr / Jellyseerr), this does not affect you.** Posters, search and title details all come through Seerr, and nothing changes for you.
>
> Everyone else needs a free TMDB API key by **1 September 2026**. Until then everything keeps working as it always has. The reason is simple: the card is going through the official HACS review, and the rules there do not allow a shared key to be built into the code, so it has to go.
>
> Getting one takes a minute at [themoviedb.org](https://www.themoviedb.org) → Settings → API — it is free and no payment details are asked for. Then paste it into **Settings → Devices & Services → Arr Stack → Reconfigure → Discovery**.
>
> Without a key after that date the posters, ratings, cast, trailers and the Trending and Popular rows stop loading. Everything tied to your own libraries — Radarr, Sonarr, downloads, the calendar — carries on regardless.
>
> Sorry for the errand. The card never asked you for anything before, and the notice disappears on its own once a key is filled in or Seerr is set up.

---

## Why is this needed?

Browsers block direct API calls from a web page to local network services (CORS policy). This integration solves that by routing all requests through Home Assistant's own API — keeping your API keys secure on the server side and requiring HA authentication for every call.

---

## Supported Services

| Service | Role | Required |
|---------|------|----------|
| Radarr | Movie library management | ✅ Yes |
| Sonarr | TV show library management | ✅ Yes |
| Radarr 2 | Second Radarr instance (e.g. 4K) | Optional |
| Sonarr 2 | Second Sonarr instance (e.g. 4K) | Optional |
| qBittorrent | Torrent download client | Optional |
| Deluge | Torrent download client | Optional |
| rTorrent / ruTorrent | Torrent download client | Optional |
| SABnzbd | Usenet download client | Optional |
| NZBGet | Usenet download client | Optional |
| Seerr (Overseerr / Jellyseerr) | Media discovery & requests | Optional |
| Bazarr | Subtitle management | Optional |
| Plex | Stream monitoring & playback control | Optional |
| Jellyfin | Stream monitoring & playback control (via HA integration — no config needed here) | Optional |
| Emby | Stream monitoring & playback control | Optional |
| Kodi | Stream monitoring & playback control (via HA integration — no config needed here) | Optional |
| Tautulli | Watch history, statistics & account sharing detection | Optional |
| Jellystat | Watch history and statistics | Optional |
| Tracearr *(beta)* | Watch history, statistics, and usage analytics | Optional |
| Prowlarr | Indexer management and search statistics | Optional |
| Trakt | Personalised recommendations — needs a paid VIP account | Optional |
| SuggestArr | Free recommendations from what you have watched | Optional |
| Maintainerr | Automatic library cleanup, with countdowns shown across the card | Optional |
| Gluetun | VPN status in the downloads panel | Optional |

> **Note:** Plex, Jellyfin, and Kodi also require their official Home Assistant integrations to be installed and connected — [Plex](https://www.home-assistant.io/integrations/plex/), [Jellyfin](https://www.home-assistant.io/integrations/jellyfin/), [Kodi](https://www.home-assistant.io/integrations/kodi/). The card uses these HA integrations for live stream detection. Emby does not have an official HA integration — configure it directly in Arr Stack instead.

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations**
2. Click the **⋮** menu (top right) → **Custom repositories**
3. Add `https://github.com/martinargalas/arr-stack-integration` — category **Integration**
4. Search for **Arr Stack Integration** and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → + Add Integration**
7. Search for **Arr Stack** and follow the setup wizard

### Manual

1. Copy the `custom_components/arr_stack/` folder to your HA `/config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

> ⚠️ After any change to the integration settings, **restart Home Assistant** for changes to take effect.

---

## Setup Wizard

Setup starts with two steps that are always shown, followed by steps for the services you select.

### Global Settings

| Field | Default | Notes |
|-------|---------|-------|
| Skip SSL certificate verification | Off | Enable if any of your services use a self-signed or untrusted certificate. Applies to all services at once. |

### Service Selection

Choose which optional services you want to configure. Only the selected steps will appear. **Radarr and Sonarr are always configured** — they are required for the card to work.

| Toggle | Services configured |
|--------|-------------------|
| Torrent clients | qBittorrent, Deluge, rTorrent |
| Usenet clients | SABnzbd, NZBGet |
| 2nd instances | Radarr 2, Sonarr 2 |
| Bazarr | Bazarr |
| Discovery | TMDB, Seerr, family and guest accounts |
| Plex / Emby | Plex, Emby |
| Streaming stats | Tautulli, Jellystat, Tracearr |
| Prowlarr | Prowlarr |
| Recommendations | Trakt, SuggestArr |
| Maintainerr | Maintainerr |
| Gluetun | Gluetun |

---

### Media — Radarr + Sonarr *(required)*

| Field | Example |
|-------|---------|
| Radarr URL | `http://192.168.1.10:7878` |
| Radarr API key | Find in Radarr → Settings → General |
| Sonarr URL | `http://192.168.1.10:8989` |
| Sonarr API key | Find in Sonarr → Settings → General |

---

### Torrent clients — qBittorrent + Deluge + rTorrent *(optional)*

| Field | Example |
|-------|---------|
| qBittorrent URL | `http://192.168.1.10:8080` |
| qBittorrent username | `admin` |
| qBittorrent password | `••••` |
| Deluge URL | `http://192.168.1.10:8112` |
| Deluge password | Your Deluge Web UI password |
| rTorrent URL | `http://192.168.1.10:9080` — base URL of ruTorrent |
| rTorrent username | HTTP Basic auth username (if configured) |
| rTorrent password | HTTP Basic auth password |

Leave any field empty to skip that service individually.

---

### Usenet clients — SABnzbd + NZBGet *(optional)*

| Field | Example |
|-------|---------|
| SABnzbd URL | `http://192.168.1.10:8080` |
| SABnzbd API key | Find in SABnzbd → Config → General |
| NZBGet URL | `http://192.168.1.10:6789` |
| NZBGet username | `nzbget` (default) |
| NZBGet password | Find in NZBGet → Settings → Security |

Leave any field empty to skip that service individually.

---

### 2nd instances — Radarr 2 + Sonarr 2 *(optional)*

Configure a second Radarr and/or Sonarr instance — useful for HD + 4K setups.

| Field | Example |
|-------|---------|
| Radarr 2 URL | `http://192.168.1.10:7879` |
| Radarr 2 API key | `••••` |
| Sonarr 2 URL | `http://192.168.1.10:8990` |
| Sonarr 2 API key | `••••` |

---

### Bazarr *(optional)*

| Field | Example |
|-------|---------|
| Bazarr URL | `http://192.168.1.10:6767` |
| Bazarr API key | Find in Bazarr → Settings → General |

---

### Discovery — TMDB, Seerr, accounts *(optional)*

Where the card gets posters, metadata and requests from. This step has four parts, all optional.

**TMDB** — needed only if you do **not** use Seerr. See the notice at the top of this page: fill in your own key before **1 September 2026** and posters, ratings, cast, trailers and the Trending and Popular rows keep working. With Seerr configured you can skip this section entirely.

| Field | Notes |
|-------|-------|
| TMDB API key | Free from [themoviedb.org](https://www.themoviedb.org) → Settings → API |

**Seerr** — Overseerr and Jellyseerr have merged under the name Seerr; both existing installations work here unchanged. Without it, movies and shows are added straight to Radarr and Sonarr; with it you get requests, approvals and multi-user support.

| Field | Notes |
|-------|-------|
| Seerr URL | `http://192.168.1.10:5055` |
| Seerr API key | Find in Seerr → Settings → General |

**Family account** — a non-admin Seerr account shared by the household. Requests made by non-admin Home Assistant users go through it, so they appear in Seerr as ordinary requests waiting for approval rather than as admin actions.

| Field | Notes |
|-------|-------|
| Family account email | Login email of that Seerr account |
| Family account password | Password for it |

**Guest account** — a second non-admin Seerr account for visitors or anyone you would rather keep separate from the household. With both accounts filled in, a **Users** tab appears in the card editor where each Home Assistant user is assigned to one or the other; anyone not assigned falls back to the family account.

| Field | Notes |
|-------|-------|
| Guest account email | Login email of that Seerr account |
| Guest account password | Password for it |

---

### Plex / Emby *(optional)*

**Plex** — authenticate via the Plex login link shown during setup. This enables stream monitoring, active user display, and playback control.

| Field | Notes |
|-------|-------|
| Plex Server URL | Leave empty to auto-detect. Fill in if HA runs on a different machine or VLAN than Plex — e.g. `http://192.168.1.10:32400`. |

> **Note:** Plex Now Playing in the card also requires the official [Plex integration](https://www.home-assistant.io/integrations/plex/) installed in HA.

**Emby** — enter your Emby server URL and API key to enable stream monitoring and remote stop with a message.

| Field | Notes |
|-------|-------|
| Emby URL | `http://192.168.1.10:8096` |
| Emby API key | Find in Emby → Dashboard → API Keys → New API Key |

> **Jellyfin and Kodi** do not require any configuration here. Install the official [Jellyfin](https://www.home-assistant.io/integrations/jellyfin/) or [Kodi](https://www.home-assistant.io/integrations/kodi/) HA integration and the card picks them up automatically.

---

### Streaming stats — Tautulli + Jellystat + Tracearr *(optional)*

| Field | Notes |
|-------|-------|
| Tautulli URL | `http://192.168.1.10:8181` |
| Tautulli API key | Find in Tautulli → Settings → Web Interface |
| Jellystat URL | `http://192.168.1.10:4000` |
| Jellystat API key | Find in Jellystat → Settings |
| Tracearr URL | `http://192.168.1.10:3102` — default port is 3102 |
| Tracearr API key | Find in Tracearr → Settings → API |
| Tracearr session cookie | Required for statistics — see below |
| Tracearr refresh token | Older alternative to the cookie — see below |

> Tautulli also powers **account sharing detection** — alerts when the same user streams from multiple IPs simultaneously.

> **Tracearr is currently in beta.** Some features may be incomplete or change in future updates.

#### Tracearr session cookie

The API key alone only reaches Tracearr's public endpoints. Watch history, library and storage statistics — everything the card actually shows — sit behind the same login its own web interface uses, so one more field is needed.

**How to get it:**

1. Open Tracearr in your browser and sign in as you normally would
2. Press **F12** → **Application** tab → **Cookies** → select your Tracearr address
3. Find the entry whose name starts with `better-auth.session_token` and copy **both the name and the value**, written as `name=value`
4. Paste that into the **Tracearr session cookie** field

The cookie lasts as long as your Tracearr login does. If the statistics stop loading one day, sign in again and copy a fresh one.

> **Refresh token** — the older way of doing the same thing, kept for accounts that already have one. It is being retired and will stop working, so use the session cookie. Accounts that sign in through Plex never had a refresh token to begin with; for those the cookie has always been the only way.

---

### Prowlarr *(optional)*

| Field | Example |
|-------|---------|
| Prowlarr URL | `http://192.168.1.10:9696` |
| Prowlarr API key | Find in Prowlarr → Settings → General |

---

### Gluetun *(optional)*

Displays a VPN status badge in the downloads panel — current status, public IP, country, and provider logo.

Gluetun's control server must be reachable from Home Assistant:

1. **Expose port 8000** in your Gluetun container — map it to any free host port, e.g. `8002:8000`
2. **Create an API key config** at `/gluetun/auth/config.toml` (bind-mounted into the container):
   ```toml
   [[roles]]
   name = "admin"
   auth = "apikey"
   apikey = "your-api-key"
   routes = ["GET /v1/vpn/status", "GET /v1/publicip/ip"]
   ```
3. Enter the **URL** (e.g. `http://192.168.1.10:8002`) and your **API key** in the setup step.

> The `auth = "apikey"` line is required — Gluetun does not support unauthenticated access. Without the config file the container will crash on startup.

---

### Recommendations — Trakt + SuggestArr *(optional)*

Two independent sources of "what should I watch next". Each gets its own category in the card and you can use either, both, or neither.

#### SuggestArr

Trakt has moved personalised recommendations behind its paid VIP plan. [SuggestArr](https://github.com/giuseppe99barchetta/SuggestArr) is a free, self-hosted alternative that needs no third-party account: it reads what you have actually watched on Plex, Jellyfin or Emby and suggests titles you do not own yet.

| Field | Notes |
|-------|-------|
| SuggestArr URL | `http://192.168.1.10:5001` |
| SuggestArr username | Leave empty if SuggestArr runs with `AUTH_MODE=local_bypass` or with authentication disabled |
| SuggestArr password | Leave empty for the same reason |

> **Turn off automatic requests in SuggestArr.** In SuggestArr's own settings, stop it from sending requests to Seerr on its own. Its background job runs on a schedule, so left on it will request titles by itself and you only find out afterwards. With it off, the suggestions wait in the card until you approve them.

SuggestArr refills its pool on its own schedule, so once you have worked through the current suggestions, a fresh batch can take a few hours to appear.

#### Trakt

Personalised recommendations from your Trakt watch history. **Trakt now requires a paid VIP account** for this — without one the API returns nothing and the category stays empty.

> **Scrobbling required for personalised results.** Recommendations are based on your watch history — titles you've already seen are filtered out and the suggestions are tailored to your taste. For this to work, your plays need to be synced to Trakt automatically. If you use Plex, [PlexTraktSync](https://github.com/Taxel/PlexTraktSync) is a good option — run it as a Docker container in `watch` mode and it will mark titles as watched on Trakt in real time as you finish them.

1. Go to [trakt.tv/oauth/applications/new](https://trakt.tv/oauth/applications/new) and create a new application (redirect URI: `urn:ietf:wg:oauth:2.0:oob`)
2. Copy the **Client ID** and **Client Secret** into the setup step
3. Visit the shown URL on trakt.tv, enter the code, then click Submit

---

### Maintainerr *(optional)*

[Maintainerr](https://github.com/jorenn92/Maintainerr) cleans up your library by rules — "delete a movie 30 days after everyone has watched it", and so on. Connecting it does two things: it gives the card a full Maintainerr panel, and it puts a **countdown badge on every title queued for deletion**, everywhere in the card. That second part is the real gain — you see what is about to disappear while browsing, not only when you go looking.

Maintainerr has no authentication, so only the address is needed.

| Field | Example |
|-------|---------|
| Maintainerr URL | `http://192.168.1.10:6246` — default port is 6246 |

In the card you can then browse and run rules, edit them or build new ones, manage collections and exclusions, see the deletion schedule on a calendar, and check how much space the cleanup has reclaimed.

---

## Family & Guest Accounts

If you configure a family account (non-admin Seerr user), the card uses that account for media requests made by non-admin HA users. This lets household members request media without admin privileges.

You can optionally add a **guest account** — a second non-admin Seerr user for visitors or temporary users. Once both accounts are configured, a **Users** tab appears in the card editor where you can map specific HA users to either the Family or Guest account. Users not explicitly mapped default to the Family account.

---

## Sensors & entities

This integration does not expose any Home Assistant sensors, entities, or devices. It acts purely as a proxy — all data is fetched on demand by the card.

---

## Reconfigure

Change any setting at any time without reinstalling:

**Settings → Devices & Services → Arr Stack → ⋮ → Reconfigure**

Your existing settings are pre-filled. Clearing a URL disables that service in the card.

---

## Anonymous usage metrics

The card sends one anonymous ping per browser session: its version, whether it is running on a phone, and which services are configured — just the names, no URLs, no keys, no titles, nothing about your library. The installation is identified by a short hash of your dashboard's hostname, so it cannot be traced back to you. You can see exactly what is collected at [argalas.org/arr-stats](https://argalas.org/arr-stats).

Knowing which parts people actually use is what guides where the work goes next, so leaving it on genuinely helps. If you would rather not take part, that is entirely fine:

**Settings → Devices & Services → Arr Stack → ⋮ → Reconfigure** → tick **Metrics collection** in the service list → turn on the opt-out switch on the final step.

This installation then stops sending anything.

---

## Related

- [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) — the Lovelace card that uses this integration
