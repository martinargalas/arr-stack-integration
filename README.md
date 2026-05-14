# Arr Stack Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/github/v/release/martinargalas/arr-stack-integration?cacheSeconds=0)](https://github.com/martinargalas/arr-stack-integration/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.x%2B-brightgreen.svg)](https://www.home-assistant.io)
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
| Seerr | Media discovery & requests | ✅ Yes |
| qBittorrent | Torrent download client | Optional |
| SABnzbd | Usenet download client | Optional |
| Bazarr | Subtitle management | Optional |

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
>
> When settings are changed, a notification appears in **Settings → Repairs** with a one-click restart option.

---

## Minimum Configuration

Only three services are required. Leave qBittorrent, SABnzbd, and Bazarr fields empty if you don't use them — they will simply not appear in the card.

**Step 1 — Downloads** *(all optional)*
- Leave blank if you don't use qBittorrent or SABnzbd

**Step 2 — Media management** *(required)*
- Radarr URL + API key
- Sonarr URL + API key

**Step 3 — Discovery** *(Seerr required, rest optional)*
- Seerr URL + API key
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
| Seerr URL | `http://192.168.1.10:5055` | Required (Jellyseerr also supported) |
| Seerr API key | `••••` | Required |
| Family account email | `user@example.com` | Optional — non-admin Overseerr/Jellyseerr account for household users |
| Family account password | `••••` | Optional — password for the Overseerr/Jellyseerr account above |
| Bazarr URL | `http://192.168.1.10:6767` | Optional |
| Bazarr API key | `••••` | Optional |

---

## Family Account

If you configure a family account (non-admin Seerr user), the card will use that account for media requests when the logged-in HA user is not an admin. This allows household members to request media without admin privileges.

---

## Sensors & entities

This integration currently does not expose any Home Assistant sensors, entities, or devices. It acts purely as a proxy — all data is fetched on demand by the card and displayed directly.

Native HA sensors (download progress, queue status, library counts, etc.) are planned for a future release.

---

## Reconfigure

You can change the integration settings at any time without reinstalling:

**Settings → Devices & Services → Arr Stack → ⋮ → Reconfigure**

All fields support being cleared — removing a URL disables that service in the card.

---

## Related

- [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card) — the Lovelace card that uses this integration
