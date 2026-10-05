# Independent review: Android gateway core, pairing and routing

Reviewer: `/root/workspace_data`, 28 September 2026. Implementer: `/root/workspace_ui`.

Scope: the four pure-Java classes in `android-gateway/app/src/main/java/com/compset/gateway/core/`, plus source inspection of `Pairing.java` and `Networks.java`. Root separately reviews Android activity/service lifecycle; `/root/ota_review` separately reviews the desktop owned-device client and its TLS pinning. This report does not accept those other surfaces or claim a successful phone connection.

Result: the frozen core is accepted for local integration after the findings below were corrected. The reviewer personally compiled and executed both the implementer's core tests and additional independent transport/resource tests. No phone action, external target request or persistent listener was performed. The transport tests use fake SSL sockets, so they prove parser, concurrency, cancellation and routing decisions—not real TLS handshakes, Android Keystore behavior, selected-network egress or device compatibility. APK build/lint and phone proof remain separate acceptance steps.

## Findings and corrections

1. **Reverse-pump starvation at four concurrent tunnels.** The original core used the same four-thread executor for `serve()` and the reverse-direction copy task submitted by each `serve()`. With four admitted tunnels, every worker could be occupied reading the forward direction while all reverse pumps remained queued. The default app admitted two tunnels, so this was a defect in the core's permitted four-tunnel setting rather than its initial app default. The implementer added a separate bounded reverse executor. The reviewer fixture forces all four numeric connects to rendezvous, then verifies all four clients receive upstream bytes. A temporary copy reverting only `reverse.submit` to `workers.submit` failed this regression as expected; the implementation file was not modified for that mutation.

2. **Owned-device health-probe mismatch.** The desktop helper uses `https://httpbin.org/ip`, while the original Android destination policy omitted `httpbin.org`. Every otherwise valid probe would therefore receive a 403. The implementer added the exact echo hostname. Both test sets now accept `httpbin.org:443` and reject arbitrary subdomains such as `sub.httpbin.org:443`.

During correction, the implementer also moved numeric connection establishment into the core. `Route.socket()` supplies an unconnected socket bound to the selected Android network; the core registers it before connecting to the already-reviewed numeric DNS result. An independent regression verifies Stop closes a socket while its connect is pending and releases admission. Another verifies a mixed public/private DNS answer is rejected before any destination socket is created.

## Personally executed proof

From `C:\Users\astha\CompSetStudio`:

```powershell
& ./android-gateway/scripts/run-core-tests.ps1
```

Result: **75 assertions passed**. Java compiles for release 8 using the local JDK 21 toolchain. Only obsolete source/target 8 option warnings and a missing `serialVersionUID` lint warning were emitted.

```powershell
$reviewClasses = 'data/android-review-classes'
$coreSources = Get-ChildItem android-gateway/app/src/main/java/com/compset/gateway/core/*.java | Select-Object -ExpandProperty FullName
& android-gateway/.tools/jdk-21.0.12.1+1/bin/javac.exe --release 8 -Xlint:all -d $reviewClasses $coreSources tests/android/GatewayReviewerProof.java
& android-gateway/.tools/jdk-21.0.12.1+1/bin/java.exe -cp $reviewClasses GatewayReviewerProof
```

Result: **101 independent assertions passed**. Coverage includes wrong/duplicate authentication, «REDACTED-SECRET» Host, content-length and transfer-encoding rejection, header byte limits, strict destination authority boundaries, preservation of tunneled bytes after CONNECT headers, private/special/mixed DNS rejection, DNS cardinality bounds, explicit private IPv4 pairing, subnet checks, atomic session accounting, byte/deadline limits, invalid upper bounds and overflow, eight-auth-failure stop, four-tunnel reverse progress, Stop during numeric connect and socket cleanup.

The same reviewer fixture compiled against a temporary mutation under ignored `data/android-review-mutation/` failed with `All four admitted tunnels receive upstream bytes without reverse-pump starvation`, confirming sensitivity to the corrected concurrency defect.

## Source inspection and limits

Authentication uses a random 128-bit token and constant-time comparison of the expected Basic authorization bytes after the TLS handshake. The phone keeps its private key in Android Keystore and exports only the public certificate and SHA-256 fingerprint. The certificate identifies this explicitly paired installation; ordinary IP-hostname validation is not its identity mechanism. The desktop's exact certificate pin, token-before-TLS ordering and target certificate verification are covered by the separate desktop-client review.

The listener constructor rejects wildcard/public addresses and restricts accepted connections to the paired private IPv4. Destination resolution is performed on the explicitly selected Android `Network`; every returned address must pass the public-address policy. The core connects one checked numeric address on port 443 without a second hostname resolution or alternate-route retry. The phone copies opaque tunnel bytes and does not install a CA or decrypt destination TLS.

Core limits remain finite: at most 24 hours, 16 GiB aggregate traffic, 10,000 tunnel admissions and 4 concurrent tunnels; app policy may select lower limits. DNS waits are bounded with a bounded executor, established tunnels have a 120-second deadline and 20-second read timeout, and a monotonic session timer stops the listener and registered sockets. The retained request-byte cap and finite session also bound unfinished authentication/header work. No claim is made that thread interruption alone cancels Android's DNS implementation.

The certificate currently has a one-year validity interval. Renewing/re-pairing after expiry is an operational requirement, not a tested automatic feature. Network availability, simultaneous Wi-Fi and cellular operation, device Keystore support and successful distinct carrier egress require physical-device proof.

## Frozen SHA-256

| File | SHA-256 |
| --- | --- |
| `core/ConnectRequest.java` | `d08a736d9f6b17a67e1b2bd111015ef8e9d043cc5921941c9675abfe734c4cc8` |
| `core/DestinationPolicy.java` | `c3e9bb9499c34e0466d4d5bf9138ed683eb4cf42703d296270c9c266f1e087b2` |
| `core/SessionBudget.java` | `38770083cf40d4dbbe87109c1c9bab32748b6b835044582f07f9f3afba6d8fb6` |
| `core/TunnelServer.java` | `97643be0f2bfe5d598817042d43ab8a03498a6da4752e481beb5f0fee50fc76a` |
| `Pairing.java` | `e1cd32d6a255aebed98c47e9f363c42f7511cb0a105f08c34c704a2581a970cc` |
| `Networks.java` | `0cb177a67d4b90549145ce2e97cfe37e8db0a7a21e488177c750cd25205c64f8` |
| `android-gateway/tests/CoreTests.java` | `a3ecf505a56fc9e924b57826779a6a30ba52f0d290358b411320def5f24d1df4` |
| `android-gateway/scripts/run-core-tests.ps1` | `e22419da5fbd88903243623a23a1c4bbfacb0ed8f8a0cbf36d0415c4a1a17090` |
| `tests/android/GatewayReviewerProof.java` | `8193eb48655460e5eec4baa37738115eac73ea2fe403ec9e17405bd90b8377cb` |

Java implementation paths above are relative to `android-gateway/app/src/main/java/com/compset/gateway/`. Any subsequent lint/build correction touching these files must be re-reviewed before using this acceptance for a different version.

## Watchdog amendment re-review

The implementer changed only the watchdog scheduling call from `scheduleAtFixedRate` to `scheduleWithFixedDelay` after Android lint identified cached-process catch-up risk. The reviewer inspected that change and personally recompiled/re-executed the independent proof: **101 assertions passed**. The `TunnelServer.java` hash above is the amended accepted version. Pairing, network-selection and other core implementation hashes were unchanged. No device action was needed for this bounded scheduling correction.
