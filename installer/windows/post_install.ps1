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

function Invoke-UvPipInstall {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Arguments
    )

    $uvCandidates = @(
        (Join-Path $envDir "Scripts\uv.exe"),
        (Join-Path $envDir "uv.exe")
    )
    $uvExe = $uvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $uvExe) {
        throw "uv.exe not found in environment: $envDir"
    }

    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "senoquant_uv_install.py"
    $pythonCode = @'
import os
import subprocess
import sys

uv_exe = sys.argv[1]
install_args = sys.argv[2:]

child_env = os.environ.copy()
child_env.pop("SSL_CERT_FILE", None)
child_env.pop("SSL_CERT_DIR", None)
child_env["UV_SYSTEM_CERTS"] = "true"
env_dir = os.path.dirname(sys.executable)
if os.path.basename(env_dir).lower() == "scripts":
    env_dir = os.path.dirname(env_dir)
java_home = os.path.join(env_dir, "Library")
path_prefixes = [
    env_dir,
    os.path.join(env_dir, "Scripts"),
    os.path.join(java_home, "bin"),
]
child_env["JAVA_HOME"] = java_home
child_env["PATH"] = os.pathsep.join(path_prefixes + [child_env.get("PATH", "")])

raise SystemExit(
    subprocess.call(
        [uv_exe, "pip", "install", "--system-certs", "--python", sys.executable, *install_args],
        env=child_env,
    )
)
'@
    Set-Content -Path $tempScript -Value $pythonCode -Encoding ASCII
    try {
        & $micromambaExe run -p $envDir python $tempScript $uvExe @Arguments
    } finally {
        Remove-Item -Path $tempScript -Force -ErrorAction SilentlyContinue
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
    Invoke-Checked "Creating environment: $envDir" { & $micromambaExe create -y -p $envDir -c conda-forge python=3.11 pip openjdk=21 jpype1 scyjava }
}
Invoke-Checked "Ensuring bundled OpenJDK, JPype, and scyjava" { & $micromambaExe install -y -p $envDir -c conda-forge openjdk=21 jpype1 scyjava }

$javaHome = Join-Path $envDir "Library"
$env:JAVA_HOME = $javaHome
$env:Path = ((@($envDir, (Join-Path $envDir "Scripts"), (Join-Path $javaHome "bin")) -join ";") + ";" + $env:Path)
Invoke-Checked "Validating bundled Java" { & $micromambaExe run -p $envDir java -version }

Invoke-Checked "Upgrading pip" { & $micromambaExe run -p $envDir python -m pip install --upgrade pip }

Invoke-Checked "Installing uv" { & $micromambaExe run -p $envDir python -m pip install uv }
Write-Host "[SenoQuant] uv installs will use system certificates and ignore SSL_CERT_FILE/SSL_CERT_DIR from the micromamba environment."
Invoke-Checked "Installing pip-system-certs" { Invoke-UvPipInstall @("pip-system-certs") }

Invoke-Checked "Installing napari" { Invoke-UvPipInstall @("napari[all]") }

Invoke-Checked "Installing SenoQuant wheel: $($wheel.Name)" { Invoke-UvPipInstall @("--reinstall-package", "senoquant", $wheel.FullName) }

Invoke-Checked "Installing GPU PyTorch (CUDA 12.1)" {
    Invoke-UvPipInstall @(
        "--force-reinstall",
        "--index-url",
        "https://download.pytorch.org/whl/cu121",
        "torch==2.5.1",
        "torchvision==0.20.1",
        "torchaudio==2.5.1"
    )
}

Invoke-Checked "Validating Java bridge imports" { & $micromambaExe run -p $envDir python -c "import jpype, scyjava, senoquant; print('jpype:', jpype.__version__)" }

Invoke-Checked "Validating napari import" { & $micromambaExe run -p $envDir python -c "import napari" }

Set-Content -Path $versionFile -Value $targetVersion -Encoding ASCII
Write-Host "[SenoQuant] Recorded installed version: $targetVersion"

Write-Host "[SenoQuant] Post-install complete."

try {
    Stop-Transcript | Out-Null
} catch {
    # ignore transcript failures
}
