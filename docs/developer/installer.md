# Installers

This page documents the native installer pipelines for Windows and macOS, including build scripts, CI workflows, and troubleshooting.

## Overview

SenoQuant provides native installers for Windows (`.exe`) and macOS (`.pkg`) that bundle the application with a dedicated Python environment. Both installers use a similar pattern:

1. Bundle the SenoQuant wheel, micromamba, and launcher scripts.
2. Run a post-install script on first launch to create the Python environment.
3. Install napari, PyTorch, and dependencies.
4. Launch napari with the SenoQuant plugin.

## Version Management

All installers read the version from `pyproject.toml` to ensure consistency:

- **Python package**: Uses `importlib.metadata.version("senoquant")` with fallback
- **macOS installer**: Extracts version using `tomllib` during build
- **Windows installer**: Reads version using Inno Setup's `ReadIni()` function

To update the version across all installers, edit the `version` field in `pyproject.toml`.

---

## macOS Installer

### Overview

The macOS installer creates a native PKG that installs SenoQuant as an app bundle to `~/Applications/`. The app uses Application Support for writable data to comply with macOS security policies.

**Key components:**

- App bundle: `dist/macos-installer/SenoQuant.app`
- PKG installer: `dist/macos-installer/SenoQuant-Installer.pkg`
- Build script: `installer/macos/build_macos_installer.sh`
- Launcher: `installer/macos/launch_senoquant.sh`
- Post-install: `installer/macos/post_install.sh`
- Environment config: `installer/macos/environment.macos.yml`

### Build Pipeline

The installer is built via the GitHub workflow `.github/workflows/macos-installer.yml`:

1. Build the SenoQuant wheel.
2. Download micromamba for the target architecture (ARM64 or x86_64).
3. Convert the SVG icon to ICNS format using `librsvg`.
4. Assemble the app bundle with launcher scripts and resources.
5. Create a component PKG with bundle relocation disabled.
6. Package into a product PKG installer.

### Local Build Commands

**Prerequisites:**

- macOS 10.15 or later
- Python 3.11+
- Build tools: `python -m pip install build`
- Icon converter (recommended): `brew install librsvg`

**From the repository root:**

```bash
bash installer/macos/build_macos_installer.sh
```

The resulting PKG is written to `dist/macos-installer/SenoQuant-Installer.pkg`.

### App Bundle Structure

```
SenoQuant.app/
├── Contents/
│   ├── Info.plist                    # Bundle metadata
│   ├── MacOS/
│   │   └── launch_senoquant.sh       # Entry point script
│   └── Resources/
│       ├── senoquant.icns            # App icon
│       ├── post_install.sh           # First-run setup
│       ├── environment.macos.yml     # Conda environment spec
│       ├── tools/
│       │   └── micromamba            # Environment manager
│       └── wheels/
│           └── senoquant-*.whl       # SenoQuant package
```

### Installation Flow

1. **User runs PKG** → installs to `~/Applications/SenoQuant.app`
2. **User launches app** → `launch_senoquant.sh` runs
3. **Terminal check** → if launched from Finder, re-opens in Terminal for visibility
4. **Environment check** → if `~/Library/Application Support/SenoQuant/env` doesn't exist, run post-install
5. **Post-install** → creates Python environment, installs dependencies (5-10 minutes)
6. **Launch napari** → opens with SenoQuant plugin loaded

### Writable Data Locations

To comply with macOS security policies that prevent apps from modifying themselves in `~/Applications`, SenoQuant uses Application Support:

- **Python environment**: `~/Library/Application Support/SenoQuant/env`
- **Launch log**: `~/Library/Application Support/SenoQuant/launch.log`
- **Post-install log**: `~/Library/Application Support/SenoQuant/post_install.log`

The app bundle at `~/Applications/SenoQuant.app` remains read-only after installation.

### PKG Configuration Details

**Install location**: `$HOME` (expands to `~/Applications/`)

**Component plist settings**:
- `BundleIsRelocatable: false` → prevents macOS from moving the app
- `BundleOverwriteAction: upgrade` → allows reinstallation

