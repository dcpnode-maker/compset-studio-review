# ADR: Windows master and opt-in Android team nodes

Status: proposed implementation architecture; hosting decision accepted by user. Scope/profile: CompSet Gateway vNext, architecture and implementation planning under Order017. Date: 28 September 2026. This document is not a shipped APK or running master service.

## Product decision

The user's Windows laptop owns the controller and schedules work while online. Team members enroll their phones as visible, revocable nodes. Each phone advertises the Wi-Fi and cellular networks it can actually use, with a separately measured public egress identity for each. The master selects eligible routes for script sessions. An offline or sleeping laptop cannot coordinate or relay work; nodes wait and reconnect with backoff when it returns.

The desired maximum is Wi-Fi plus SIM1 plus SIM2, potentially more on future devices. Show two separate counts: simultaneously usable, independently probed routes, and distinct observed public exits. Two usable routes can share an exit. A dual-SIM label or several phones on the same router does not establish extra exits. IPv4 and IPv6 observations of one network are address-family measurements, not automatically two independent routes.

## Components and ownership

| Component | Responsibilities | Proposed technology |
| --- | --- | --- |
| Windows master | Device enrollment/revocation, route health, session leases, source cooldowns, scheduling, local client proxy, audit counters | Existing Python runtime, asyncio, SQLite, one owned process while open |
| Master panel | Nodes, active routes, verified distinct exits, latency/age, bytes, session ownership, pause/revoke and failure explanation | Reuse CompSet's lightweight JavaScript/CSS components; deployment remains separate from source work |
| Android node | Consent/enrollment, local identity, foreground lifetime, network discovery, per-network DNS and sockets, encrypted reverse connection, bounded streams, Stop | Native Java/API23 baseline; public Android APIs with version guards |
| Remote reachability adapter | Exposes only the authenticated node transport to the laptop when nodes are away from its LAN | Configurable encrypted endpoint or reviewed tunnel; provider choice and activation remain open |
| Collector adapter | Stable localhost HTTP CONNECT interface; explicit session ID maps to an eligible route lease | Extend the owned-device interface without silently modifying collector behavior |

Keep Python for orchestration and native Java for the phone. Both are handling network waits; measure CPU, memory, framing and throughput before introducing Go/Rust or JNI. No LLM runs on the phone or inside the packet path.

## Laptop reachability

Phone nodes initiate outbound connections; they do not need inbound mobile ports. Same-LAN master access can be proved first. Remote team phones require a stable, reachable endpoint leading to the online laptop; localhost alone is insufficient behind home NAT. Do not silently open a router port or publish the controller UI.

The node transport and the master UI are separate listeners/authorities. Enrollment binds the node to the master identity, not merely a tunnel URL. Prefer end-to-end TLS terminating on the master. A relay that terminates TLS requires an independently reviewed additional end-to-end authenticated encryption design before use; it must not receive device secrets or plaintext stream metadata by accident. The selected relay and its protocol support, stability, throughput, license and cost must be verified before claiming remote operation. No free relay is assumed unlimited or permanently available.

## Enrollment and control contract

1. The master displays a short-lived, single-use enrollment QR containing its endpoint, identity pin and enrollment nonce. It has no reusable operator or collector credential.
2. The phone displays who operates the master and which Wi-Fi/cellular resources it will share. The owner opts in and can pause, stop or revoke locally. A shared operational profile may request continuous operation but cannot override local withdrawal.
3. The node generates its own nonexportable key where Android Keystore supports it. Both sides prove possession and the master records the approved node public identity. Store master secrets using Windows account protection; never place them in URLs, process arguments, logs or exported handovers.
4. After enrollment, authenticated messages include protocol version, node ID, boot/session generation, request ID, sequence and deadline. Reject stale generations, duplicates with conflicting content, expired commands and revoked identities.
5. Commands are typed: advertise/update routes, open a stream on a specific route lease, close stream, pause and revoke. No shell command, arbitrary executable, contact/SMS access, file browsing or remote Android UI control is part of this protocol.

Keep node control and target traffic separate. A target stream carries opaque destination TLS, with normal certificate verification by the desktop client. CONNECT authentication and master/node transport authentication are distinct. The new protocol needs its own security review; existing same-LAN pairing proof does not establish reverse-tunnel correctness.

