#!/bin/bash
set -u -o pipefail

RESOURCES_DIR="${1:-}"
APP_VERSION="${2:-}"

if [ -z "${RESOURCES_DIR}" ]; then
    RESOURCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

HOST_ARCH="$(uname -m)"
if [ "${HOST_ARCH}" != "arm64" ]; then
    echo "ERROR: SenoQuant requires native Apple Silicon macOS (arm64). Intel and Rosetta are unsupported." >&2
    exit 1
fi

CONSTRAINTS_FILE="${RESOURCES_DIR}/constraints.txt"
if [ ! -f "${CONSTRAINTS_FILE}" ]; then
    echo "ERROR: Constraints file not found at ${CONSTRAINTS_FILE}" >&2
    exit 1
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
    local status=${PIPESTATUS[0]}
    if [ $status -ne 0 ]; then
        echo "[SenoQuant] ERROR: Command failed with exit code $status" | tee -a "${LOG_PATH}"
        exit $status
    fi
}

uv_pip_install() (
    cd "${RESOURCES_DIR}" || exit 1
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" env -u SSL_CERT_FILE -u SSL_CERT_DIR \
        JAVA_HOME="${ENV_DIR}" PATH="${ENV_DIR}/bin:${PATH}" UV_SYSTEM_CERTS=true \
        uv pip install --system-certs --python "${ENV_DIR}/bin/python" --constraint constraints.txt "$@"
)

echo "[SenoQuant] Starting post-install at $(date)" > "${LOG_PATH}"

TOOLS_DIR="${RESOURCES_DIR}/tools"
WHEEL_DIR="${RESOURCES_DIR}/wheels"
VERSION_FILE="${APP_SUPPORT}/installed_version"
ARCH_FILE="${APP_SUPPORT}/installed_arch"

MICROMAMBA_ARCH="osx-arm64"

PREFERRED_MICROMAMBA_BIN="${TOOLS_DIR}/${MICROMAMBA_ARCH}/micromamba"
OLD_NAMED_MICROMAMBA_BIN="${TOOLS_DIR}/micromamba-${MICROMAMBA_ARCH}"
LEGACY_MICROMAMBA_BIN="${TOOLS_DIR}/micromamba"
if [ -f "${PREFERRED_MICROMAMBA_BIN}" ]; then
    BUNDLED_MICROMAMBA_BIN="${PREFERRED_MICROMAMBA_BIN}"
elif [ -f "${OLD_NAMED_MICROMAMBA_BIN}" ]; then
    BUNDLED_MICROMAMBA_BIN="${OLD_NAMED_MICROMAMBA_BIN}"
elif [ -f "${LEGACY_MICROMAMBA_BIN}" ]; then
    BUNDLED_MICROMAMBA_BIN="${LEGACY_MICROMAMBA_BIN}"
else
    echo "ERROR: micromamba not found for ${MICROMAMBA_ARCH} at ${PREFERRED_MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"
    exit 1
fi

if [ ! -f "${BUNDLED_MICROMAMBA_BIN}" ]; then
    echo "ERROR: micromamba not found at ${BUNDLED_MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"
    exit 1
fi

RUNTIME_TOOLS_DIR="${APP_SUPPORT}/tools/${MICROMAMBA_ARCH}"
MICROMAMBA_BIN="${RUNTIME_TOOLS_DIR}/micromamba"
mkdir -p "${RUNTIME_TOOLS_DIR}"
if ! cmp -s "${BUNDLED_MICROMAMBA_BIN}" "${MICROMAMBA_BIN}"; then
    cp "${BUNDLED_MICROMAMBA_BIN}" "${MICROMAMBA_BIN}"
fi
chmod +x "${MICROMAMBA_BIN}"

if command -v file >/dev/null 2>&1; then
    MICROMAMBA_FILE_DESC="$(file -b "${MICROMAMBA_BIN}")"
    if [[ "${MICROMAMBA_FILE_DESC}" != *"arm64"* ]]; then
        echo "ERROR: bundled micromamba is not compatible with Apple Silicon (${MICROMAMBA_FILE_DESC})" | tee -a "${LOG_PATH}"
        exit 1
    fi
fi

echo "[SenoQuant] Detected macOS architecture: ${HOST_ARCH} (${MICROMAMBA_ARCH})" | tee -a "${LOG_PATH}"
echo "[SenoQuant] Bundled micromamba: ${BUNDLED_MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"
echo "[SenoQuant] Using micromamba: ${MICROMAMBA_BIN}" | tee -a "${LOG_PATH}"

