$ErrorActionPreference = "Stop"

function Find-PythonInAncestorVenv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StartDirectory
    )

    $current = (Resolve-Path $StartDirectory).Path
    while ($true) {
        $candidate = Join-Path $current ".venv\Scripts\python.exe"
        if (Test-Path $candidate) {
            return $candidate
        }

        $parent = Split-Path $current -Parent
        if (-not $parent -or $parent -eq $current) {
            break
        }
        $current = $parent
    }

    return $null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Find-PythonInAncestorVenv -StartDirectory $scriptDir

if (-not $python) {
    throw ".venv\Scripts\python.exe 를 찾지 못했습니다. 저장소 루트에서 가상환경을 먼저 준비해주세요."
}

$buildRequirements = Join-Path $scriptDir "requirements-dictation-build.txt"
$entryScript = Join-Path $scriptDir "codex_dictation.py"
$distDir = Join-Path $scriptDir "dist"
$workDir = Join-Path $scriptDir "build"

& $python -m pip install -r $buildRequirements
if ($LASTEXITCODE -ne 0) {
    throw "빌드 의존성 설치에 실패했습니다."
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name CodexDictation `
    --distpath $distDir `
    --workpath $workDir `
    --specpath $workDir `
    --collect-data faster_whisper `
    --hidden-import sounddevice `
    --hidden-import soundfile `
    --hidden-import keyboard `
    --hidden-import tkinter `
    --hidden-import tkinter.ttk `
    --hidden-import tkinter.messagebox `
    --exclude-module torch `
    --exclude-module torchaudio `
    --exclude-module torchvision `
    --exclude-module lightning `
    --exclude-module pytorch_lightning `
    --exclude-module tensorflow `
    --exclude-module jax `
    --exclude-module scipy `
    --exclude-module sklearn `
    --exclude-module matplotlib `
    --exclude-module numba `
    --exclude-module llvmlite `
    --exclude-module librosa `
    --exclude-module transformers `
    --exclude-module so_vits_svc_fork `
    $entryScript

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 빌드에 실패했습니다."
}

$exePath = Join-Path $distDir "CodexDictation.exe"
if (-not (Test-Path $exePath)) {
    throw "빌드는 끝났지만 실행 파일이 생성되지 않았습니다: $exePath"
}

Write-Host ""
Write-Host "빌드 완료: $exePath"