**Why staging directory?** The build uses a staging directory (`pkg_staging/Applications/`) to isolate the app bundle from build artifacts, preventing pkgbuild from including unintended files.

### Architecture Support

The build script auto-detects the host architecture and downloads the appropriate micromamba:

- **Apple Silicon** (arm64): ARM64 micromamba
- **Intel** (x86_64): x86_64 micromamba

PyTorch is installed via standard channels and automatically includes MPS support on Apple Silicon.

### Troubleshooting

**Icon not appearing:**
- Install `librsvg`: `brew install librsvg`
- Rebuild the installer
- Alternatively, manually place `senoquant.icns` in `Resources/`

**App doesn't launch:**
- Check launch log: `~/Library/Application Support/SenoQuant/launch.log`
- Check post-install log: `~/Library/Application Support/SenoQuant/post_install.log`
- Verify micromamba exists: `ls ~/Applications/SenoQuant.app/Contents/Resources/tools/micromamba`

**Terminal window doesn't open:**
- The app uses AppleScript to open Terminal when launched from Finder
- Try launching directly from Terminal: `~/Applications/SenoQuant.app/Contents/MacOS/launch_senoquant.sh`

**Permission denied errors:**
- Should not occur if using Application Support correctly
- If you see these, verify `launch_senoquant.sh` and `post_install.sh` are using `APP_SUPPORT` variable

---

## Windows Installer

### Overview

The Windows installer bundles a portable app directory and runs a post-install step to create the Python environment, install dependencies, and set up the SenoQuant wheel.

**Key components:**

- App bundle root: `dist/windows-installer/senoquant`
- Inno Setup script: `installer/windows/senoquant.iss`
- Build script: `installer/windows/build_windows_installer.ps1`
- Post-install script: `installer/windows/post_install.ps1`

### Build Pipeline

The installer is built via the GitHub workflow `.github/workflows/windows-installer.yml`:

1. Build the SenoQuant wheel into the app bundle.
2. Download and include `micromamba.exe`.
3. Copy launchers, icon, and post-install script into the bundle.
4. Package with Inno Setup into `SenoQuant-Installer.exe`.

### Local Build Commands

**Prerequisites:**

- Python 3.11
- Inno Setup (ISCC)
- ImageMagick (`magick` on PATH)

**From the repository root:**

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

### App Bundle Layout

The build script assembles this structure under `dist/windows-installer/senoquant`:

```
senoquant/
├── launch_senoquant.bat
├── launch_senoquant.ps1
├── post_install.ps1
├── senoquant_icon.ico
├── tools/
│   └── micromamba.exe
└── wheels/
    └── senoquant-*.whl
```

### Post-Install Steps

`post_install.ps1` runs after installation to:

- Create a Python 3.11 environment under `env/`.
- Install `napari[all]`, PyTorch (CUDA 12.1), and SenoQuant from the local wheel.
- Validate imports.

The SenoQuant wheel pulls in runtime dependencies, including `senoquant-stardist-ext`.

### Troubleshooting

**Missing StarDist ops:**
- Verify `senoquant-stardist-ext` is installed
- Check compiled binaries exist: `env/Lib/site-packages/senoquant/tabs/segmentation/stardist_onnx_utils/_stardist/lib/`

**Install location:**
- Avoid `Program Files` to prevent permissions issues
- The installer warns and recommends user-local installs (e.g., `%LOCALAPPDATA%`)

**GPU not detected:**
- Verify CUDA toolkit is installed
- Check PyTorch installation: `python -c "import torch; print(torch.cuda.is_available())"`
- The installer uses PyTorch with CUDA 12.1 support

---

## CI/CD Workflows

Both installers are built automatically via GitHub Actions:

- **macOS**: `.github/workflows/macos-installer.yml`
- **Windows**: `.github/workflows/windows-installer.yml`

**Triggers:**
- Manual dispatch via `workflow_dispatch`
- Automatic on release publication

**Artifacts:**
- Uploaded as build artifacts for testing
- Automatically attached to GitHub releases

**Verification:**
- macOS: `pkgutil --check-signature` (unsigned PKG)
- Windows: Build completes successfully (Inno Setup doesn't sign by default)
