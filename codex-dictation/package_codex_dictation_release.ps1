param(
    [string]$PythonPath = "",
    [switch]$SkipBuild,
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptDir -Parent
$buildScript = Join-Path $scriptDir "build_codex_dictation_exe.ps1"
$exePath = Join-Path $scriptDir "dist\CodexDictation.exe"
$releaseRoot = Join-Path $scriptDir "release"
$packageName = "CodexDictation-win64"
$packageRoot = Join-Path $releaseRoot $packageName
$packageAppDir = Join-Path $packageRoot "codex-dictation"
$packageToolsDir = Join-Path $packageRoot "tools"
$packageZip = Join-Path $releaseRoot ($packageName + ".zip")
$autoHotkeyDir = Join-Path $repoRoot "tools\AutoHotkey"

if (-not $SkipBuild) {
    if ($PythonPath) {
        & $buildScript -PythonPath $PythonPath
    } else {
        & $buildScript
    }
    if ($LASTEXITCODE -ne 0) {
        throw "단일 실행 파일 빌드에 실패했습니다."
    }
}

if (-not (Test-Path $exePath)) {
    throw "릴리즈 패키지를 만들려면 먼저 실행 파일이 필요합니다: $exePath"
}

if (-not (Test-Path $autoHotkeyDir)) {
    throw "릴리즈 패키지를 만들려면 AutoHotkey 엔진이 필요합니다: $autoHotkeyDir"
}

if (Test-Path $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (-not (Test-Path $releaseRoot)) {
    New-Item -ItemType Directory -Path $releaseRoot | Out-Null
}

New-Item -ItemType Directory -Path (Join-Path $packageAppDir "dist") -Force | Out-Null
New-Item -ItemType Directory -Path $packageToolsDir -Force | Out-Null

Copy-Item -LiteralPath $exePath -Destination (Join-Path $packageAppDir "dist\CodexDictation.exe")

foreach ($relativePath in @(
    "README.md",
    "launch_codex_dictation.ahk",
    "run_codex_dictation.bat",
    "run_codex_hotkeys.bat"
)) {
    Copy-Item -LiteralPath (Join-Path $scriptDir $relativePath) -Destination (Join-Path $packageAppDir $relativePath)
}

Copy-Item -LiteralPath $autoHotkeyDir -Destination (Join-Path $packageToolsDir "AutoHotkey") -Recurse

if (Test-Path $packageZip) {
    Remove-Item -LiteralPath $packageZip -Force
}

if (-not $SkipZip) {
    Compress-Archive -Path $packageRoot -DestinationPath $packageZip -Force
}

Write-Host ""
Write-Host "릴리즈 패키지 준비 완료:"
Write-Host " - 폴더: $packageRoot"
if (-not $SkipZip) {
    Write-Host " - zip:   $packageZip"
}
