#!/bin/bash
set -e

RESOURCES_DIR="${1:-}"

if [ -z "${RESOURCES_DIR}" ]; then
    RESOURCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Use Application Support for writable data
APP_SUPPORT="${HOME}/Library/Application Support/SenoQuant"
mkdir -p "${APP_SUPPORT}"
LOG_PATH="${APP_SUPPORT}/post_install.log"

# Function to log and execute commands
log_exec() {
    echo "[SenoQuant] $1" | tee -a "${LOG_PATH}"
    shift
    "$@" 2>&1 | tee -a "${LOG_PATH}"
    local status=$?
    if [ $status -ne 0 ]; then
        echo "[SenoQuant] ERROR: Command failed with exit code $status" | tee -a "${LOG_PATH}"
        exit $status
    fi
}

echo "[SenoQuant] Starting post-install at $(date)" > "${LOG_PATH}"

ENV_DIR="${RESOURCES_DIR}/env"
TOOLS_DIR="${RESOURCES_DIR}/tools"
WHEEL_DIR="${RESOURCES_DIR}/wheels"
MICROMAMBA_BIN="${TOOLS_DIR}/micromamba"

if [ ! -f "${MICROMAMBA_BIN}" ]; then
    echo "ERROR: micromamba not found at ${MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"
    exit 1
fi

echo "[SenoQuant] Using micromamba: ${MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"

# Create environment in Application Support
ENV_DIR="${APP_SUPPORT}/env"
if [ ! -d "${ENV_DIR}" ]; then
    log_exec "Creating environment: ${ENV_DIR}" \
        "${MICROMAMBA_BIN}" create -y -p "${ENV_DIR}" python=3.11 pip
fi

# Upgrade pip
log_exec "Upgrading pip" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -m pip install --upgrade pip

# Install uv for faster package installation
log_exec "Installing uv" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -m pip install uv

# Install napari
log_exec "Installing napari" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" uv pip install "napari[all]"

# Install PyTorch (CPU version for macOS - no CUDA)
log_exec "Installing PyTorch" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" uv pip install torch torchvision torchaudio

# Find and install SenoQuant wheel
WHEEL=$(find "${WHEEL_DIR}" -name "senoquant-*.whl" | head -n 1)
if [ -z "${WHEEL}" ]; then
    echo "ERROR: SenoQuant wheel not found in ${WHEEL_DIR}" | tee -a "${LOG_PATH}"
    exit 1
fi

log_exec "Installing SenoQuant wheel: $(basename ${WHEEL})" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" uv pip install "${WHEEL}"

# Validate napari installation
log_exec "Validating napari import" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -c "import napari; print('napari version:', napari.__version__)"

echo "[SenoQuant] Post-install complete at $(date)" | tee -a "${LOG_PATH}"
