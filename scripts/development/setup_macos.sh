#!/usr/bin/env bash

set -euo pipefail

ENVIRONMENT_NAME="${1:-senoquant-dev}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script is intended for macOS." >&2
    exit 1
fi

if ! command -v conda >/dev/null 2>&1; then
    echo "conda was not found. Install Miniforge, Miniconda, or Anaconda first." >&2
    exit 1
fi

if conda run --name "${ENVIRONMENT_NAME}" python --version >/dev/null 2>&1; then
    echo "[SenoQuant] Updating existing conda environment: ${ENVIRONMENT_NAME}"
    conda install --yes --name "${ENVIRONMENT_NAME}" --channel conda-forge \
        python=3.11 pip openjdk=21 jpype1 scyjava
else
    echo "[SenoQuant] Creating conda environment: ${ENVIRONMENT_NAME}"
    conda create --yes --name "${ENVIRONMENT_NAME}" --channel conda-forge \
        python=3.11 pip openjdk=21 jpype1 scyjava
fi

echo "[SenoQuant] Installing uv"
conda run --name "${ENVIRONMENT_NAME}" python -m pip install --upgrade pip uv

echo "[SenoQuant] Installing development dependencies and editable package"
cd "${REPOSITORY_ROOT}"
conda run --name "${ENVIRONMENT_NAME}" uv pip install \
    --system-certs \
    --python python \
    pip-system-certs \
    "napari[all]" \
    --requirement requirements-test.txt \
    --editable .

echo "[SenoQuant] Development environment is ready."
echo "Run: conda activate ${ENVIRONMENT_NAME}"
echo "Then: python -m pytest -q"
