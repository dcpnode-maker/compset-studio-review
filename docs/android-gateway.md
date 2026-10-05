# Native Android gateway

CompSet Gateway is original native Java code in `android-gateway/`, licensed under MIT. It provides a user-started, finite HTTPS CONNECT route for a paired desktop. It does not run the scraper on the phone. A phone route becomes usable only after explicit pairing, certificate verification and an independent neutral connectivity test; it does not authorize automatic route changes when a source returns a challenge, 403 or 429.

## Architecture and pairing contract

`MainActivity` uses Android widgets to choose an actually exposed outbound network, one desktop's private IPv4 and session limits. `GatewayService` owns the visible foreground lifetime, wake lock, network callbacks and TLS listener. Its startup and teardown share a lifecycle lock so Stop cannot leave newly acquired resources behind. It is not sticky, has no boot receiver and stops when its task is removed. Android or the device manufacturer can still terminate a session.

The listener binds only to the phone's observed private Wi-Fi IPv4, TCP port **8443**. The paired desktop must have a different RFC1918 IPv4 in that Wi-Fi interface's subnet. Other source addresses are rejected before a TLS handshake. No public listener, relay server, tethering configuration, root, VPN or default-SIM change is created. LAN isolation on a Wi-Fi access point may prevent pairing.

Pairing has these exact fields:

| Field | Contract |
| --- | --- |
| Proxy endpoint | `https://<phone-private-ipv4>:8443` |
| Proxy protocol | TLS 1.2, then authenticated HTTP CONNECT |
| Proxy username | `compset` |
| Proxy password | Per-install 128-bit random token, 32 lowercase hex characters |
| Public certificate | PEM exported through Android's document picker |
| Certificate fingerprint | SHA-256 of DER certificate, 64 lowercase hex characters displayed on the phone |
| CONNECT target | An allowlisted DNS hostname with explicit port 443 |
| Probe | `https://httpbin.org/ip` on the selected phone network |

The private RSA-2048 key remains in AndroidKeyStore. The public self-signed certificate has CN `compset-phone-gateway`, a one-year validity and no IP Subject Alternative Name, because the phone's LAN address can change. The desktop must trust only the exported leaf and verify its exact fingerprint before transmitting proxy authentication. Ordinary system trust or disabled certificate verification is insufficient. The desktop independently verifies the destination server's normal public TLS certificate inside the tunnel. No interception CA is installed on either device.

The token is stored in private app preferences with Android backup disabled and explicit Android 12+ cloud/device-transfer exclusions. Revealing it sets the screen's secure flag; it is not copied to the clipboard or logged. Resetting the token requires the gateway to be stopped and invalidates the previous token. Clearing app data or reinstalling requires pairing again. An expired certificate requires a new installation identity and another verified pairing. The desktop registry stores public certificate metadata and a token environment-variable name, not the token itself. Root integration lives in `routes/owned_devices.py`. [Android backup rules](https://developer.android.com/identity/data/autobackup)

## Destination and resource rules

The core reads a bounded CONNECT header, authenticates before DNS and resolves once through the selected Android `Network`. Mixed public/private answers fail. Version 0.1.3 adds a narrow DNS64 compatibility rule: when Android advertises a /96 NAT64 prefix, a translated IPv6 answer may be removed only if its final four bytes exactly match a public native IPv4 answer in that same response. Prefix membership is checked before ordinary public-IPv6 classification. The original maximum of 16 answers still applies; null, private, unmatched translated, and matching unsupported-prefix answers reject the whole result. No address is manufactured and retained answers keep their original order. IPv6-only translation is not supported. API levels below 30 cannot supply this prefix observation and receive no DNS64 exception.

The upstream socket is bound to the chosen network, tracked for cancellation, then connected to an already resolved numeric IP. There is no second hostname lookup, alternate-IP retry or alternate-network fallback. Losing the selected route or LAN stops the service.

`DestinationPolicy.java` is the source of truth for accommodation domains and the exact neutral probe hosts. It rejects arbitrary IP authorities, non-443 ports, loopback, private, link-local, multicast, documentation and other reserved addresses. The selected domain allowlist is a routing constraint, not a guarantee that every path on those domains is accommodation content. The tunnel carries opaque destination TLS; the desktop retains source-specific request limits, parser checks and cooldowns.

