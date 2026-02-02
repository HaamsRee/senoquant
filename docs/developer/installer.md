# Windows Installer

This page documents the Windows installer pipeline and its supporting scripts.

## Overview

The Windows installer bundles a portable app directory and runs a post-install step to create the Python environment, install dependencies, and set up the SenoQuant wheel.

Key components:

- App bundle root: `dist/windows-installer/senoquant`
- Inno Setup script: `installer/windows/senoquant.iss`
- Build script: `installer/windows/build_windows_installer.ps1`
- Post-install script: `installer/windows/post_install.ps1`

## Build pipeline

The installer is built via the GitHub workflow `windows-installer.yml`:

1. Build the SenoQuant wheel into the app bundle.
2. Download and include `micromamba.exe`.
3. Copy launchers, icon, and post-install script into the bundle.
4. Package with Inno Setup into `SenoQuant-Installer.exe`.

## Local build commands

Prerequisites:

- Python 3.11
- Inno Setup (ISCC)
- ImageMagick (`magick` on PATH)

From the repository root:

1. Build the app bundle:

	```powershell
	.\installer\windows\build_windows_installer.ps1
	```

2. Build the installer with Inno Setup:

	```powershell
	$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
	& $iscc .\installer\windows\senoquant.iss
	```

The resulting installer is written to `installer/windows/Output/SenoQuant-Installer.exe`.

## App bundle layout

The build script assembles this structure under `dist/windows-installer/senoquant`:

- `launch_senoquant.bat` / `launch_senoquant.ps1`
- `post_install.ps1`
- `tools/micromamba.exe`
- `wheels/` (contains the SenoQuant wheel)
- `senoquant_icon.ico`

## Post-install steps

`post_install.ps1` runs after installation to:

- Create a Python 3.11 environment under `env/`.
- Install `napari[all]`, PyTorch (CUDA 12.1), and SenoQuant from the local wheel.
- Validate imports.

The SenoQuant wheel pulls in runtime dependencies, including `senoquant-stardist-ext`.

## Troubleshooting

- Missing StarDist ops: verify `senoquant-stardist-ext` is installed and that compiled binaries are in `env/Lib/site-packages/senoquant/tabs/segmentation/stardist_onnx_utils/_stardist/lib/`.
- Install location: avoid `Program Files` to prevent permissions issues. The installer warns and recommends user-local installs.
