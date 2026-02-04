# SenoQuant macOS Installer

This directory contains scripts to build a macOS installer for SenoQuant.

## Prerequisites

- macOS 10.15 or later
- Python 3.11+
- Build tools: `python -m pip install build`
- Icon conversion tools (one of):
  - `librsvg` (recommended): `brew install librsvg`
  - ImageMagick with Ghostscript: `brew install imagemagick ghostscript`
  - Or skip icon conversion by not having these tools installed

## Building the Installer

Run the build script from the repository root:

```bash
cd /path/to/senoquant
bash installer/macos/build_macos_installer.sh
```

This will:

1. Build the SenoQuant wheel package
2. Download micromamba for the current architecture (Intel or Apple Silicon)
3. Convert the icon from SVG to ICNS format (if ImageMagick is available)
4. Create a macOS app bundle structure
5. Package everything into a PKG installer

## Output

The installer is created at:
- PKG: `dist/macos-installer/SenoQuant-Installer.pkg`
- App Bundle: `dist/macos-installer/SenoQuant.app`

## Installation

1. **Download and open the PKG file** - `SenoQuant-Installer.pkg`
2. **Follow the installer prompts**
   - The app is installed into `/Applications`
3. **Open SenoQuant**
   - Find it in Applications folder or Spotlight
   - Double-click to launch
   - A Terminal window opens showing installation progress
   - The first launch will create the Python environment (may take 5-10 minutes)
   - Once complete, napari will open with SenoQuant loaded

## What Gets Installed

- Python 3.11 environment with micromamba
- napari and all dependencies
- PyTorch
- SenoQuant plugin and its dependencies

## First Launch

When you launch SenoQuant:

1. **A Terminal window opens** showing status messages
2. **First launch only**: 
   - Post-install script runs automatically
   - Creates Python environment with dependencies
   - May take **5-10 minutes** depending on internet speed
   - Log shown in Terminal: `SenoQuant.app/Contents/Resources/post_install.log`
3. **napari opens** once setup completes
4. **Terminal remains open** while napari runs
   - Close it when you're done with SenoQuant
5. **Subsequent launches** skip setup and open immediately



## Troubleshooting

### Icon conversion errors

If you see errors like `gs: command not found` during icon conversion:

**Solution 1: Use librsvg** (recommended)
```bash
brew install librsvg
bash installer/macos/build_macos_installer.sh
```

**Solution 2: Use ImageMagick with Ghostscript**
```bash
brew install ghostscript
bash installer/macos/build_macos_installer.sh
```

**Solution 3: Skip icon conversion**
The script will continue without an icon if no SVG converter is found. You can add an icon manually later to `SenoQuant.app/Contents/Resources/senoquant.icns`.

### App doesn't launch

If the app doesn't launch:

1. Check the post-install log: `SenoQuant.app/Contents/Resources/post_install.log`
2. Try running the post-install script manually:
   ```bash
   bash SenoQuant.app/Contents/Resources/post_install.sh
   ```
3. Check that micromamba exists:
   ```bash
   ls -la SenoQuant.app/Contents/Resources/tools/micromamba
   ```

## Architecture Support

The installer automatically detects your Mac architecture:
- Apple Silicon (M1/M2/M3): Downloads ARM64 micromamba
- Intel: Downloads x86_64 micromamba

Both architectures will get the standard PyTorch package, which supports:
- Apple Silicon: MPS (Metal Performance Shaders) acceleration
- Intel: CPU-only operation