| Limit | App behavior |
| --- | --- |
| Concurrent connections | 2, including handshake and DNS stages |
| Session duration | User chooses 60 minutes, 4 hours, 12 hours or 24 hours |
| Aggregate tunnel traffic | 64 MiB, 256 MiB, 1 GiB, 4 GiB or 16 GiB |
| Opened connections per session | 120, 500, 2,000 or 10,000 |
| TLS handshake / CONNECT-header socket timeout | 10 seconds |
| DNS wait | 5 seconds; bounded two-worker resolver |
| Numeric upstream connect | 10 seconds |
| Tunnel idle timeout | 20 seconds |
| Established tunnel absolute lifetime | 2 minutes |
| Repeated invalid authentication | Entire session stops after 8 failures |
| CONNECT request | At most 8 KiB and 50 header lines |

Traffic is counted in both directions before forwarding. The aggregate byte budget never increases itself. Connection count covers CONNECT tunnels, not encrypted HTTP requests within a tunnel. Stop closes listener, active and connecting sockets, timers and worker pools, then releases Android callbacks and the wake lock. A native DNS call may finish later if the OS ignores interruption, but the stopped tunnel does not connect afterward. Separate bounded forward and reverse pools avoid a concurrency deadlock under four core-level sessions; the app itself admits two.

## Compatibility target and limitations

The manifest targets API **37** and has minimum API **23**. Android's official API table maps these to Android 17 and Android 6. The code guards newer foreground-service, notification and local-network APIs. [Android SDK version table](https://developer.android.com/guide/topics/manifest/uses-sdk-element)

| Device / Android | Intended support | Actual proof |
| --- | --- | --- |
| Android 6 / 7 / 10 | API 23 minimum; no newer unguarded runtime APIs | No device test yet |
| OnePlus 10R, Android 15 | Native Java, API-guarded foreground gateway | 0.1.3 installed; Wi-Fi HTTPS passed; cellular HTTPS failed at DNS64 validation; visible Stop closed active TLS and removed service/listener |
| OnePlus 11R / Nord 5, Android 16 | Same single APK | Device test pending |
| Android 17 | API 37 build target and local-network runtime permission | No device test yet |

There are no native `.so` libraries or ABI-specific packages, so the APK does not require an ARM/ARM64/x86 variant. This is a packaging property, not proof on every manufacturer or future Android release. Android 17's setup page and installed SDK metadata were checked on 2026-09-28: platform `android-37.0` revision 2 was available on the stable SDK channel, while some documentation retains preview wording. [Android 17 SDK setup](https://developer.android.com/about/versions/17/setup-sdk)

Target-37 apps require Android 17's local-network permission for incoming LAN sockets. The app requests it on API 37 and later. Notification permission is requested on API 33 and later, and a user must tap Start again after granting permissions. API 34 and later use the `specialUse` foreground-service type with a declared purpose. [Local network permission](https://developer.android.com/privacy-and-security/local-network-permission), [foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types)

The network list is based on `ConnectivityManager.getAllNetworks()`, transport/capability observations and `Network` handles. Request cellular asks Android to expose an internet-capable cellular network; it cannot promise a second SIM or force a carrier to keep a route alive. Per-network DNS and socket binding preserve the user's choice. Wi-Fi and cellular public IPs can coincide or change, so distinct egress must be measured rather than inferred. [Android Network API](https://developer.android.com/reference/android/net/Network)

## Reproducible local build

Tools stay under ignored `android-gateway/.tools/`; scripts set process-local environment variables. No global PATH, system Java or SDK registration is required. The user explicitly accepted the Android SDK License Agreement before SDK package installation. Build scripts never accept new terms automatically.

| Tool | Pinned version | Download SHA-256 |
| --- | --- | --- |
| Microsoft OpenJDK | 21.0.12.1+1, Windows x64 | `192441a9d27da813bada974bb88b4cf64d37a9589ed37f204374d411ca5ce07f` |
| Android command-line tools | 15859902, Windows | `90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a` |
| Gradle | 9.6.0 | `bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01` |
| Android Gradle Plugin | 9.4.0, Google Maven | Resolved by Gradle |
| Android platform | `platforms;android-37.0`, revision 2 | Resolved by official SDK manager |
| Android build tools | 36.0.0 | Resolved by official SDK manager |
| Platform tools | 37.0.1 | Resolved by official SDK manager |

