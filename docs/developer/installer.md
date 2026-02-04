# Installers

This page documents the native installer pipelines for Windows and macOS, including build scripts, CI workflows, and troubleshooting notes.

## Overview

SenoQuant provides native installers for Windows (`.exe`) and macOS (`.pkg`) that bundle the application with a dedicated Python environment.

Both installers follow the same high-level pattern:

1. Bundle the SenoQuant wheel, micromamba, and launcher scripts.
2. Run a post-install script on first launch to create the Python environment.
3. Install napari, PyTorch, and dependencies.
4. Launch napari with the SenoQuant plugin.

## Version management

All installers read the version from `pyproject.toml` to ensure consistency.

- **Python package**: Uses `importlib.metadata.version("senoquant")` with fallback.
- **macOS installer**: Extracts the version using `tomllib` during build.
- **Windows installer**: Reads the version using Inno Setup's `ReadIni()` function.

To update the version across all installers, edit the `version` field in `pyproject.toml`.

---

## macOS installer

### Overview

The macOS installer creates a native PKG that installs SenoQuant as an app bundle in `~/Applications/`.

The app uses Application Support for writable data so it complies with macOS security policies.

Key components:

- App bundle: `dist/macos-installer/SenoQuant.app`.
- PKG installer: `dist/macos-installer/SenoQuant-Installer.pkg`.
- Build script: `installer/macos/build_macos_installer.sh`.
- Launcher: `installer/macos/launch_senoquant.sh`.
- Post-install: `installer/macos/post_install.sh`.
- Environment config: `installer/macos/environment.macos.yml`.

### Build pipeline

The installer is built via `.github/workflows/macos-installer.yml`:

1. Build the SenoQuant wheel.
2. Download micromamba for the target architecture (`arm64` or `x86_64`).
3. Convert the SVG icon to ICNS format using `librsvg`.
4. Assemble the app bundle with launcher scripts and resources.
5. Create a component PKG with bundle relocation disabled.
6. Package into a product PKG installer.

### Local build commands

Prerequisites:

- macOS 10.15 or later.
- Python 3.11 or later.
- Build tools: `python -m pip install build`.
- Icon converter (recommended): `brew install librsvg`.

From the repository root:

```bash
bash installer/macos/build_macos_installer.sh
```

The resulting PKG is written to `dist/macos-installer/SenoQuant-Installer.pkg`.

### App bundle structure

```text
SenoQuant.app/
  Contents/
    Info.plist
    MacOS/
      launch_senoquant.sh
    Resources/
      senoquant.icns
      post_install.sh
      environment.macos.yml
      tools/
        micromamba
      wheels/
        senoquant-*.whl
```

### Installation flow

1. The user runs the PKG, which installs to `~/Applications/SenoQuant.app`.
2. The user launches the app, which runs `launch_senoquant.sh`.
3. If launched from Finder, the launcher opens Terminal so logs are visible.
4. If `~/Library/Application Support/SenoQuant/env` does not exist, the launcher runs post-install.
5. Post-install creates the Python environment and installs dependencies.
6. The launcher starts napari with the SenoQuant plugin.

### Writable data locations

To avoid self-modification inside `~/Applications`, SenoQuant writes runtime data to Application Support:

- Python environment: `~/Library/Application Support/SenoQuant/env`.
- Launch log: `~/Library/Application Support/SenoQuant/launch.log`.
- Post-install log: `~/Library/Application Support/SenoQuant/post_install.log`.

The app bundle at `~/Applications/SenoQuant.app` remains read-only after installation.

### PKG configuration details

Install location:

- `$HOME` (expands to `~/Applications/`).

Component plist settings:

- `BundleIsRelocatable: false`, which prevents macOS from moving the app.
- `BundleOverwriteAction: upgrade`, which allows reinstallation.

The build uses a staging directory (`pkg_staging/Applications/`) so `pkgbuild` only packages intended files.

### Architecture support

The build script auto-detects the host architecture and downloads the matching micromamba binary:

