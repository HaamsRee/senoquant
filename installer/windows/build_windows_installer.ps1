$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$distRoot = Join-Path $repoRoot "dist\windows-installer"
$appDir = Join-Path $distRoot "senoquant"
$toolsDir = Join-Path $appDir "tools"
$wheelDir = Join-Path $appDir "wheels"
$versionIniPath = Join-Path $distRoot "version.ini"

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

# Start from a clean app bundle so stale wheels/scripts are not packaged.
if (Test-Path $appDir) {
    Remove-Item -Path $appDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $appDir | Out-Null
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null

# Build wheel (ensure build is available)
Push-Location $repoRoot
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
if (!(Test-Path $pyprojectPath)) {
    throw "pyproject.toml not found at $pyprojectPath"
}

# Clear setuptools intermediates so removed files are not carried into wheels.
$setuptoolsBuildDir = Join-Path $repoRoot "build"
$eggInfoDir = Join-Path $repoRoot "senoquant.egg-info"
if (Test-Path $setuptoolsBuildDir) {
    Remove-Item -Path $setuptoolsBuildDir -Recurse -Force
}
if (Test-Path $eggInfoDir) {
    Remove-Item -Path $eggInfoDir -Recurse -Force
}

$inProjectSection = $false
$appVersion = $null
foreach ($line in Get-Content $pyprojectPath) {
    $trimmed = $line.Trim()
    if ($trimmed -match '^\[(.+)\]$') {
        $inProjectSection = ($matches[1] -eq "project")
        continue
    }
    if ($inProjectSection -and $trimmed -match '^version\s*=\s*"([^"]+)"') {
        $appVersion = $matches[1]
        break
    }
}
if ([string]::IsNullOrWhiteSpace($appVersion)) {
    throw "Failed to parse [project].version from pyproject.toml"
}

$versionIni = @(
    "[project]"
    "version=$appVersion"
) -join "`r`n"
Set-Content -Path $versionIniPath -Value $versionIni -Encoding ASCII
Write-Host "[SenoQuant] Installer version: $appVersion"

python -m pip install --upgrade pip | Out-Null
python -m pip install build | Out-Null
python -m build --wheel -o $wheelDir
Pop-Location

# Download micromamba
$micromambaExe = Join-Path $toolsDir "micromamba.exe"
if (!(Test-Path $micromambaExe)) {
    $url = "https://micro.mamba.pm/api/micromamba/win-64/latest"
    $archivePath = Join-Path $toolsDir "micromamba.tar.bz2"
    Invoke-WebRequest -Uri $url -OutFile $archivePath
    # Extract using tar (bundled with Windows 10+)
    tar -xf $archivePath -C $toolsDir
    $extracted = Join-Path $toolsDir "micromamba.exe"
    if (!(Test-Path $extracted)) {
        $candidate = Get-ChildItem -Path $toolsDir -Filter micromamba.exe -Recurse | Select-Object -First 1
        if ($candidate) {
            Copy-Item $candidate.FullName $micromambaExe -Force
        }
    }
    if (!(Test-Path $micromambaExe)) {
        throw "micromamba.exe not found after extraction."
    }
}

# Build icon (.ico) from SVG
$iconSvg = Join-Path $repoRoot "installer\senoquant_icon.svg"
$iconIco = Join-Path $repoRoot "installer\senoquant_icon.ico"
if (!(Test-Path $iconSvg)) {
    throw "Icon SVG not found: $iconSvg"
}
$magickCmd = Get-Command magick -ErrorAction SilentlyContinue
if (-not $magickCmd) {
    $pf = [Environment]::GetFolderPath("ProgramFiles")
    $pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
    $magickCandidates = @(
        Join-Path $pf "ImageMagick-7.1.0-Q16-HDRI\magick.exe",
        Join-Path $pf "ImageMagick-7.1.1-Q16-HDRI\magick.exe",
        Join-Path $pf "ImageMagick-7.1.2-Q16-HDRI\magick.exe",
        Join-Path $pf86 "ImageMagick-7.1.0-Q16-HDRI\magick.exe",
        Join-Path $pf86 "ImageMagick-7.1.1-Q16-HDRI\magick.exe",
        Join-Path $pf86 "ImageMagick-7.1.2-Q16-HDRI\magick.exe"
    )
    $magickPath = $magickCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $magickPath) {
        throw "ImageMagick (magick) not found. Install it or add magick.exe to PATH."
    }
} else {
    $magickPath = $magickCmd.Source
}
& $magickPath -background none $iconSvg -define icon:auto-resize=256,128,64,48,32,16 $iconIco
if (!(Test-Path $iconIco)) {
    throw "Icon conversion failed: $iconIco"
}

# Copy launchers and installer scripts into app dir
Copy-Item (Join-Path $repoRoot "installer\windows\launch_senoquant.ps1") (Join-Path $appDir "launch_senoquant.ps1") -Force
Copy-Item (Join-Path $repoRoot "installer\windows\launch_senoquant.bat") (Join-Path $appDir "launch_senoquant.bat") -Force
Copy-Item (Join-Path $repoRoot "installer\windows\post_install.ps1") (Join-Path $appDir "post_install.ps1") -Force
if ($micromambaExe -ne (Join-Path $toolsDir "micromamba.exe")) {
    Copy-Item $micromambaExe (Join-Path $toolsDir "micromamba.exe") -Force
}
Copy-Item $iconIco (Join-Path $appDir "senoquant_icon.ico") -Force
