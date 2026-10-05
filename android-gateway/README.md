# CompSet Gateway

A small native Java Android app that exposes an encrypted CONNECT gateway to one explicitly paired desktop on the same private Wi-Fi subnet. The user chooses an Android-exposed Wi-Fi or cellular network, session limits and Start. Stop is available in the app and foreground notification.

There are no runtime libraries, native binaries, WebView, analytics, remote configuration, boot receiver or automatic network fallback. One APK packages Java bytecode for supported Android device architectures.

See [the complete setup, security and compatibility notes](../docs/android-gateway.md). Device and cellular-egress verification are separate from a successful APK build.

From the repository root, with the documented local official toolchain installed:

```powershell
& ./android-gateway/scripts/run-core-tests.ps1
& ./android-gateway/scripts/build-apk.ps1
```

The build script assembles the internal debug APK and runs Android lint. It does not install onto a phone, start a service, accept SDK licenses or configure any collector route. Toolchains and generated APKs are ignored by Git.

This directory's original source is licensed under MIT; see [LICENSE](LICENSE). Downloaded Android/JDK/Gradle tools retain their own licenses.