The Android Gradle Plugin release notes specify its Gradle/JDK/build-tool requirements. Java source and core tests compile for Java 8 language compatibility. [AGP 9.4](https://developer.android.com/build/releases/agp-9-4-0-release-notes), [Microsoft JDK downloads](https://learn.microsoft.com/en-us/java/openjdk/download), [Android command-line tools](https://developer.android.com/studio#command-tools)

From `C:\Users\astha\CompSetStudio`:

```powershell
& ./android-gateway/scripts/run-core-tests.ps1
& ./android-gateway/scripts/build-apk.ps1
```

Scripts accept explicit `-JdkRoot`, and the APK script also accepts `-SdkRoot` and `-GradleRoot`. The build assembles `android-gateway/app/build/outputs/apk/debug/app-debug.apk`, runs Android lint and prints the APK SHA-256. This is an internal debug-signed build; production release signing and store publication are separate work. The source has no third-party runtime dependencies. Downloaded build tools retain their own licenses.

The 2026-09-28 version **0.1.3 / code 4** build completed `assembleDebug` and `lintDebug` successfully. The APK is **917,387 bytes**, SHA-256 `249187863bb59fe39196431737b0ac73508f5b766c1c4b2e0215291bf1a2e88e`. Android `aapt2` confirms minimum 23 / target 37; `apksigner verify --verbose` verifies v1 and v2 signatures. Lint reports zero errors and seven `SetTextI18n` warnings for the initial English-only interface. Java/Gradle deprecation notices remain build-time warnings. The signer additionally notes that the generated `META-INF/com/android/build/gradle/app-metadata.properties` entry is outside JAR-signature coverage; the whole-APK v2 signature verifies. The local machine-readable record is `android-gateway/build/verification.json`.

## Verification and device checklist

The implementer core suite passes **181 assertions**, including 106 new DNS64 checks alongside strict authority/authentication/header parsing, address rejection, subnet checks, byte/session/connection limits and concurrent admission. The earlier independent reviewer ran **101 assertions**, including four simultaneous reverse streams, cancellation during numeric connect and zero socket creation for mixed public/private DNS. Reverting the reverse-worker fix made that regression fail. Original review evidence belongs in `handoff/reviews/024-android-core.md`; current device/TLS/DNS64 proof is recorded in `handoff/reviews/029-android-device-tls.md`.

The OnePlus 10R on Android 15 exposed an Android Keystore padding-authorization incompatibility in version 0.1.0. Version 0.1.1 introduced a new, exact-selected nonexportable key identity with the raw RSA authorizations required by Conscrypt. The old identity is preserved; upgrading from 0.1.0 requires exporting and pairing the new public certificate. Versions 0.1.2 and 0.1.3 retain that v2 identity and token. An independent reviewer verified TLS1.2, certificate-chain validation and the exact paired fingerprint on the physical phone at 12:27 UTC on 28 September; this was a handshake-only proof. The later diagnostic identified eight public IPv4 answers and eight prefix-matching DNS64 answers, motivating the bounded duplicate rule above.

At 12:49 UTC on 28 September, root installed 0.1.3 on the OnePlus 10R and completed one authenticated, certificate-verified HTTPS request through its observed Wi-Fi route to `https://httpbin.org/ip`. Both proxy and destination TLS verification passed; the single end-to-end sample was 1,785.86 ms. Root then used the visible Stop button while a newly verified TLS connection was open: the connection closed in less than four seconds. A separate check verified the foreground service was removed and the listener unreachable. The phone was left stopped. The final button-disabled UI assertion was interrupted because the app left the foreground; do not treat it as passed. Full attribution and timestamps are in review029.

At 13:13 UTC, root tested the user-selected cellular route while retaining Wi-Fi for the private desktop connection. The selected and running network handles agreed before and after the request; Android's matching capability record reported cellular, internet, validated and not VPN. One authenticated neutral probe failed: the app received eight public IPv4 and eight prefix-matching translated IPv6 answers but rejected the complete batch under its duplicate-only DNS64 rule. A later read of the same network's advertised prefix length showed /96. No successful cellular HTTP response or different public IP was established. Cellular use remains unsupported for this observed response; repeating requests or falling back to another route is not a repair.

The cellular session's visible Stop closed a separately verified TLS connection in 162.83 ms, removed the foreground service and made the listener unreachable. Its final button-disabled assertion was again unverified after the app left the foreground. The phone was left stopped. These remain separate teardown and end-to-end transport results, with evidence in review029.

Phone tests still required include the other intended OS versions; physical wrong-token, unpaired-client and private-destination rejection; successful cellular egress and a measured public-IP comparison after a reviewed compatibility repair; selected-network loss; notification Stop; app task removal; budget expiry; long sessions; and Stop during an authenticated active data transfer. No collector route was assigned by these neutral tests. Never publish tokens, private key material, local phone addresses or device identifiers as test artifacts. Core tests alone do not establish phone or carrier behavior.
