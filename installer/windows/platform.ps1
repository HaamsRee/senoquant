function Test-SenoQuantWindowsArm64 {
    [CmdletBinding()]
    param(
        [string[]]$Architecture = @(
            $env:PROCESSOR_ARCHITECTURE
            $env:PROCESSOR_ARCHITEW6432
            [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        )
    )

    return [bool]($Architecture | Where-Object {
        $_ -and $_.Replace("-", "").ToUpperInvariant() -in @("ARM64", "AARCH64")
    })
}