## Route identity and scheduler

Represent a route with node ID, node boot generation, ephemeral route ID, transport, device-local subscription binding if available, public capability flags, observation time, public address family/identity, probe outcome, health age, available concurrency and byte counters. Network handles and subscription identifiers are device-local and may change; never reuse an old route after reboot or network loss. Do not collect phone numbers, IMSI, IMEI or contacts to label SIM routes.

Route states: discovered -> probing -> healthy; healthy -> stale/offline/cooldown/paused; any state -> revoked. A failed probe cannot enter healthy. A new network generation or changed observed exit invalidates previous eligibility. Use monotonic deadlines within a running master; master restart invalidates prior leases rather than reusing stale monotonic values.

Schedule one explicit route for each session. Rank healthy routes by source eligibility, freshness, remaining concurrency, observed latency and fairness; round-robin is a selectable simple policy. Deduplicate measured public exits so two phones behind one router do not inflate pool size. Persist a session-to-route lease before opening its first connection. Retries inside that session retain its route; route loss pauses/fails it. A new session may select another eligible route. Source cooldowns apply across the pool where appropriate; a challenge or rate limit is not a trigger for automatic IP cycling.

The master exposes a localhost-only authenticated CONNECT endpoint to approved script processes. Do not expose an unauthenticated general proxy. Use bounded queues, frame sizes, per-stream windows and fair multiplexing so one download cannot exhaust the controller or starve every route. Resource ceilings are operator-visible/configurable; no invented battery-percentage cutoff is required. Permission and carrier availability remain device constraints.

## Network concurrency and Android lifetime

