param(
    [string]$EnvironmentName = "senoquant-dev"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (!(Test-Path (Join-Path $repositoryRoot "pyproject.toml"))) {
    throw "Run this script from a SenoQuant repository checkout."
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "conda was not found. Install Miniforge, Miniconda, or Anaconda first."
}

$architectures = @(
    $env:PROCESSOR_ARCHITECTURE
    $env:PROCESSOR_ARCHITEW6432
    [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
)
$isWindowsArm64 = [bool]($architectures | Where-Object {
    $_ -and $_.Replace("-", "").ToUpperInvariant() -in @("ARM64", "AARCH64")
})
$platformArguments = @()
if ($isWindowsArm64) {
    $windowsBuild = [Environment]::OSVersion.Version.Build
    if ($windowsBuild -lt 26100) {
        throw "Windows ARM64 requires Windows 11 24H2 (build 26100) or later for the supported x64 emulation path."
    }
    $platformArguments = @("--platform", "win-64")
    Write-Host "[SenoQuant] Windows ARM64 detected; creating a win-64 environment for x64 emulation."
}

& conda run --name $EnvironmentName python --version *> $null
$environmentExists = $LASTEXITCODE -eq 0

if ($environmentExists) {
    if ($isWindowsArm64) {
        $environmentMachine = (& conda run --name $EnvironmentName python -c "import platform; print(platform.machine())" | Select-Object -Last 1).Trim()
        if ($environmentMachine.ToLowerInvariant() -notin @("amd64", "x86_64")) {
            throw "Existing environment '$EnvironmentName' is not win-64. Remove it or choose another environment name for the supported x64 emulation path."
        }
    }
    Write-Host "[SenoQuant] Updating existing conda environment: $EnvironmentName"
    & conda install --yes --name $EnvironmentName --channel conda-forge python=3.11 pip openjdk=21 jpype1 scyjava
} else {
    Write-Host "[SenoQuant] Creating conda environment: $EnvironmentName"
    & conda create --yes --name $EnvironmentName --channel conda-forge @platformArguments python=3.11 pip openjdk=21 jpype1 scyjava
}
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create or update the conda environment."
}

Write-Host "[SenoQuant] Installing uv"
& conda run --name $EnvironmentName python -m pip install --upgrade pip uv
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install uv."
}

Write-Host "[SenoQuant] Installing development dependencies and editable package"
Push-Location $repositoryRoot
try {
    & conda run --name $EnvironmentName uv pip install `
        --system-certs `
        --python python `
        pip-system-certs `
        "napari[all]" `
        --requirement requirements-test.txt `
        --editable .
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install the development dependencies."
    }
} finally {
    Pop-Location
}

Write-Host "[SenoQuant] Development environment is ready."
Write-Host "Run: conda activate $EnvironmentName"
Write-Host "Then: python -m pytest -q"
