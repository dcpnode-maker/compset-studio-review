# Independent review: Android device TLS key authorization

Reviewer: `/root/ota_review`, 28 September 2026. Implementer and physical-device operator: `/root`. Scope: the Order015 correction to `Pairing.java` and the application version bump to 0.1.1 / code 2. The reviewer did not implement these changes or operate the phone.

## Result and limits

Accepted for the next coordinated, certificate-verified physical handshake. Independent source inspection, compiled key-manager behavior, existing core/transport proof, and the APK build/lint passed. This is not yet acceptance of an actual Android Keystore handshake, carrier egress, physical Stop behavior or continuous operation. The earlier desktop TLS socket-pair tests and pure-Java fake-socket tests cannot establish those device facts.

Root reported the original device logs: Conscrypt's private RSA operation failed with AndroidKeyStore `INCOMPATIBLE_PADDING_MODE`, internal code -11, during `startHandshake`. Two connections had been admitted and zero tunnel bytes transferred. This attributed evidence supports key-authorization failure; the reviewer did not independently collect those phone logs.

## Diagnosis and inspected correction

The old generation profile allowed only PKCS1 encryption padding and SHA256/SHA512 digests. Conscrypt's delegated RSA signing path can request `RSA/ECB/NoPadding`. Android15 translates a private-key cipher encryption operation into signing and supplies `DIGEST_NONE`. Consequently the corrected profile authorizes both `ENCRYPTION_PADDING_NONE` and `DIGEST_NONE`, while retaining the prior purposes, PKCS1 signature padding and SHA256/SHA512. This changes the permitted private-key primitive; it does not remove TLS hashing, certificate validation or application authentication.

Primary references inspected:

