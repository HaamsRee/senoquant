param(
    [Parameter(Mandatory = $true)]
    [string]$AppDir,
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$activeProcessExitCode = 20
$managedInstallMarker = ".senoquant-managed-install"

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path.Trim('"')).TrimEnd('\', '/')
}

function Test-PathWithinDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    $prefix = $Directory.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    return $Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

try {
    $appRoot = Get-NormalizedPath -Path $AppDir
    $volumeRoot = [System.IO.Path]::GetPathRoot($appRoot).TrimEnd('\', '/')
    if ([string]::IsNullOrWhiteSpace($appRoot) -or $appRoot -eq $volumeRoot) {
        throw "Refusing to clean an empty path or volume root: $appRoot"
    }

    $markerPath = Join-Path $appRoot $managedInstallMarker
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "SenoQuant ownership marker not found at $markerPath. No runtime files were removed."
    }

    $environmentDir = Get-NormalizedPath -Path (Join-Path $appRoot "env")
    if (-not (Test-PathWithinDirectory -Path $environmentDir -Directory $appRoot) -or
        [System.IO.Path]::GetFileName($environmentDir) -ne "env") {
        throw "Invalid managed environment path: $environmentDir"
    }

    if (Test-Path -LiteralPath $environmentDir) {
        $environmentItem = Get-Item -LiteralPath $environmentDir -Force
        if (($environmentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to remove a linked or redirected environment: $environmentDir"
        }
    }

    $activeProcesses = @()
    try {
        $activeProcesses = @(
            Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue |
                Where-Object {
                    -not [string]::IsNullOrWhiteSpace($_.Path) -and
                    (Test-PathWithinDirectory -Path (Get-NormalizedPath $_.Path) -Directory $environmentDir)
                }
        )
    } catch {
        Write-Warning "Could not inspect running processes: $($_.Exception.Message)"
    }

    if ($activeProcesses.Count -gt 0) {
        $processIds = ($activeProcesses | ForEach-Object { $_.Id }) -join ", "
        [Console]::Error.WriteLine(
            "SenoQuant is still running (managed Python process IDs: $processIds). Close it before uninstalling."
        )
        exit $activeProcessExitCode
    }

    if ($CheckOnly) {
        exit 0
    }

    if (Test-Path -LiteralPath $environmentDir) {
        Write-Host "[SenoQuant] Removing managed runtime: $environmentDir"
        Remove-Item -LiteralPath $environmentDir -Recurse -Force
    }

    foreach ($fileName in @("installed_version", "post_install.log")) {
        $filePath = Join-Path $appRoot $fileName
        if (Test-Path -LiteralPath $filePath) {
            Write-Host "[SenoQuant] Removing managed file: $filePath"
            Remove-Item -LiteralPath $filePath -Force
        }
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
