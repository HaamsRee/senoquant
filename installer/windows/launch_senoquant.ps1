$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envDir = Join-Path $scriptDir "env"
$wheelDir = Join-Path $scriptDir "wheels"
$versionFile = Join-Path $scriptDir "installed_version"
$env:SENOQUANT_MODEL_DIR = Join-Path $envDir "models"

function Get-PackagedVersion {
    param([string]$Dir)

    if (!(Test-Path $Dir)) {
        return $null
    }

    $wheel = Get-ChildItem -Path $Dir -Filter "senoquant-*.whl" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $wheel) {
        return $null
    }

    if ($wheel.Name -match '^senoquant-([^-]+)-') {
        return $matches[1]
    }
    return $null
}

function Invoke-PostInstall {
    param([string]$TargetVersion)

    $postInstall = Join-Path $scriptDir "post_install.ps1"
    if (!(Test-Path $postInstall)) {
        throw "post_install.ps1 not found at $postInstall"
    }

    Write-Host "[SenoQuant] Running post-install setup..."
    if (-not [string]::IsNullOrWhiteSpace($TargetVersion)) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $postInstall $scriptDir $TargetVersion
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $postInstall $scriptDir
    }
    if ($LASTEXITCODE -ne 0) {
        throw "post_install.ps1 failed with exit code $LASTEXITCODE"
    }
}

$packagedVersion = Get-PackagedVersion -Dir $wheelDir
if (Test-Path $envDir) {
    $installedVersion = $null
    if (Test-Path $versionFile) {
        $installedVersion = (Get-Content -Path $versionFile -Raw).Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($packagedVersion)) {
        if ([string]::IsNullOrWhiteSpace($installedVersion)) {
            Write-Host "[SenoQuant] Version marker missing. Rebuilding environment for $packagedVersion."
            Remove-Item -Path $envDir -Recurse -Force
        } elseif ($installedVersion -ne $packagedVersion) {
            Write-Host "[SenoQuant] Version change detected ($installedVersion -> $packagedVersion). Rebuilding environment."
            Remove-Item -Path $envDir -Recurse -Force
        }
    }
}

if (!(Test-Path $envDir)) {
    Invoke-PostInstall -TargetVersion $packagedVersion
}

$javaExe = Join-Path $envDir "Library\bin\java.exe"
if (!(Test-Path $javaExe)) {
    Write-Host "[SenoQuant] Bundled Java missing. Refreshing environment."
    Invoke-PostInstall -TargetVersion $packagedVersion
}

$pythonExe = Join-Path $envDir "python.exe"
if (!(Test-Path $pythonExe)) {
    $pythonExe = Join-Path $envDir "Scripts\python.exe"
}

if (!(Test-Path $pythonExe)) {
    Invoke-PostInstall -TargetVersion $packagedVersion
    $pythonExe = Join-Path $envDir "python.exe"
    if (!(Test-Path $pythonExe)) {
        $pythonExe = Join-Path $envDir "Scripts\python.exe"
    }
    if (!(Test-Path $pythonExe)) {
        Write-Error "Python not found in environment: $envDir"
        exit 1
    }
}

# Ensure console-script entry points from the bundled environment are discoverable.
$pathPrefixes = @()
if (Test-Path $envDir) {
    $pathPrefixes += $envDir
}
$envScriptsDir = Join-Path $envDir "Scripts"
if (Test-Path $envScriptsDir) {
    $pathPrefixes += $envScriptsDir
}
if ($pathPrefixes.Count -gt 0) {
    $env:Path = (($pathPrefixes -join ";") + ";" + $env:Path)
}

# Set JAVA_HOME for bundled BioFormats/scyjava support.
$javaHomeDir = Join-Path $envDir "Library"
$javaBinDir = Join-Path $javaHomeDir "bin"
$env:JAVA_HOME = $javaHomeDir
if (Test-Path $javaBinDir) {
    $env:Path = "$javaBinDir;" + $env:Path
}

try {
    & $pythonExe -c "import napari" | Out-Null
} catch {
    Invoke-PostInstall -TargetVersion $packagedVersion
    & $pythonExe -c "import napari" | Out-Null
}

& $pythonExe -m napari --with senoquant
