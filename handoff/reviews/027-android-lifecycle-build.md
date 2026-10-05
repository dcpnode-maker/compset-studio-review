# Independent Android lifecycle and build review

Reviewer: root; implementer: workspace_ui. Date: 2026-09-28. Scope: native Activity, foreground Service, manifest and backup exclusions. Android core transport and desktop TLS have separate independent reports.

Root found a startup/teardown race: after the initial ending check, a worker could acquire callbacks or a wake lock after onDestroy had already cleaned up. The implementer serialized resource acquisition and teardown under one lifecycle lock, retained ending/generation guards, and checks ending again before server start. Root inspected the final correction, Stop paths, background notification behavior, API guards, network loss handling, per-install key handling, token visibility and backup exclusions.

Accepted for local source/build integration. This is not device-runtime acceptance. No phone app was installed or started: the user took the phone away and asked to prioritize dashboards. The earlier read-only ADB check confirmed the connected OnePlus10R reports Android15/API35; it does not prove gateway operation.

Root personally executed `android-gateway/scripts/build-apk.ps1` from the CompSetStudio directory. Result: `assembleDebug` and `lintDebug`, BUILD SUCCESSFUL in18s, exit0. The build retained seven English localization warnings and no lint errors; a Gradle option deprecation does not prevent the pinned build. SDK terms had been explicitly accepted by the user before installation.

| Artifact | SHA256 |
| --- | --- |
| MainActivity.java | 305ab07031593fa440b670eba771daae85689919c91327f91605477889209c58 |
| GatewayService.java | c0db4a1ae9d49b47f2024110626fedf989d0054b5cc229b6cc86a5b3ba76b06f |
| AndroidManifest.xml | 9867121fbf0878b701aa00b378eeaf650720da22fe0b4c8f8372195d6d7f42a9 |
| data_extraction_rules.xml | cb029b35db0e976c087100424e16e14a6256b46962398887520e51508c3b5842 |
| app/build/outputs/apk/debug/app-debug.apk | 2f83e6dd6be0fed7d97768bccc540134ea9a9298b881d904dc922357753ae909 |

Remaining physical proof: AndroidKeyStore TLS handshake from the desktop, certificate export/pairing, visible Stop, app backgrounding and network loss, actual cellular egress, and older-device compatibility. One APK with minSdk23 and no native ABI dependency is a compatibility target, not universal device proof. This is an internal debug-signed APK, not a release-signing or store-publication approval.
