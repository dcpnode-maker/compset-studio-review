# Phone gateways and measured public proxies

CompSet keeps two separate route inventories. Public proxy measurements are unauthenticated neutral HTTPS checks. Owned phone routes require explicit pairing to a certificate, a private LAN endpoint and a token that is never saved in the registry. A working echo request does not demonstrate that an OTA accepts that route.

The 2026-09-28 finite public batch fetched 4,728 lines and normalized 4,038 unique candidates. Of 2,000 selected, 939 completed within the 900-second deadline: 100 passed valid TLS and a public IP echo, 839 failed, and 1,061 selected candidates were unfinished. The successes reported 95 distinct exit addresses. A second bounded check of the fastest 20 successes passed 10; all ten reported the same address as their earlier observation. These are transient measurements, not a promise of stable or low-latency service.

Local measurement artifacts are in ignored `data/routes/proxy-health-20260928T093958Z/`, including `README.md`, `measurement-summary.json`, `working_proxies.json`, `working_proxies.txt`, and `repeat-canary/`. They have not been activated for accommodation collection or authenticated account traffic.

## Owned-phone pairing

The native app source is in `android-gateway/`. Minimum Android is 6/API23; the APK contains Java code without ABI-specific native libraries. This is a build compatibility target, not proof for every phone/version. On the OnePlus10R with Android15/API35, version 0.1.3 passed a verified Wi-Fi neutral HTTPS probe. The later cellular attempt confirmed network selection but failed at the duplicate-only DNS64 compatibility check. Visible Stop closed a verified TLS connection and removed the listener/service; the final button-disabled UI assertion was unverified. OnePlus11R/Nord5 Android16 and old Android6/7/10 devices remain untested. See `docs/android-gateway.md` and `handoff/reviews/029-android-device-tls.md` for dates and exact proof limits.

The phone and desktop initially use the same private Wi-Fi subnet. Android exposes the outbound network choices; requesting a cellular connection does not guarantee both SIMs can carry data concurrently. The phone binds each outbound DNS lookup and connection to the selected network. Several phones on the same Wi-Fi can share one external address.

1. Open CompSet Gateway and enter the desktop's current private IPv4 address.
2. Choose an available outbound network. Request cellular if that is the intended route.
3. Export the public pairing certificate, compare its displayed SHA256 fingerprint, and reveal the token privately. No CA is installed into Android or Windows.
4. Register the phone with the CLI below. The certificate is public; the token stays in the named process environment variable and is excluded from JSON/status output.
5. Start the visible gateway on the phone and run a neutral probe. Stop remains available in the app and foreground notification. Repeat pairing after an intentional credential reset; a changed endpoint with assigned sessions requires a new route ID.

From the CompSetStudio directory:

```powershell
.venv\Scripts\python.exe -m routes.owned_devices register --id phone1 --label "My phone" --host <phone-private-ip> --certificate <exported-public-certificate.pem> --fingerprint <displayed-sha256> --token-env COMPSET_PHONE_ONE
.venv\Scripts\python.exe -m routes.owned_devices probe --id phone1
.venv\Scripts\python.exe -m routes.owned_devices status
.venv\Scripts\python.exe -m routes.owned_devices assign --session explicit-job-session
```

`COMPSET_PHONE_ONE` must contain the token for the probe process. Do not place the token in command-line arguments, Git, screenshots or logs. The registry defaults to ignored `routes/data/owned-devices.json`; its certificate and endpoint are checked before client construction. TLS to the phone requires both a trusted exported certificate and the exact fingerprint. Target HTTPS uses normal independent certificate and hostname verification inside CONNECT. Proxy authorization is sent only to the phone after the proxy TLS handshake.

New sessions distribute across phones with successful probes from the past hour. Existing sessions retain the original phone and stop when its health becomes stale or failed; there is no automatic fallback after failure. A process-safe compare/write lock rejects stale registry instances rather than overwriting another session's assignment. Reload the registry after such a rejection. This client does not change production collectors or source cooldowns; adapter integration and device egress proof are distinct work.

Official references: [Android physical-device setup](https://developer.android.com/studio/run/device), [foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types), and [urllib3 HTTPS proxy verification](https://urllib3.readthedocs.io/en/stable/reference/urllib3.poolmanager.html#urllib3.ProxyManager).
