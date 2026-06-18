# Arr Stack Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/martinargalas/arr-stack-integration?cacheSeconds=0)](https://github.com/martinargalas/arr-stack-integration/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-brightgreen.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Discord](https://img.shields.io/discord/1503764189057908798?logo=discord&label=chat&color=5865F2&logoColor=white)](https://discord.gg/CA83tqYZ)

<a href="https://buymeacoffee.com/argii" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>

<a href="https://discord.gg/Q4jKKqRY" target="_blank"><img src="https://img.shields.io/badge/Join%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord" height="50"></a>

A Home Assistant custom integration that acts as a secure server-side proxy between the [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) and your local media services.

### Supported services

<p><img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/radarr.png" height="36" title="Radarr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/sonarr.png" height="36" title="Sonarr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/bazarr.png" height="36" title="Bazarr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/qbittorrent.png" height="36" title="qBittorrent"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/deluge.png" height="36" title="Deluge"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/rutorrent.png" height="36" title="rTorrent"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/sabnzbd.png" height="36" title="SABnzbd"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/nzbget.png" height="36" title="NZBGet"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/overseerr.png" height="36" title="Overseerr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellyseerr.png" height="36" title="Jellyseerr"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/tmdb.png" height="36" title="TMDB"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/prowlarr.png" height="36" title="Prowlarr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/plex.png" height="36" title="Plex"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellyfin.png" height="36" title="Jellyfin"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/emby.png" height="36" title="Emby"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/kodi.png" height="36" title="Kodi"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/tautulli.png" height="36" title="Tautulli"/> <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/jellystat.png" height="36" title="Jellystat"/> <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/tracearr.svg" height="36" title="Tracearr"/> &nbsp; <img src="https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/trakt.png" height="36" title="Trakt"/></p>

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
| Overseerr / Jellyseerr | Media discovery & requests | Optional |
| Bazarr | Subtitle management | Optional |
| Plex | Stream monitoring & playback control | Optional |
| Jellyfin | Stream monitoring & playback control (via HA integration — no config needed here) | Optional |
| Emby | Stream monitoring & playback control | Optional |
| Kodi | Stream monitoring & playback control (via HA integration — no config needed here) | Optional |
| Tautulli | Watch history, statistics & account sharing detection | Optional |
| Jellystat | Watch history and statistics | Optional |
| Tracearr *(beta)* | Watch history, statistics, and usage analytics | Optional |
| Prowlarr | Indexer management and search statistics | Optional |
| Trakt | Personalised movie & show recommendations | Optional |

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
| Discovery | Overseerr / Jellyseerr |
| Plex / Emby | Plex, Emby |
| Streaming stats | Tautulli, Jellystat, Tracearr |
| Prowlarr | Prowlarr |
| Trakt | Trakt |

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

### Discovery — Overseerr / Jellyseerr *(optional)*

Trending, popular, and upcoming sections are always available without Overseerr. Adding it enables request approvals and family account support.

| Field | Notes |
|-------|-------|
| Overseerr / Jellyseerr URL | `http://192.168.1.10:5055` |
| Overseerr / Jellyseerr API key | Find in Settings → General |
| Family account email | Optional — non-admin account for household members |
| Family account password | Optional |

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
| Tracearr refresh token | See below |

> Tautulli also powers **account sharing detection** — alerts when the same user streams from multiple IPs simultaneously.

> **Tracearr is currently in beta.** Some features may be incomplete or change in future updates.

#### Tracearr refresh token

The Tracearr API key (from Settings → API) is sufficient for read-only access. Some analytics features require an additional **refresh token**, which is the long-lived authentication token Tracearr issues when you log in.

**How to get it:**

1. Open Tracearr in your browser and log in with your **local username and password** (not Plex Sign-In — SSO accounts do not have a locally stored token)
2. Open browser Developer Tools: **F12** → **Application** tab → **Local Storage** → select your Tracearr URL
3. Find the entry named `refreshToken` and copy its value
4. Paste it into the **Tracearr refresh token** field in the integration setup

**If you use Plex Sign-In to log into Tracearr** and have Plex configured in Arr Stack, you can leave the refresh token field empty — the integration will authenticate with Tracearr automatically using your Plex token.

---

### Prowlarr *(optional)*

| Field | Example |
|-------|---------|
| Prowlarr URL | `http://192.168.1.10:9696` |
| Prowlarr API key | Find in Prowlarr → Settings → General |

---

### Trakt *(optional)*

Enables personalised movie and show recommendations in the card based on your Trakt watch history.

> **Scrobbling required for personalised results.** Trakt recommendations are based on your watch history — titles you've already seen are filtered out and the suggestions are tailored to your taste. For this to work, your plays need to be synced to Trakt automatically. If you use Plex, [PlexTraktSync](https://github.com/Taxel/PlexTraktSync) is a good option — run it as a Docker container in `watch` mode and it will mark titles as watched on Trakt in real time as you finish them.

1. Go to [trakt.tv/oauth/applications/new](https://trakt.tv/oauth/applications/new) and create a new application (redirect URI: `urn:ietf:wg:oauth:2.0:oob`)
2. Copy the **Client ID** and **Client Secret** into the setup step
3. Visit the shown URL on trakt.tv, enter the code, then click Submit

---

## Family Account

If you configure a family account (non-admin Overseerr/Jellyseerr user), the card uses that account for media requests made by non-admin HA users. This lets household members request media without admin privileges.

---

## Sensors & entities

This integration does not expose any Home Assistant sensors, entities, or devices. It acts purely as a proxy — all data is fetched on demand by the card.

---

## Reconfigure

Change any setting at any time without reinstalling:

**Settings → Devices & Services → Arr Stack → ⋮ → Reconfigure**

Your existing settings are pre-filled. Clearing a URL disables that service in the card.

---

## Related

- [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) — the Lovelace card that uses this integration
