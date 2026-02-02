#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_ROOT="${REPO_ROOT}/dist/macos-installer"
APP_DIR="${DIST_ROOT}/SenoQuant.app"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
TOOLS_DIR="${RESOURCES_DIR}/tools"
WHEEL_DIR="${RESOURCES_DIR}/wheels"

echo "[SenoQuant] Building macOS installer..."

# Create directory structure
mkdir -p "${MACOS_DIR}"
mkdir -p "${RESOURCES_DIR}"
mkdir -p "${TOOLS_DIR}"
mkdir -p "${WHEEL_DIR}"

# Build wheel
echo "[SenoQuant] Building wheel..."
cd "${REPO_ROOT}"
python -m pip install --upgrade pip --quiet
python -m pip install --upgrade jsonschema --quiet
python -m pip install build --quiet
python -m build --wheel -o "${WHEEL_DIR}" 2>&1 | grep -v "SetuptoolsDeprecationWarning" | grep -v "License classifiers" | grep -v "See https://"
MICROMAMBA_BIN="${TOOLS_DIR}/micromamba"
if [ ! -f "${MICROMAMBA_BIN}" ]; then
    echo "[SenoQuant] Downloading micromamba..."
    
    # Detect architecture
    if [ "$(uname -m)" = "arm64" ]; then
        ARCH="osx-arm64"
    else
        ARCH="osx-64"
    fi
    
    MICROMAMBA_URL="https://micro.mamba.pm/api/micromamba/${ARCH}/latest"
    curl -L "${MICROMAMBA_URL}" -o "${TOOLS_DIR}/micromamba.tar.bz2"
    
    # Extract micromamba
    cd "${TOOLS_DIR}"
    tar -xjf micromamba.tar.bz2
    
    # Find and move the binary
    if [ -f "./bin/micromamba" ]; then
        mv ./bin/micromamba ./micromamba
        rm -rf ./bin
    fi
    
    chmod +x "${MICROMAMBA_BIN}"
    rm -f micromamba.tar.bz2
    
    if [ ! -f "${MICROMAMBA_BIN}" ]; then
        echo "ERROR: micromamba binary not found after extraction"
        exit 1
    fi
fi

# Create icon from SVG
ICON_SVG="${REPO_ROOT}/installer/senoquant_icon.svg"
ICON_ICNS="${RESOURCES_DIR}/senoquant.icns"

if [ -f "${ICON_SVG}" ]; then
    echo "[SenoQuant] Converting icon..."
    
    # Try cairosvg first (pure Python, most reliable)
    if command -v cairosvg &> /dev/null; then
        echo "[SenoQuant] Using cairosvg for icon conversion"
        cairosvg "${ICON_SVG}" -o "${RESOURCES_DIR}/icon_512.png" -w 512 -h 512
        ICON_PNG="${RESOURCES_DIR}/icon_512.png"
    # Try rsvg-convert (librsvg)
    elif command -v rsvg-convert &> /dev/null; then
        echo "[SenoQuant] Using rsvg-convert for icon conversion"
        rsvg-convert -w 512 -h 512 "${ICON_SVG}" > "${RESOURCES_DIR}/icon_512.png"
        ICON_PNG="${RESOURCES_DIR}/icon_512.png"
    # Try imagemagick with ghostscript installed
    elif command -v magick &> /dev/null && command -v gs &> /dev/null; then
        echo "[SenoQuant] Using ImageMagick with Ghostscript for icon conversion"
        magick -background none "${ICON_SVG}" -resize 512x512 "${RESOURCES_DIR}/icon_512.png"
        ICON_PNG="${RESOURCES_DIR}/icon_512.png"
    # Try convert (ImageMagick 6) with ghostscript
    elif command -v convert &> /dev/null && command -v gs &> /dev/null; then
        echo "[SenoQuant] Using ImageMagick 6 with Ghostscript for icon conversion"
        convert -background none "${ICON_SVG}" -resize 512x512 "${RESOURCES_DIR}/icon_512.png"
        ICON_PNG="${RESOURCES_DIR}/icon_512.png"
    else
        echo "WARNING: No SVG converter found. Icon will not be created."
        echo "         Install with: brew install librsvg cairosvg"
        ICON_PNG=""
    fi
    
    # If we have a PNG, create the iconset
    if [ -n "${ICON_PNG}" ] && [ -f "${ICON_PNG}" ]; then
        ICONSET="${RESOURCES_DIR}/senoquant.iconset"
        mkdir -p "${ICONSET}"
        
        # Use sips to generate all sizes
        sips -z 16 16     "${ICON_PNG}" --out "${ICONSET}/icon_16x16.png" > /dev/null 2>&1
        sips -z 32 32     "${ICON_PNG}" --out "${ICONSET}/icon_16x16@2x.png" > /dev/null 2>&1
        sips -z 32 32     "${ICON_PNG}" --out "${ICONSET}/icon_32x32.png" > /dev/null 2>&1
        sips -z 64 64     "${ICON_PNG}" --out "${ICONSET}/icon_32x32@2x.png" > /dev/null 2>&1
        sips -z 128 128   "${ICON_PNG}" --out "${ICONSET}/icon_128x128.png" > /dev/null 2>&1
        sips -z 256 256   "${ICON_PNG}" --out "${ICONSET}/icon_128x128@2x.png" > /dev/null 2>&1
        sips -z 256 256   "${ICON_PNG}" --out "${ICONSET}/icon_256x256.png" > /dev/null 2>&1
        sips -z 512 512   "${ICON_PNG}" --out "${ICONSET}/icon_256x256@2x.png" > /dev/null 2>&1
        sips -z 512 512   "${ICON_PNG}" --out "${ICONSET}/icon_512x512.png" > /dev/null 2>&1
        
        # Convert to .icns
        iconutil -c icns "${ICONSET}" -o "${ICON_ICNS}"
        rm -rf "${ICONSET}"
        rm -f "${RESOURCES_DIR}/icon_512.png"
    fi