- Apple Silicon (`arm64`) gets ARM64 micromamba.
- Intel (`x86_64`) gets x86_64 micromamba.

PyTorch is installed from standard channels and includes MPS support on Apple Silicon.

### Troubleshooting

**Icon not appearing.**

- Install `librsvg`: `brew install librsvg`.
- Rebuild the installer.
- Alternatively, place `senoquant.icns` manually in `Resources/`.

**App does not launch.**

- Check `~/Library/Application Support/SenoQuant/launch.log`.
- Check `~/Library/Application Support/SenoQuant/post_install.log`.
- Verify micromamba exists at `~/Applications/SenoQuant.app/Contents/Resources/tools/micromamba`.

**Terminal window does not open.**

- The app uses AppleScript to open Terminal when launched from Finder.
- Try launching directly from Terminal using `~/Applications/SenoQuant.app/Contents/MacOS/launch_senoquant.sh`.

**Permission denied errors.**

- Verify `launch_senoquant.sh` and `post_install.sh` are using the Application Support path.

---

## Windows installer

### Overview

The Windows installer bundles a portable app directory and runs a post-install step to create the Python environment, install dependencies, and install the SenoQuant wheel.

Key components:

- App bundle root: `dist/windows-installer/senoquant`.
- Inno Setup script: `installer/windows/senoquant.iss`.
- Build script: `installer/windows/build_windows_installer.ps1`.
- Post-install script: `installer/windows/post_install.ps1`.

### Build pipeline

The installer is built via `.github/workflows/windows-installer.yml`:

1. Build the SenoQuant wheel into the app bundle.
2. Download and include `micromamba.exe`.
3. Copy launchers, icons, and post-install scripts into the bundle.
4. Package with Inno Setup into `SenoQuant-Installer.exe`.

### Local build commands

Prerequisites:

- Python 3.11.
- Inno Setup (`ISCC`).
- ImageMagick (`magick` on `PATH`).

From the repository root:

1. Build the app bundle.

   ```powershell
   .\installer\windows\build_windows_installer.ps1
   ```

2. Build the installer with Inno Setup.

   ```powershell
   $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
   & $iscc .\installer\windows\senoquant.iss
   ```

The resulting installer is written to `installer/windows/Output/SenoQuant-Installer.exe`.

### App bundle layout

The build script assembles this structure under `dist/windows-installer/senoquant`:

```text
senoquant/
  launch_senoquant.bat
  launch_senoquant.ps1
  post_install.ps1
  senoquant_icon.ico
  tools/
    micromamba.exe
  wheels/
    senoquant-*.whl
```

### Post-install steps

`post_install.ps1` runs after installation to:

- Create a Python 3.11 environment under `env/`.
- Install `napari[all]`, PyTorch (CUDA 12.1), and SenoQuant from the local wheel.
- Validate imports.

The SenoQuant wheel pulls in runtime dependencies, including `senoquant-stardist-ext`.

### Troubleshooting

**Missing StarDist ops.**

- Verify `senoquant-stardist-ext` is installed.
- Check compiled binaries under `env/Lib/site-packages/senoquant/tabs/segmentation/stardist_onnx_utils/_stardist/lib/`.

**Install location issues.**

- Avoid `Program Files` to reduce permissions issues.
- Prefer user-local install paths, such as `%LOCALAPPDATA%`.

**GPU not detected.**

- Verify CUDA toolkit installation.
- Check PyTorch with `python -c "import torch; print(torch.cuda.is_available())"`.
- Confirm the installer pulled the CUDA 12.1-compatible PyTorch build.

---

## CI/CD workflows

Both installers are built automatically via GitHub Actions:

- macOS: `.github/workflows/macos-installer.yml`.
- Windows: `.github/workflows/windows-installer.yml`.

Triggers:

- Manual dispatch via `workflow_dispatch`.
- Automatic runs on release publication.

Artifacts:

- Uploaded as build artifacts for testing.
- Automatically attached to GitHub releases.

Verification:

- macOS: `pkgutil --check-signature` (unsigned PKG).
- Windows: successful Inno Setup build (signing is not configured by default).