# Find the newest bundled SenoQuant wheel.
WHEEL=$(ls -t "${WHEEL_DIR}"/senoquant-*.whl 2>/dev/null | head -n 1 || true)
if [ -z "${WHEEL}" ]; then
    echo "ERROR: SenoQuant wheel not found in ${WHEEL_DIR}" | tee -a "${LOG_PATH}"
    exit 1
fi

TARGET_VERSION="${APP_VERSION}"
if [ -z "${TARGET_VERSION}" ]; then
    TARGET_VERSION="$(basename "${WHEEL}")"
    TARGET_VERSION="${TARGET_VERSION#senoquant-}"
    TARGET_VERSION="${TARGET_VERSION%%-*}"
fi

INSTALLED_VERSION=""
if [ -f "${VERSION_FILE}" ]; then
    INSTALLED_VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi
INSTALLED_ARCH=""
if [ -f "${ARCH_FILE}" ]; then
    INSTALLED_ARCH="$(tr -d '[:space:]' < "${ARCH_FILE}")"
fi

# Create environment in Application Support
ENV_DIR="${APP_SUPPORT}/env"
if [ -d "${ENV_DIR}" ]; then
    if [ -n "${INSTALLED_ARCH}" ] && [ "${INSTALLED_ARCH}" != "${MICROMAMBA_ARCH}" ]; then
        echo "[SenoQuant] Architecture change detected (${INSTALLED_ARCH} -> ${MICROMAMBA_ARCH}). Rebuilding environment." | tee -a "${LOG_PATH}"
        rm -rf "${ENV_DIR}"
    elif [ -z "${INSTALLED_VERSION}" ]; then
        echo "[SenoQuant] Version marker missing. Rebuilding environment for ${TARGET_VERSION}." | tee -a "${LOG_PATH}"
        rm -rf "${ENV_DIR}"
    elif [ "${INSTALLED_VERSION}" != "${TARGET_VERSION}" ]; then
        echo "[SenoQuant] Version change detected (${INSTALLED_VERSION} -> ${TARGET_VERSION}). Rebuilding environment." | tee -a "${LOG_PATH}"
        rm -rf "${ENV_DIR}"
    fi
fi

if [ ! -d "${ENV_DIR}" ]; then
    log_exec "Creating environment: ${ENV_DIR}" \
        "${MICROMAMBA_BIN}" create -y -p "${ENV_DIR}" -c conda-forge python=3.11 pip openjdk=21 jpype1 scyjava
fi

log_exec "Ensuring bundled OpenJDK, JPype, and scyjava" \
    "${MICROMAMBA_BIN}" install -y -p "${ENV_DIR}" -c conda-forge openjdk=21 jpype1 scyjava

log_exec "Validating bundled Java" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" env JAVA_HOME="${ENV_DIR}" java -version

# Upgrade pip
log_exec "Upgrading pip" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -m pip install --upgrade pip

# Install uv for faster package installation
log_exec "Installing uv" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -m pip install --constraint "${CONSTRAINTS_FILE}" uv

echo "[SenoQuant] uv installs will use system certificates and ignore SSL_CERT_FILE/SSL_CERT_DIR from the micromamba environment." | tee -a "${LOG_PATH}"

# Install pip-system-certs for SSL certificate handling
log_exec "Installing pip-system-certs" \
    uv_pip_install pip-system-certs

# Install napari
log_exec "Installing napari" \
    uv_pip_install "napari[all]"

# Install PyTorch (CPU version for macOS - no CUDA)
log_exec "Installing PyTorch" \
    uv_pip_install torch torchvision torchaudio "numpy>=1.23,<=1.26.4"

log_exec "Installing SenoQuant wheel: $(basename "${WHEEL}")" \
    uv_pip_install --reinstall-package senoquant "${WHEEL}"

log_exec "Validating Java bridge imports" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" env JAVA_HOME="${ENV_DIR}" python -c "import jpype, scyjava, senoquant; print('jpype:', jpype.__version__)"

# Validate napari installation
log_exec "Validating napari import" \
    "${MICROMAMBA_BIN}" run -p "${ENV_DIR}" python -c "import napari; print('napari version:', napari.__version__)"

echo "${TARGET_VERSION}" > "${VERSION_FILE}"
echo "${MICROMAMBA_ARCH}" > "${ARCH_FILE}"
echo "[SenoQuant] Recorded installed version: ${TARGET_VERSION}" | tee -a "${LOG_PATH}"

echo "[SenoQuant] Post-install complete at $(date)" | tee -a "${LOG_PATH}"