else
    echo "WARNING: Icon SVG not found at ${ICON_SVG}"
fi

# Copy launcher scripts
echo "[SenoQuant] Copying launcher scripts..."
cp "${REPO_ROOT}/installer/macos/launch_senoquant.sh" "${MACOS_DIR}/launch_senoquant.sh"
cp "${REPO_ROOT}/installer/macos/post_install.sh" "${RESOURCES_DIR}/post_install.sh"
cp "${REPO_ROOT}/installer/macos/environment.macos.yml" "${RESOURCES_DIR}/environment.macos.yml"

chmod +x "${MACOS_DIR}/launch_senoquant.sh"
chmod +x "${RESOURCES_DIR}/post_install.sh"

# Create Info.plist
echo "[SenoQuant] Creating Info.plist..."
cat > "${CONTENTS_DIR}/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launch_senoquant.sh</string>
    <key>CFBundleIdentifier</key>
    <string>org.senoquant.SenoQuant</string>
    <key>CFBundleName</key>
    <string>SenoQuant</string>
    <key>CFBundleDisplayName</key>
    <string>SenoQuant</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>SQNT</string>
    <key>CFBundleIconFile</key>
    <string>senoquant.icns</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.productivity</string>
</dict>
</plist>
EOF

# Create PKG installer
echo "[SenoQuant] Creating PKG installer..."
PKG_NAME="SenoQuant-Installer"
PKG_PATH="${DIST_ROOT}/${PKG_NAME}.pkg"
COMPONENT_PKG="${DIST_ROOT}/SenoQuant.component.pkg"
COMPONENT_PLIST="${DIST_ROOT}/component.plist"
STAGING_DIR="${DIST_ROOT}/pkg_staging"

# Get version from pyproject.toml
VERSION=$(python -c "import tomllib; f=open('pyproject.toml','rb'); print(tomllib.load(f)['project']['version'])" 2>/dev/null || echo "1.0.0b2")
PKG_ID="org.senoquant.SenoQuant"

if [ ! -d "${APP_DIR}" ]; then
    echo "[SenoQuant] ERROR: App bundle missing. Aborting."
    exit 1
fi

# Remove old PKG artifacts if they exist
rm -f "${PKG_PATH}" "${COMPONENT_PKG}" "${COMPONENT_PLIST}"
rm -rf "${STAGING_DIR}"

# Prepare staging root with Applications/SenoQuant.app
mkdir -p "${STAGING_DIR}/Applications"
cp -R "${APP_DIR}" "${STAGING_DIR}/Applications/" 2>/dev/null || \
ditto "${APP_DIR}" "${STAGING_DIR}/Applications/SenoQuant.app"
if [ ! -d "${STAGING_DIR}/Applications/SenoQuant.app" ]; then
    echo "[SenoQuant] ERROR: App bundle missing from staging. Aborting."
    exit 1
fi

# Create a component plist with relocation disabled
pkgbuild --analyze --root "${STAGING_DIR}" "${COMPONENT_PLIST}"
/usr/libexec/PlistBuddy -c "Set :0:BundleIsRelocatable false" "${COMPONENT_PLIST}" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :0:BundleOverwriteAction upgrade" "${COMPONENT_PLIST}" 2>/dev/null || true

# Build component package targeting ~/Applications
pkgbuild \
    --root "${STAGING_DIR}" \
    --component-plist "${COMPONENT_PLIST}" \
    --install-location "$HOME" \
    --identifier "${PKG_ID}" \
    --version "${VERSION}" \
    "${COMPONENT_PKG}"

# Build final product package
productbuild \
    --package "${COMPONENT_PKG}" \
    --version "${VERSION}" \
    "${PKG_PATH}"

rm -rf "${STAGING_DIR}"

echo "[SenoQuant] Build complete!"
echo "           PKG: ${PKG_PATH}"
echo "           App: ${APP_DIR}"