- [Android KeyGenParameterSpec.Builder](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder): TLS digest/padding guidance.
- [Conscrypt CryptoUpcalls](https://raw.githubusercontent.com/google/conscrypt/master/common/src/main/java/org/conscrypt/CryptoUpcalls.java): delegated RSA cipher/signing operation.
- [Android15 AndroidKeyStoreRSACipherSpi](https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android15-release/keystore/java/android/security/keystore2/AndroidKeyStoreRSACipherSpi.java): raw private-key signing purpose and NONE digest.
- [Android Keystore authorization](https://developer.android.com/privacy-and-security/keystore#key-use-authorizations): authorizations cannot be edited after key generation.

The new alias is `compset-gateway-v2-tls`. No old alias is deleted or overwritten. Existing installations create a distinct identity when the corrected profile is first requested and require explicit desktop re-pairing with its newly exported public certificate/fingerprint. Merely updating the builder could not repair the previously generated key. The authentication token is not rotated by this patch. No token or private-key bytes are logged, exported or included in this review.

The key manager captures only the exact new alias's private-key handle and certificate chain. It returns the alias only for RSA server requests, refuses all client aliases and all other alias lookups, and returns cloned certificate-chain arrays. Thus retaining an old keystore entry cannot cause selection of its certificate. Private key material remains in Android Keystore. The listener retains TLS1.2 and the existing paired-client admission, authentication, destination, network and resource rules.

Using baseline `X509KeyManager` is valid for this socket path. [ConscryptEngine](https://raw.githubusercontent.com/google/conscrypt/master/common/src/main/java/org/conscrypt/ConscryptEngine.java) explicitly calls its `chooseServerAlias` fallback when the manager does not implement `X509ExtendedKeyManager`; the supplied socket can be null and this implementation does not depend on it. [X509ExtendedKeyManager](https://developer.android.com/reference/javax/net/ssl/X509ExtendedKeyManager) is documented from API1, so minSDK23 itself would not prohibit the extended class, but changing to it is unnecessary for this fix. These are source/API compatibility findings, not a test of every Android vendor TLS implementation.

## Personally executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

1. `& ./android-gateway/scripts/run-core-tests.ps1`: **75 assertions passed**, Java release8 compilation. Only the existing obsolete source/target8 and missing `serialVersionUID` warnings.
2. Compiled the current four core classes and `tests/android/GatewayReviewerProof.java` using local JDK21 `javac --release 8 -Xlint:all` into ignored `data/android-device-tls-review-classes`, then executed `GatewayReviewerProof`: **101 independent assertions passed**. This covers authentication, «REDACTED-SECRET» boundaries, byte/session/concurrency limits, reverse progress and socket cleanup with fake SSL sockets.
3. `& ./android-gateway/scripts/build-apk.ps1`: **BUILD SUCCESSFUL in 17s**; an independent incremental build invocation, 43 tasks with 42 up-to-date. Lint reported **0 errors, 7 existing localization warnings**. This script neither installs nor operates the phone.
4. Executed a JDK JShell probe against the actual compiled `com.compset.gateway.Pairing$1` class from `app/build/intermediates/javac/debug/compileDebugJavaWithJavac/classes`. Reflection supplied a dummy nonexportable RSA `PrivateKey` and certificate-array fixture directly to that anonymous manager constructor. **15 checks passed**: exact RSA server alias/list, refusal of EC/null key types, both client methods null, exact private-key identity, old/null alias rejection, and distinct cloned chain arrays. The probe did not invoke `Pairing.store`, generate a key, inspect a real token or perform any network operation. It validates compiled selection behavior only, not cryptographic execution.

The resulting APK SHA256 exactly matches the implementer's frozen artifact:

`ebe48b861ec27e97e1581cdec94737c49cd021991b558f2ca92dd701a0d59491`

## Frozen source SHA256

| File | SHA256 |
| --- | --- |
| `android-gateway/app/src/main/java/com/compset/gateway/Pairing.java` | `ad9454f821d5025c53d963c3684f266f2deee0ce53a33085f9c8fd8a3ffb7785` |
| `android-gateway/app/build.gradle` | `13edd5228ec5e31c11d2565a2441987d7ca65dcf38249a3ce292fe44fc3f6886` |
| `android-gateway/app/src/main/java/com/compset/gateway/GatewayService.java` | `c0db4a1ae9d49b47f2024110626fedf989d0054b5cc229b6cc86a5b3ba76b06f` |
| `android-gateway/app/src/main/java/com/compset/gateway/core/TunnelServer.java` | `97643be0f2bfe5d598817042d43ab8a03498a6da4752e481beb5f0fee50fc76a` |

## Remaining physical acceptance

The corrected APK must serve the newly exported certificate under successful desktop verification. A coordinated reviewer handshake can verify certificate trust and exact fingerprint before any authentication data is sent. Root separately owns authenticated fixed-neutral-target probing, selected-network evidence and visible Stop verification. Until those results are appended with their actual executor and limits, they remain unverified. No accommodation scraping or collector-route activation is accepted by this report.

## Independently executed physical TLS proof

At **2026-09-28T12:27:24.640183+00:00**, root provided an explicit single-handshake window with the updated gateway active. The reviewer made exactly **one** direct private-LAN connection from the paired desktop and closed it after TLS verification. No ADB/phone action, authentication header, token access or HTTP request was performed.

The Python standard-library client used `SSLContext(PROTOCOL_TLS_CLIENT)`, `CERT_REQUIRED`, and both minimum and maximum protocol set to TLS1.2. It loaded only the newly exported public certificate, first checked its SHA256 and DER against the registered pairing, and compared the served certificate's SHA256 with that same expected pin after the successful verified handshake. DNS/IP hostname matching was disabled because the explicit paired certificate fingerprint is this private listener's identity; certificate-chain verification remained mandatory. No endpoint address, certificate fingerprint or serial, or credential was printed or stored in this report.

Result: **verified TLSv1.2**, cipher **ECDHE-RSA-AES128-GCM-SHA256**, certificate-chain validation **passed**, exact paired fingerprint **passed**. Authentication sent: **false**. HTTP sent: **false**. The connection was closed and the device window returned to root without retry.

This proves the corrected nonexportable Android Keystore identity can complete the actual TLS handshake on the tested Android15 device, superseding the pending-handshake limitation above. It does not establish authenticated CONNECT, target TLS, neutral HTTP egress, cellular route choice or Stop behavior. Root reported a separate neutral-probe failure; that remains a distinct downstream diagnosis and is not promoted to successful egress by this certificate-only proof.

## 0.1.2 DNS diagnostic amendment

The reviewer independently inspected the subsequent diagnostic-only `GatewayService.java` change and version bump to 0.1.2 / code3. The existing `Route.resolve` performs exactly one selected-network `getAllByName` call, optionally reports classification for the fixed `httpbin.org` neutral target, and returns the same answers array without filtering, reordering or another lookup. The destination policy, authentication, TLS settings and v2 pairing identity are unchanged.

The fixed log contains counts and booleans only: answer/null counts, accepted/rejected IPv4/IPv6 counts under the existing policy, cardinality-limit result, `all_public`, and NAT64-prefix presence/match count. There is no raw address, prefix, hostname variable, request, credential or exception-message output. Diagnostic runtime failures produce only `diagnostic_unavailable`, preserving the resolver result. A missing prefix observation is not proof that a network does not use any form of address translation.

`LinkProperties.getNat64Prefix()` is guarded by `SDK_INT >= 30`, as required by its [Android API declaration](https://developer.android.com/reference/android/net/LinkProperties#getNat64Prefix()). `IpPrefix.contains()` is available from [API23](https://developer.android.com/reference/android/net/IpPrefix#contains(java.net.InetAddress)), matching minSDK23; it is only invoked for a non-null prefix and non-null address.

The reviewer personally ran `& ./android-gateway/scripts/build-apk.ps1` again after this source freeze: **BUILD SUCCESSFUL in 17s**, incremental 43 tasks / 42 up-to-date, **0 lint errors / 7 existing localization warnings**. No phone, ADB, DNS or connection action was performed in this amendment review. The unchanged core tests were not redundantly rerun. The diagnostic source and build are accepted; no 0.1.2 neutral-egress result is asserted here. The independently executed physical TLS proof above remains specifically the 0.1.1 test with the unchanged v2 identity.

| 0.1.2 artifact | SHA256 |
| --- | --- |
| `GatewayService.java` | `bced5a66bd159d69426968aeb37d8cb23cfe37708b04f3af0dd25e536e360a3a` |
| `app/build.gradle` | `8a31073b05875e5cb8279ef97321a254643ab8420cb6047ef0e789747fdd72be` |
| `Pairing.java` (unchanged) | `ad9454f821d5025c53d963c3684f266f2deee0ce53a33085f9c8fd8a3ffb7785` |
| `app-debug.apk` | `6b0df9a7e87e775537e7b66fbdfbf4f490ba9551af821d396d519c694218901e` |

## 0.1.3 conservative DNS64 duplicate handling

Implementer: `/root/workspace_ui`. Independent reviewer: `/root/ota_review`. The reviewer inspected the frozen `Nat64Duplicates.java`, its service integration and Order015 scope, and wrote the separate `tests/android/Nat64ReviewerProof.java`. No implementation file was edited by the reviewer.

**Source and executable security proof accepted.** The helper only removes a /96 translation that matches the selected network's advertised prefix and embeds a public native IPv4 address actually present in the same original answer array. The original nonempty/16-answer/null-member bounds apply before removal. Advertised-prefix classification precedes generic public-IPv6 classification; an unmatched or unsupported translated answer returns null, which the existing tunnel policy rejects. This prevents a network-specific global-unicast prefix from hiding a private or unmatched embedded destination. Other rejected addresses remain fatal to the complete batch. Accepted results retain the original native objects and order; no address is synthesized and no fallback is added.

`GatewayService` performs one lookup on the selected Android `Network`, reads that same network's advertised prefix once under the API30 guard, and passes it to the pure helper and count-only diagnostic. It returns the helper result to the unchanged `DestinationPolicy.allPublic` gate. An exception while obtaining network metadata becomes the existing bounded DNS failure, rather than permission to retry with an unverified route. Pairing, certificate checks and CONNECT authentication remain unchanged. Without a usable matching public A record, translated-only answers remain unsupported. Unsupported advertised prefix lengths reject matching IPv6 answers; ordinary native answers outside that prefix still undergo the normal policy.

The format used for /96 extraction is supported by [RFC6052 sections2.2–2.3](https://www.rfc-editor.org/rfc/rfc6052): the embedded IPv4 occupies the last32 bits. This is duplicate removal of addresses already returned by the same resolution, not a general NAT64 authorization.

Personally executed from the repository root:

```powershell
& ./android-gateway/scripts/run-core-tests.ps1
$reviewClasses = Join-Path (Get-Location) 'data/android-nat64-review-classes'
New-Item -ItemType Directory -Force -Path $reviewClasses | Out-Null
$coreSources = @(Get-ChildItem -LiteralPath 'android-gateway/app/src/main/java/com/compset/gateway/core' -Filter '*.java' | ForEach-Object FullName)
& ./android-gateway/.tools/jdk-21.0.12.1+1/bin/javac.exe --release 8 -Xlint:all -d $reviewClasses @coreSources tests/android/GatewayReviewerProof.java tests/android/Nat64ReviewerProof.java
& ./android-gateway/.tools/jdk-21.0.12.1+1/bin/java.exe -ea -cp $reviewClasses Nat64ReviewerProof
& ./android-gateway/.tools/jdk-21.0.12.1+1/bin/java.exe -ea -cp $reviewClasses GatewayReviewerProof
```

Results: **181 core assertions passed; 456 independent DNS64 checks passed; 101 existing independent gateway assertions passed**. The DNS64 proof includes32 deterministic permutations of the observed eight-A/eight-translated-answer shape, original ordering/object retention and no-input-mutation checks, cardinality before collapse, missing/malformed prefixes, missing native matches, private/special/null contamination, global-unicast translated-private and unmatched cases, and unsupported-prefix rejection.

Six fake `TunnelServer` cases exercise the actual policy gate: a valid duplicate allows exactly one resolution and one numeric upstream connection; private contamination, translated-private/global-prefix, unmatched/global-prefix, unsupported/global-prefix and null contamination each return403 with exactly one resolution and **zero upstream sockets**. Fake SSL sockets are used; these checks perform no DNS, phone, ADB or network operations and do not establish physical egress. The prior core concurrency and cleanup proof also remains green.

The reviewer also personally executed `& ./android-gateway/scripts/build-apk.ps1`: **BUILD SUCCESSFUL in55s**,43 tasks/5 executed/38 up-to-date, **0 lint errors and7 existing localization warnings**. The resulting APK hash matches the frozen implementer artifact below. Physical operation of0.1.3 belongs to root's coordinated device window; this review does not claim that result in advance.

| 0.1.3 artifact | SHA256 |
| --- | --- |
| `core/Nat64Duplicates.java` | `9113681dac23ec809a45485e9b2e7789691fc50521073e8ff79b8b6d8b070fc0` |
| `GatewayService.java` | `fd75a18d1ebc4a7921670ae18fb4dd973057bf86f9eaa17cb7a25bf53400c2dd` |
| `Pairing.java` (unchanged) | `ad9454f821d5025c53d963c3684f266f2deee0ce53a33085f9c8fd8a3ffb7785` |
| `app/build.gradle` | `f4cf5241b81ed0f3c7361c6404343052d521ae74cfe248b74f20785a473e8c4a` |
| `android-gateway/tests/Nat64DuplicateTests.java` | `06ed132d4cd29c9be641dec5c77b82630e859f542356be5e13bbc1e1617e8115` |
| `tests/android/Nat64ReviewerProof.java` | `10efe6c6ecbb59d4073666ddaf5b6a1114b90fbda64bc51807926c0443b79caa` |
| `app-debug.apk` | `249187863bb59fe39196431737b0ac73508f5b766c1c4b2e0215291bf1a2e88e` |

## Attributed cellular follow-up and independent record audit

Physical operator: `/root`, with the user's explicit cellular-test authorization. Read-only auditor: `/root/ota_review`. The auditor inspected `data/device-qa/phone_cellular.py`, the delegated probe call in `phone_probe.py`, the current `OwnedDevices.probe` implementation, and the sanitized records in `data/device-qa/outcomes.json`. The auditor did not execute these device scripts, use ADB, send a probe, or modify source during this follow-up.

The procedure correlates the UI's selected network handle with the running gateway handle and one matching Android connectivity record, requires CELLULAR/INTERNET/VALIDATED/NOT_VPN capabilities, checks foreground-service presence and unchanged private Wi-Fi ingress, and checks the running handle again after the probe. The delegated helper makes one `OwnedDevices.probe` call. That method retains required proxy certificate verification/pinning, verified target TLS, fixed `https://httpbin.org/ip`, disabled retries/redirects and bounded timeouts. It records a healthy public origin only after a successful valid response; its general failure label alone does not identify the failing transport stage.

The recorded attempt at **2026-09-28T13:13:35.790975+00:00 failed**, with `connection_or_tls_failed`. The selected cellular capabilities and running-handle consistency checks passed; Wi-Fi ingress remained unchanged. The comparison with the earlier Wi-Fi sample at12:49:18.335018+00:00 is explicitly **not_available**. No successful cellular origin was collected, so no same/different-egress claim is supported.

Root supplied the app-process diagnostic for this attempt:16 answers,0 nulls,8 policy-public IPv4,0 policy-public IPv6,0 rejected IPv4,8 rejected IPv6, original cardinality within limit, advertised NAT64 prefix present,8 prefix matches, and0 accepted native results. Root then read only the prefix length from the uniquely selected network record: **/96**. The raw prefix and embedded addresses were not collected into this review. Android `IpPrefix` supplies canonical prefix bytes.

Given those attributed observations and the independently inspected helper, at least one translated answer lacked an identical public native IPv4 answer in the same original response, so the helper rejected the entire batch. Prefix membership alone did not establish duplicate equivalence. This does **not** establish that the embedded target was private or otherwise unsafe; its exact value was not observed here. The current conservative duplicate-only compatibility rule therefore did not support this cellular DNS response. The rejected batch is not evidence of successful upstream connectivity or of a general carrier outage. No policy exception or source correction was made during this test.

Root's final Stop record at **2026-09-28T13:15:31.709627+00:00** reports that a verified open TLS connection closed in **162.83ms**, the listener became unreachable and the foreground service was removed. No authentication or HTTP was sent on that Stop-test connection. `network_teardown_passed` is true, but the overall record's `passed` is false because the final disabled-Stop-button UI assertion could not be observed after the app left the foreground. That UI assertion remains unverified, rather than being treated as a passed test. The phone was left stopped.

Conclusion of this audit: cellular selection and bounded network teardown have attributed procedural evidence; **cellular end-to-end egress and distinct egress remain unproved**. The current cellular route must not be presented as successfully usable from this attempt. The earlier Wi-Fi neutral request and independently verified phone TLS results retain their separate scope.

## Root-operated physical follow-up, 0.1.3

Executor: `/root`; this section is attributed physical evidence, not a claim that the independent reviewer operated the phone. After the user's explicit readiness reply, root stopped the prior foreground session through its visible button, installed the reviewed APK using `adb install -r`, and launched the gateway activity. Android reported a successful install and cold launch. The observed outbound selector was **Wi-Fi, validated**. No default SIM, system Wi-Fi or carrier setting was changed. The paired v2 certificate and token were preserved by the update.

At **2026-09-28T12:49:18.335018+00:00**, root's standard `OwnedDevices.probe` made one authenticated CONNECT request and HTTPS GET to the fixed neutral endpoint `https://httpbin.org/ip`. The helper obtained the pairing token only in memory from our app's revealed details, checked its displayed fingerprint against the existing local registration, hid those details, and started the foreground gateway. The probe returned **healthy**, a valid public echo address, **1,785.86 ms** end-to-end elapsed time, `proxy_tls_verified=true`, and `target_tls_verified=true`. No redirects, retries, alternate targets, accommodation requests or collector assignments were used. This is one Wi-Fi sample, not a speed benchmark or evidence of cellular routing. The echo address, phone/desktop addresses, token, device ID and certificate fingerprint are not included here.

For Stop, root first located an enabled **Stop gateway** button in our app's current UI hierarchy. A new TLS1.2 socket completed certificate-chain and exact-pin verification; it sent no authentication or HTTP. Root tapped that observed button. The script passed its assertion that this active TLS socket closed in **less than four seconds**, before the ten-second CONNECT-header timeout. The subsequent button-disabled UI assertion could not run because the app was no longer foreground. That UI assertion remains unverified, and the interrupted script did not retain a precise elapsed value.

A separate read-only check at **12:50:39.860465 UTC** verified installed version **0.1.3 / code4**, absence of the app's foreground service, and that a new connection to its listener was unsuccessful. The phone was left **stopped**. These observations prove active verified-TLS closure and service/listener teardown for this test. They do not prove a mid-transfer authenticated tunnel, notification-button behavior, task-removal behavior, selected-network loss, budget expiry or a long-running session. At that checkpoint, cellular egress, distinct carrier IPs, dual-SIM availability and all other Android versions had not been tested; the attributed cellular follow-up above records the later failed attempt.

Sanitized local outcomes are in ignored `data/device-qa/outcomes.json`; the helper scripts and pairing registry remain local. These records contain historical failures as well as the new success. A successful neutral probe does not authorize accommodation collection or make an idle phone a currently running route.
