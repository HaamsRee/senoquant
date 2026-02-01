$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envDir = Join-Path $scriptDir "env"

if (!(Test-Path $envDir)) {
    Write-Error "Environment not found: $envDir"
    exit 1
}

$pythonExe = Join-Path $envDir "python.exe"
if (!(Test-Path $pythonExe)) {
    $pythonExe = Join-Path $envDir "Scripts\python.exe"
}

if (!(Test-Path $pythonExe)) {
    Write-Error "Python not found in environment: $envDir"
    exit 1
}

try {
    & $pythonExe -c "import napari" | Out-Null
} catch {
    $postInstall = Join-Path $scriptDir "post_install.ps1"
    if (Test-Path $postInstall) {
        Write-Host "[SenoQuant] Running post-install setup..."
        & powershell -ExecutionPolicy Bypass -File $postInstall $scriptDir
    }
    & $pythonExe -c "import napari" | Out-Null
}

& $pythonExe -m napari --with senoquant
