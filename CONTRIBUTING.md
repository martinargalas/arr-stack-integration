# Contributing

Thanks for looking. Bug reports and pull requests are both welcome — open an issue first for anything large, so the approach can be agreed before you spend an evening on it.

This integration is the Home Assistant side of the [Arr Stack Card](https://github.com/martinargalas/ha-arr-stack-card): the card asks it for everything, and it talks to Radarr, Sonarr, the download clients, the media servers and the rest, so that no address or key ever reaches the browser.

## Where things are

Everything is in [`custom_components/arr_stack/`](custom_components/arr_stack):

| File | What it holds |
|------|---------------|
| `views.py` | The proxy. One view answers `/api/arr_stack/<service>/<path>`, with a branch per service (`elif service == "radarr":` …) and a route per path inside it. Almost every change lands here. |
| `config_flow.py` | The setup wizard and Reconfigure: which steps exist and what each one asks for. |
| `const.py` | The `CONF_*` keys a service's settings are stored under. |
| `strings.json`, `translations/en.json` | The wizard's wording. A new field needs its label in both. |
| `__init__.py` | Setup, the sensors, and registering the view. |

## Pull requests

- **Keep responses additive.** The card and the integration are released together, but people update one without the other. Add fields rather than renaming or removing them, and keep a route answering in the shape older cards expect.
- **A new service** needs its `CONF_*` keys, a step in the wizard, a branch in `views.py`, and an entry in the `capabilities` route, which is how the card learns it is set up.
- **Fail softly.** An unreachable or unconfigured service answers with an empty result or a clear status, never an exception that reaches Home Assistant's log as a traceback.
- **Never log secrets.** No API keys, passwords, tokens or cookies in a log line or a response — not even shortened.
- **Older versions of the services exist.** If you use something a newer Sonarr, rTorrent or Plex added, check what an older one says and fall back — see how the rTorrent queue retries without `d.load_date`.

The integration's tests are not published yet; they run before every merge. If a pull request changes what a route returns, say so in the description, so the card side can be checked against it.
