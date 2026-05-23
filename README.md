# Arr Stack Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/martinargalas/arr-stack-integration?cacheSeconds=0)](https://github.com/martinargalas/arr-stack-integration/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-brightgreen.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Discord](https://img.shields.io/discord/1503764189057908798?logo=discord&label=chat&color=5865F2&logoColor=white)](https://discord.gg/SUfDr52G)

<a href="https://buymeacoffee.com/argii" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>

<a href="https://discord.gg/SUfDr52G" target="_blank"><img src="https://img.shields.io/badge/Join%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord" height="50"></a>

A Home Assistant custom integration that acts as a secure server-side proxy between the [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) and your local media services.

---

## Why is this needed?

Browsers block direct API calls from a web page to local network services (CORS policy). This integration solves that by routing all requests through Home Assistant's own API — keeping your API keys secure on the server side and requiring HA authentication for every call.

---

## Supported Services

| Service | Role | Required |
|---------|------|----------|
| Radarr | Movie library management | ✅ Yes |
| Sonarr | TV show library management | ✅ Yes |
| Overseerr / Jellyseerr | Media discovery & requests | ✅ Yes |
| qBittorrent | Torrent download client | Optional |
| SABnzbd | Usenet download client | Optional |
| Bazarr | Subtitle management | Optional |
| Plex | Stream monitoring & playback control | Optional |
| Tautulli | Watch history & statistics | Optional |

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations**
2. Click the **⋮** menu (top right) → **Custom repositories**
3. Add `https://github.com/martinargalas/arr-stack-integration` — category **Integration**
4. Click **+ Explore & Download Repositories**, search for **Arr Stack Integration** and install
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

The integration is configured via a 4-step wizard.

**Step 1 — Downloads** *(all optional)*

| Field | Example |
|-------|---------|
| qBittorrent URL | `http://192.168.1.10:8080` |
| qBittorrent username | `admin` |
| qBittorrent password | `••••` |
| SABnzbd URL | `http://192.168.1.10:8080` |
| SABnzbd API key | `••••` |

**Step 2 — Media Management** *(required)*

| Field | Example |
|-------|---------|
| Radarr URL | `http://192.168.1.10:7878` |
| Radarr API key | `••••` |
| Sonarr URL | `http://192.168.1.10:8989` |
| Sonarr API key | `••••` |

**Step 3 — Discovery & Subtitles** *(Overseerr/Jellyseerr required, rest optional)*

| Field | Example | Notes |
|-------|---------|-------|
| Overseerr / Jellyseerr URL | `http://192.168.1.10:5055` | Required |
| Overseerr / Jellyseerr API key | `••••` | Required |
| Family account email | `user@example.com` | Optional — non-admin account for household users |
| Family account password | `••••` | Optional |
| Bazarr URL | `http://192.168.1.10:6767` | Optional |
| Bazarr API key | `••••` | Optional |

**Step 4 — Plex & Tautulli** *(both optional)*

| Field | Notes |
|-------|-------|
| Plex | Authenticate via the Plex login link — enables stream monitoring and playback control |
| Tautulli URL | `http://192.168.1.10:8181` |
| Tautulli API key | Found in Tautulli → Settings → Web Interface → API Key |

---

## Family Account

If you configure a family account (non-admin Overseerr/Jellyseerr user), the card will use that account for media requests when the logged-in HA user is not an admin. This allows household members to request media without admin privileges.

---

## Sensors & entities

This integration currently does not expose any Home Assistant sensors, entities, or devices. It acts purely as a proxy — all data is fetched on demand by the card and displayed directly.

---

## Reconfigure

You can change the integration settings at any time without reinstalling:

**Settings → Devices & Services → Arr Stack → ⋮ → Reconfigure**

All fields support being cleared — removing a URL disables that service in the card.

---

## Related

- [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) — the Lovelace card that uses this integration
