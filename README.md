# Arr Stack Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/martinargalas/arr-stack-integration?cacheSeconds=0)](https://github.com/martinargalas/arr-stack-integration/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.x%2B-brightgreen.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

<a href="https://buymeacoffee.com/argii" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>

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

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations
2. Click **+ Explore & Download Repositories**
3. Search for **Arr Stack Integration** and install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → + Add Integration**
6. Search for **Arr Stack** and follow the setup wizard

### Manual

1. Copy the `custom_components/arr_stack/` folder to your HA `/config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

> ⚠️ After any change to the integration settings, **restart Home Assistant** for changes to take effect.

---

## Minimum Configuration

Only three services are required. Leave qBittorrent, SABnzbd, and Bazarr fields empty if you don't use them — they will simply not appear in the card.

**Step 1 — Downloads** *(all optional)*
- Leave blank if you don't use qBittorrent or SABnzbd

**Step 2 — Media management** *(required)*
- Radarr URL + API key
- Sonarr URL + API key

**Step 3 — Discovery** *(Overseerr required, rest optional)*
- Overseerr/Jellyseerr URL + API key
- Family account email + password *(optional — for non-admin household users)*
- Bazarr URL + API key *(optional — for subtitle status badges)*

---

## Full Configuration

### Step 1 — Downloads

| Field | Example | Description |
|-------|---------|-------------|
| qBittorrent URL | `http://192.168.1.10:8088` | Leave empty to disable |
| qBittorrent username | `admin` | Leave empty to disable |
| qBittorrent password | `••••` | Leave empty to disable |
| SABnzbd URL | `http://192.168.1.10:8080` | Leave empty to disable |
| SABnzbd API key | `••••` | Leave empty to disable |

### Step 2 — Media Management

| Field | Example | Description |
|-------|---------|-------------|
| Radarr URL | `http://192.168.1.10:7878` | Required |
| Radarr API key | `••••` | Required |
| Sonarr URL | `http://192.168.1.10:8989` | Required |
| Sonarr API key | `••••` | Required |

### Step 3 — Discovery & Subtitles

| Field | Example | Description |
|-------|---------|-------------|
| Overseerr URL | `http://192.168.1.10:5055` | Required (Jellyseerr also supported) |
| Overseerr API key | `••••` | Required |
| Family account email | `user@example.com` | Optional — non-admin household user |
| Family account password | `••••` | Optional |
| Bazarr URL | `http://192.168.1.10:6767` | Optional |
| Bazarr API key | `••••` | Optional |

---

## Family Account

If you configure a family account (non-admin Overseerr user), the card will use that account for media requests when the logged-in HA user is not an admin. This allows household members to request media without admin privileges.

---

## Support

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-☕-yellow)](https://buymeacoffee.com/argii)

---

## Related

- [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) — the Lovelace card that uses this integration
