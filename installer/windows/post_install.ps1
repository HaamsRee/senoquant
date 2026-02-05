param(
    [string]$AppDir,
    [string]$AppVersion
)

$ErrorActionPreference = 'Stop'

$logPath = Join-Path $AppDir "post_install.log"
try {
    Start-Transcript -Path $logPath -Append | Out-Null
} catch {
    # ignore transcript failures
}

Write-Host "[SenoQuant] Starting post-install..."

function Invoke-Checked {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        [Parameter(Mandatory=$true)]
        [scriptblock]$Command
    )

    Write-Host "[SenoQuant] $Message"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Message"
    }
}

if (-not $AppDir) {
    $AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$AppDir = $AppDir.Trim('"')

$envDir = Join-Path $AppDir "env"
$toolsDir = Join-Path $AppDir "tools"
$wheelDir = Join-Path $AppDir "wheels"
$micromambaExe = Join-Path $toolsDir "micromamba.exe"
$versionFile = Join-Path $AppDir "installed_version"

if (!(Test-Path $micromambaExe)) {
    throw "micromamba.exe not found at $micromambaExe"
}

Write-Host "[SenoQuant] Using micromamba: $micromambaExe"

$wheel = Get-ChildItem -Path $wheelDir -Filter "senoquant-*.whl" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $wheel) {
    throw "Wheel not found in $wheelDir"
}

$targetVersion = $null
if (-not [string]::IsNullOrWhiteSpace($AppVersion)) {
    $targetVersion = $AppVersion.Trim()
} elseif ($wheel.Name -match '^senoquant-([^-]+)-') {
    $targetVersion = $matches[1]
}
if ([string]::IsNullOrWhiteSpace($targetVersion)) {
    throw "Could not determine target SenoQuant version."
}

$installedVersion = $null
if (Test-Path $versionFile) {
    $installedVersion = (Get-Content -Path $versionFile -Raw).Trim()
}

if (Test-Path $envDir) {
    if ([string]::IsNullOrWhiteSpace($installedVersion)) {
        Write-Host "[SenoQuant] Version marker missing. Rebuilding environment for $targetVersion."
        Remove-Item -Path $envDir -Recurse -Force
    } elseif ($installedVersion -ne $targetVersion) {
        Write-Host "[SenoQuant] Version change detected ($installedVersion -> $targetVersion). Rebuilding environment."
        Remove-Item -Path $envDir -Recurse -Force
    }
}

if (!(Test-Path $envDir)) {
    Invoke-Checked "Creating environment: $envDir" { & $micromambaExe create -y -p $envDir python=3.11 pip }
}
Invoke-Checked "Upgrading pip" { & $micromambaExe run -p $envDir python -m pip install --upgrade pip }
Invoke-Checked "Installing uv" { & $micromambaExe run -p $envDir python -m pip install uv }
Invoke-Checked "Installing pip-system-certs" { & $micromambaExe run -p $envDir uv pip install pip-system-certs }

Invoke-Checked "Installing napari" { & $micromambaExe run -p $envDir uv pip install "napari[all]" }

Invoke-Checked "Installing SenoQuant wheel: $($wheel.Name)" { & $micromambaExe run -p $envDir uv pip install --force-reinstall $wheel.FullName }

Invoke-Checked "Installing GPU PyTorch (CUDA 12.1)" { & $micromambaExe run -p $envDir uv pip install --force-reinstall --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio }

Invoke-Checked "Validating napari import" { & $micromambaExe run -p $envDir python -c "import napari" }

Set-Content -Path $versionFile -Value $targetVersion -Encoding ASCII
Write-Host "[SenoQuant] Recorded installed version: $targetVersion"

Write-Host "[SenoQuant] Post-install complete."

try {
    Stop-Transcript | Out-Null
} catch {
    # ignore transcript failures
}