Bind DNS and every upstream socket to the selected Android `Network`. Do not bind the whole process, switch the default SIM or fall back to the default network. Control connectivity may stay on Wi-Fi while an individual destination stream uses cellular. Android documents network-specific DNS/socket binding in the [Network API](https://developer.android.com/reference/android/net/Network).

Subscription-specific requests must use public APIs available on the installed version. [TelephonyNetworkSpecifier.Builder](https://developer.android.com/reference/android/net/TelephonyNetworkSpecifier.Builder) is available from API30 (Android11). API23–29 have a documented legacy numeric subscription specifier in `NetworkRequest.Builder.setNetworkSpecifier(String)`, but that is a request, not a guarantee of nondefault-SIM internet. Enumerating active subscriptions requires the applicable `READ_PHONE_STATE` permission or carrier privilege; requesting connectivity needs `CHANGE_NETWORK_STATE`. Permission denial falls back to reporting networks already available, without inventing SIM bindings.

| Android/API | Capability plan | Claim permitted after testing |
| --- | --- | --- |
| 6–10 / 23–29 | Existing network-specific DNS/socket API; optional documented legacy subscription specifier | Only actually available/probed routes; no guaranteed multi-SIM concurrency |
| 11+ / 30+ | Public `TelephonyNetworkSpecifier.Builder` plus guarded NAT64 metadata | Subscription request success must be correlated to returned network capabilities and egress |
| 15+ / 35+ | Same supported request path | Do not substitute nonempty `setSubscriptionIds`: its privileged permission is unavailable to an ordinary team APK |
| Every supported release | Observe physical network callbacks and probe each route | Active modem/SIM counts are inventory, not proof of concurrent usable internet or distinct IPs |

Android's telephony implementation can reject unrestricted INTERNET requests for a non-preferred data subscription; [this AOSP PhoneSwitcher revision](https://android.googlesource.com/platform/frameworks/opt/telephony/+/9bd01f0d94448cef232cddc3b414a11efaf79358/src/java/com/android/internal/telephony/data/PhoneSwitcher.java#1526) documents that constraint. Vendor behavior and supported use cases may differ. Wi-Fi plus a cellular route is a valid design target; ordinary-app SIM1 plus SIM2 concurrent internet remains device-specific and unproved. No hidden/privileged API or default-SIM switching is a substitute for that proof.

Continuous mode means a visible foreground service with clear sharing state, bytes and Stop, plus reconnect/backoff while the owner keeps it enabled. It is the desired operating state, not a guarantee of uninterrupted availability: Android restrictions, Doze, OEM policies and user Stop can interrupt it, so master leases expire promptly when heartbeats stop. After user Force stop, permission withdrawal or local Stop, no hidden restart. Reboot/unlock recovery is an explicit owner setting using only permitted OS entry points. Android documents background foreground-service restrictions [here](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start). A declared `specialUse` type needs an appropriate use-case justification; it does not guarantee uptime. `dataSync` is not the choice for an indefinite relay given its [time limits](https://developer.android.com/develop/background-work/services/fgs/timeout). OEM behavior and long sessions need device tests; minimum SDK compatibility alone is insufficient.

API37/Android17 local master connections and LAN listeners need the applicable `ACCESS_LOCAL_NETWORK` permission in the target37 app, including a clear denied state; [Android local-network guidance](https://developer.android.com/privacy-and-security/local-network-permission) is the implementation reference. Keep this separate from subscription enumeration. Do not request phone-number or hardware-identifier permissions merely to label routes.

## DNS64 prerequisite from the current phone test

Version 0.1.3's Wi-Fi neutral HTTPS request passed. Its cellular test returned a /96 translated answer batch which the duplicate-only helper could not match completely to public native IPv4 answers. The batch was rejected before upstream traffic. This is a compatibility limitation; the evidence does not prove the unmatched embedded addresses were private.

A follow-up resolver design must retain same-network DNS, original response bounds, rejection of private/reserved destinations, protection against network-specific global translation prefixes, one selected connect with no hidden retries, and source authentication/TLS checks. Do not fix this by simply dropping arbitrary rejected answers. A typed, separately validated route result for supported NAT64 layouts is a candidate for review, not accepted implementation. Include unmatched but public translations, translated-private, malformed/unsupported prefixes, mixed answers, IPv6-only carriers and network-generation changes in independent proof. Repeat physical cellular and fresh Wi-Fi probes before claiming distinct exits.

## Staged build and acceptance

| Work package | Owner role | Independent evidence required |
| --- | --- | --- |
| Resolver compatibility repair | Android networking implementer | Adversarial resolver/tunnel proof plus one real cellular HTTPS result; no weakened destination/TLS policy |
| Capability discovery | Android implementer | API guards, permission-denied behavior, matched subscription/network observations; simultaneous Wi-Fi/SIM tests on each available OnePlus model |
| Master inventory and lease core | Python implementer | SQLite concurrency, stale-generation rejection, deduplication, fairness, source cooldown and restart tests |
| Enrollment and reverse transport | Transport implementer | Separate reviewer executes bad identity/replay/revocation, bounded memory, stream isolation, abrupt disconnect and TLS proof |
| Native lifecycle and team setup | Android implementer | Opt-in/Stop/revoke; screen-off, unplug, master sleep, app removal, reboot, permission changes and long-session measurements |
| Local master panel and collector adapter | Frontend/integration implementer | Actual master state, truthful route counts, single-session affinity and request accounting; no fake rates or route health |
| Remote team pilot | Root coordination plus independent reviewer | Two consenting phones on different networks, reachable master transport, measured exits, failed-node containment, no credential export |

Parallelize master core, capability discovery and transport design after the protocol contract is reviewed. One coordinator owns integration; reviewers never certify their own implementation. Do not migrate the existing UI framework for this work. Measure APK size, idle/active RAM and CPU, reconnect cost, battery/data use, first-route readiness and p50/p95 tunnel overhead. Use these measurements to choose concurrency rather than asserting “blazing fast.”

## Alternatives and remaining decisions

The current inbound same-LAN phone proxy is simplest and proven for Wi-Fi, but cannot serve arbitrary remote team phones. A node-initiated reverse transport is the preferred next architecture. A full-device VPN/overlay adds setup, a VPN-slot dependency and extra routing behavior; it is not the default for the requested single lightweight APK. A permanent cloud master would remain available while the laptop sleeps but conflicts with the user's selected laptop-only master.

Remaining decisions: the laptop's remote reachability adapter and endpoint, the reviewed reverse-transport library/protocol, and tested simultaneous subscription support. No additional hosting spend, public service, device enrollment or vNext APK installation has occurred. The original dashboard activation denial remains a separate delivery issue and is not worked around by this architecture.
