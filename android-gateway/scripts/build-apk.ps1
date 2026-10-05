param(
  [string]$JdkRoot = (Join-Path $PSScriptRoot '../.tools/jdk-21.0.12.1+1'),
  [string]$SdkRoot = (Join-Path $PSScriptRoot '../.tools/android-sdk'),
  [string]$GradleRoot = (Join-Path $PSScriptRoot '../.tools/gradle-9.6.0')
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (!(Test-Path (Join-Path $SdkRoot 'platforms/android-37.0/android.jar'))) { throw 'Install the approved official Android platform 37.0 first.' }
if (!(Test-Path (Join-Path $SdkRoot 'licenses/android-sdk-license'))) { throw 'Android SDK license acceptance is required; this script never accepts licenses.' }
$env:JAVA_HOME = (Resolve-Path $JdkRoot).Path
$env:ANDROID_SDK_ROOT = (Resolve-Path $SdkRoot).Path
& (Join-Path $GradleRoot 'bin/gradle.bat') --no-daemon --project-dir $ProjectRoot :app:assembleDebug :app:lintDebug
if ($LASTEXITCODE -ne 0) { throw 'Android build/lint failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'app/build/outputs/apk/debug/app-debug.apk')
