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
| Radarr 2 | Second Radarr instance (e.g. 4K) | Optional |
| Sonarr 2 | Second Sonarr instance (e.g. 4K) | Optional |
| Overseerr / Jellyseerr | Media discovery & requests | Optional |
| qBittorrent | Torrent download client | Optional |
| SABnzbd | Usenet download client | Optional |
| Bazarr | Subtitle management | Optional |
| Plex | Stream monitoring & playback control | Optional |
| Tautulli | Watch history, statistics & account sharing detection | Optional |
| Jellystat | Watch history and statistics | Optional |

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

The integration is configured via a 7-step wizard.

**Step 1 — Global Settings**

| Field | Default | Notes |
|-------|---------|-------|
| Skip SSL certificate verification | Off | Enable if any of your services use a self-signed or untrusted certificate (e.g. behind a reverse proxy). Applies to all services at once. Safe to enable even in mixed setups — services with valid certificates or plain HTTP are unaffected. |

**Step 2 — Downloads** *(all optional)*

| Field | Example |
|-------|---------|
| qBittorrent URL | `http://192.168.1.10:8080` |
| qBittorrent username | `admin` |
| qBittorrent password | `••••` |
| SABnzbd URL | `http://192.168.1.10:8080` |
| SABnzbd API key | `••••` |

**Step 3 — Media Management** *(required)*

| Field | Example |
|-------|---------|
| Radarr URL | `http://192.168.1.10:7878` |
| Radarr API key | `••••` |
| Sonarr URL | `http://192.168.1.10:8989` |
| Sonarr API key | `••••` |

**Step 4 — Second instances** *(all optional)*

Configure a second Radarr and/or Sonarr instance — useful for HD + 4K setups.

| Field | Example |
|-------|---------|
| Radarr 2 URL | `http://192.168.1.10:7879` |
| Radarr 2 API key | `••••` |
| Sonarr 2 URL | `http://192.168.1.10:8990` |
| Sonarr 2 API key | `••••` |

**Step 5 — Discovery & Subtitles** *(all optional)*

Trending, popular, and upcoming sections are always available. Overseerr/Jellyseerr adds request approval workflow and family account support.

| Field | Example | Notes |
|-------|---------|-------|
| Overseerr / Jellyseerr URL | `http://192.168.1.10:5055` | Optional |
| Overseerr / Jellyseerr API key | `••••` | Optional |
| Family account email | `user@example.com` | Optional — non-admin account for household users |
| Family account password | `••••` | Optional |
| Bazarr URL | `http://192.168.1.10:6767` | Optional |
| Bazarr API key | `••••` | Optional |

**Step 6 — Plex** *(optional)*

| Field | Notes |
|-------|-------|
| Plex | Authenticate via the Plex login link — enables stream monitoring and playback control |
| Plex Server URL | Leave empty to auto-detect. Fill in if auto-detection picks the wrong address — e.g. when HA runs on a different machine or VLAN than Plex (`https://plex.yourdomain.com` or `http://192.168.1.10:32400`). |

> **Note — Plex Now Playing** requires the [Plex integration](https://www.home-assistant.io/integrations/plex/) installed in HA. It creates `media_player.plex_*` entities that the card reads for active sessions. Authenticating Plex here (Step 6) additionally enables playback control (pause / resume / stop) and shows the active user on each stream card.

**Step 7 — Tautulli & Jellystat** *(both optional)*

| Field | Notes |
|-------|-------|
| Tautulli URL | `http://192.168.1.10:8181` |
| Tautulli API key | Found in Tautulli → Settings → Web Interface → API Key |
| Jellystat URL | `http://192.168.1.10:4000` |
| Jellystat API key | Found in Jellystat → Settings → API Key |

> **Note — Tautulli account sharing detection** scans recent watch history to identify users streaming from multiple IP addresses and alerts you via the Statistics section. Configure threshold and history depth via `security.*` keys in the card YAML.

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
