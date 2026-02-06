#!/bin/bash

# Get the directory where the app bundle is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/launch_senoquant.sh"

# If launched from Finder (no TTY), re-launch inside Terminal for visibility
if [ -z "${SENOQUANT_TERMINAL}" ] && [ ! -t 1 ]; then
    ESCAPED_PATH=$(printf '%q' "${SCRIPT_PATH}")
    osascript <<EOF
tell application "Terminal"
    activate
    do script "export SENOQUANT_TERMINAL=1; ${ESCAPED_PATH}"
end tell
EOF
    exit 0
fi
CONTENTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
INFO_PLIST="${CONTENTS_DIR}/Info.plist"

# Use Application Support for writable data
APP_SUPPORT="${HOME}/Library/Application Support/SenoQuant"
mkdir -p "${APP_SUPPORT}"
ENV_DIR="${APP_SUPPORT}/env"
LOG_FILE="${APP_SUPPORT}/launch.log"
VERSION_FILE="${APP_SUPPORT}/installed_version"
APP_VERSION=""

if [ -f "${INFO_PLIST}" ]; then
    APP_VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "${INFO_PLIST}" 2>/dev/null || true)
fi

# Function to log to both file and terminal
log() {
    echo "[SenoQuant] $1" | tee -a "${LOG_FILE}"
}

run_post_install() {
    POST_INSTALL="${RESOURCES_DIR}/post_install.sh"
    if [ ! -f "${POST_INSTALL}" ]; then
        log "ERROR: post_install.sh not found at ${POST_INSTALL}"
        return 1
    fi

    if [ -n "${APP_VERSION}" ]; then
        "${POST_INSTALL}" "${RESOURCES_DIR}" "${APP_VERSION}" 2>&1 | tee -a "${LOG_FILE}"
    else
        "${POST_INSTALL}" "${RESOURCES_DIR}" 2>&1 | tee -a "${LOG_FILE}"
    fi

    return "${PIPESTATUS[0]}"
}

log "SenoQuant launching at $(date)"
if [ -n "${APP_VERSION}" ]; then
    log "App version: ${APP_VERSION}"
fi

SETUP_REQUIRED=0
if [ ! -d "${ENV_DIR}" ]; then
    log "Environment not found at ${ENV_DIR}"
    SETUP_REQUIRED=1
fi

if [ -n "${APP_VERSION}" ]; then
    INSTALLED_VERSION=""
    if [ -f "${VERSION_FILE}" ]; then
        INSTALLED_VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
    fi

    if [ -n "${INSTALLED_VERSION}" ] && [ "${INSTALLED_VERSION}" != "${APP_VERSION}" ]; then
        log "Version change detected (${INSTALLED_VERSION} -> ${APP_VERSION}). Rebuilding environment."
        rm -rf "${ENV_DIR}"
        SETUP_REQUIRED=1
    elif [ -z "${INSTALLED_VERSION}" ] && [ -d "${ENV_DIR}" ]; then
        log "Version marker missing. Refreshing environment for ${APP_VERSION}."
        SETUP_REQUIRED=1
    fi
fi

if [ $SETUP_REQUIRED -eq 1 ]; then
    log "Running post-install setup (this may take several minutes)..."
    run_post_install
    SETUP_STATUS=$?
    if [ $SETUP_STATUS -ne 0 ]; then
        log "ERROR: Post-install setup failed"
        log "Check ${LOG_FILE} for details"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
fi

# Find Python executable
PYTHON_EXE="${ENV_DIR}/bin/python"
if [ ! -f "${PYTHON_EXE}" ]; then
    log "ERROR: Python not found at ${PYTHON_EXE}"
    read -p "Press ENTER to close this window..."
    exit 1
fi

# Verify napari is installed
if ! "${PYTHON_EXE}" -c "import napari" 2>/dev/null; then
    log "napari not found. Running setup..."
    run_post_install
    SETUP_STATUS=$?
    if [ $SETUP_STATUS -ne 0 ]; then
        log "ERROR: Failed to setup napari"
        log "Check ${LOG_FILE} for details"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
    
    # Verify again
    if ! "${PYTHON_EXE}" -c "import napari" 2>/dev/null; then
        log "ERROR: napari import still failing"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
fi

log "Environment ready. Launching napari..."
log "=============================================="

# Launch napari with SenoQuant plugin
"${PYTHON_EXE}" -m napari --with senoquant 2>&1 | tee -a "${LOG_FILE}"
NAPARI_STATUS=${PIPESTATUS[0]}

if [ $NAPARI_STATUS -ne 0 ]; then
    log "ERROR: napari exited with status $NAPARI_STATUS"
    log "Check ${LOG_FILE} for details"
    read -p "Press ENTER to close this window..."
    exit $NAPARI_STATUS
fi

log "SenoQuant closed at $(date)"
