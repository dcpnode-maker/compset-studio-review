param([string]$JdkRoot = (Join-Path $PSScriptRoot '../.tools/jdk-21.0.12.1+1'))
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$OutputPath = Join-Path $ProjectRoot 'build/core-tests'
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
$Sources = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'app/src/main/java/com/compset/gateway/core') -Filter '*.java' | ForEach-Object FullName)
$Sources += @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tests') -Filter '*.java' | ForEach-Object FullName)
& (Join-Path $JdkRoot 'bin/javac.exe') --release 8 -Xlint:all -d $OutputPath @Sources
if ($LASTEXITCODE -ne 0) { throw 'Core Java compilation failed' }
& (Join-Path $JdkRoot 'bin/java.exe') -ea -cp $OutputPath com.compset.gateway.core.CoreTests
if ($LASTEXITCODE -ne 0) { throw 'Core Java proof failed' }
