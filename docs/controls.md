# Controls: notes for a later version

The integration currently only reads data. This note collects what is known about
the car controls in the MyNISSAN app (Android v3.6.0, `jp.co.nissan.nissanconnect.ncx`),
so the work can be picked up later.

## What is known

Commands go to the same backend as the read endpoints, with the same token:

- Base: `https://nc-app-bff-prod.apps.jp.kamereon.io/nc-app-bff/`
- Command services: `nissan/remote-action/v1/cars/{vin}/…` and `nissan/remote-action/v2/cars/{vin}/…`.
  Also `alliance/car-adapter/v1|v2/cars/{vin}/actions/…`, which the old integration used.
- Command results: `alliance/action-status-polling/v1/cars/{vin}/…`. Commands complete
  asynchronously, so the app polls for the outcome (paths `/actions/status`, `/actions/set`).

Action paths found in the app:

| Path | Likely use |
|---|---|
| `/actions/wake-up-vehicle` | Ask the car to send fresh data |
| `/actions/refresh-battery-status`, `refresh-hvac-status`, `refresh-location`, `refresh-lock-status` | Refresh one part of the data |
| `/hvac-control` | Start or stop climate (pre-heat or cool) |
| `/actions/hvac-schedule` | Climate timers |
| `/actions/charging-start` | Charge now |
| `/actions/charge-schedule` | Charging timers |
| `/actions/minimum-charge` | Minimum charge level |
| (app screen `ChargeLimitationSetting`) | Charge limit (充電上限値), endpoint not identified |
| `/actions/send-navigation` | Send a destination to the car |
| `/actions/data-reset` | Reset trip data |
| `/actions/engine-start` | Remote start, petrol cars only |

The car's entitlements (`nissan/account/v1/cars/{vin}/entitlements`) on the test Leaf:

```json
{"doorLockUnlock": {"remoteLock": true, "reminderToLockNotificationSetting": true},
 "hvacStart": {"remoteHvac": true, "hvacSettingCard": true}}
```

Remote lock is entitled, but no lock command was found in the app's strings; it may
need an extra PIN step (the old Kamereon API used SRP for lock and unlock).

Related read endpoints that already work (`alliance/car-adapter/v1/cars/{vin}/…`):
`hvac-settings` (target temperature, seat and steering heaters, 5 schedules) and
`charging-settings` (mode, 5 weekly schedules).

## What is not known

The request body for each command. Only the addresses were recovered from the
compiled app (a Flutter build, so the logic itself is not readable). Guessing means
sending trial commands to a real car, so the formats should be captured instead.

## How to capture the formats

1. Pull the APK from the phone (`adb shell pm path jp.co.nissan.nissanconnect.ncx`,
   then `adb pull` each split).
2. Patch it to trust user-installed certificates (for example with `apk-mitm`), and
   install it in place of the store version.
3. Run `mitmproxy` on the Mac, set the phone's Wi-Fi proxy to it, and install its
   certificate on the phone.
4. In the app, use each control once: refresh, climate on and off, charge now, charge
   limit, the timers. Record the requests and the status polling that follows.
5. Restore the store version of the app afterwards.

The capture contains tokens and the VIN, so keep it out of the repository.

## Ideas for entities

- **Update** button: wake the car and poll until new data arrives. Optionally an
  automatic wake interval, kept long (the old integration defaulted to 60 minutes)
  to spare the 12 V battery.
- **Climate** entity: start and stop with a target temperature. It would also carry
  the cabin temperature.
- **Start charging** button.
- **Charge limit** number entity.
- Possibly switches for the charging and climate timers, and a **lock** entity if the
  lock command turns up.
