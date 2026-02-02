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

# Use Application Support for writable data
APP_SUPPORT="${HOME}/Library/Application Support/SenoQuant"
mkdir -p "${APP_SUPPORT}"
ENV_DIR="${APP_SUPPORT}/env"
LOG_FILE="${APP_SUPPORT}/launch.log"

# Function to log to both file and terminal
log() {
    echo "[SenoQuant] $1" | tee -a "${LOG_FILE}"
}

log "SenoQuant launching at $(date)"

# Check if environment exists
if [ ! -d "${ENV_DIR}" ]; then
    log "Environment not found at ${ENV_DIR}"
    log "Running post-install setup (this may take several minutes)..."
    
    POST_INSTALL="${RESOURCES_DIR}/post_install.sh"
    if [ -f "${POST_INSTALL}" ]; then
        "${POST_INSTALL}" "${RESOURCES_DIR}" 2>&1 | tee -a "${LOG_FILE}"
        SETUP_STATUS=$?
    else
        log "ERROR: post_install.sh not found at ${POST_INSTALL}"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
    
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
    log "Napari not found. Running setup..."
    POST_INSTALL="${RESOURCES_DIR}/post_install.sh"
    if [ -f "${POST_INSTALL}" ]; then
        "${POST_INSTALL}" "${RESOURCES_DIR}" 2>&1 | tee -a "${LOG_FILE}"
        SETUP_STATUS=$?
    else
        log "ERROR: post_install.sh not found"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
    
    if [ $SETUP_STATUS -ne 0 ]; then
        log "ERROR: Failed to setup napari"
        log "Check ${LOG_FILE} for details"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
    
    # Verify again
    if ! "${PYTHON_EXE}" -c "import napari" 2>/dev/null; then
        log "ERROR: Napari import still failing"
        read -p "Press ENTER to close this window..."
        exit 1
    fi
fi

log "Environment ready. Launching napari..."
log "=============================================="

# Launch napari with SenoQuant plugin
"${PYTHON_EXE}" -m napari --with senoquant 2>&1 | tee -a "${LOG_FILE}"
NAPARI_STATUS=$?

if [ $NAPARI_STATUS -ne 0 ]; then
    log "ERROR: Napari exited with status $NAPARI_STATUS"
    log "Check ${LOG_FILE} for details"
    read -p "Press ENTER to close this window..."
    exit $NAPARI_STATUS
fi

log "SenoQuant closed at $(date)"
