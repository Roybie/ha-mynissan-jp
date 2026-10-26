# MyNISSAN Japan for Home Assistant

Unofficial integration for the 2025+ Nissan Leaf (ZE2) and other cars that use a
NISSAN ID in the Japanese MyNISSAN app (第2世代NissanConnect / NissanConnect
インフォテインメントシステム). Cars on the older NissanConnect member ID are served
by [HomeAssistant-NissanConnect-JP](https://github.com/developerfromjokela/HomeAssistant-NissanConnect-JP).

## What it shows

Every 5 minutes (2 while charging) it reads the data Nissan holds for the car. This
does not wake the car, so values are as of the car's last report (see the *Last
updated* sensor). Both intervals can be changed under **Configure** on the
integration.

- Battery level, range, available energy, battery capacity
- Plugged in, charging, charge state, charge time remaining
- Odometer, cabin temperature, climate running
- Lock, doors, hatch, hood, warning lamps
- Location

> **Sensors only.** This version only reads data. Controls such as climate, charging,
> a charge limit and asking the car for fresh data may come in a later version; see
> [docs/controls.md](docs/controls.md) for what is known so far.

## Install

Copy `custom_components/mynissan_jp` into your Home Assistant `config/custom_components/`
folder (or add this repository to HACS as a custom repository), restart, then add
**MyNISSAN Japan** under Settings → Devices & services.

## Signing in

NISSAN ID only hands the login back to the MyNISSAN app, so the setup dialog asks
you to copy it by hand:

1. On a computer, open Chrome DevTools (⌘⌥I / F12) on the **Network** tab.
2. Open the login link from the dialog in that tab (not on a phone with MyNISSAN).
3. Sign in with your NISSAN ID and the access code emailed to you.
4. Copy the `ncx://ciam.prd/login?code=…` address of the last request in the Network
   tab and paste it into the dialog within a few minutes.

After that the session renews itself. If it ever expires, Home Assistant asks you to
sign in again the same way.

## Development

```
python3 -m venv .venv-test
.venv-test/bin/pip install pytest-homeassistant-custom-component
.venv-test/bin/python -m pytest
```

`nissan_jp_probe.py` reads every endpoint the app knows about and writes a redacted
`probe_result.json`, which helps when mapping new fields or cars.
