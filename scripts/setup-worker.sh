#!/usr/bin/env bash
# Install the Worker's micro-benchmark dependency (PyTorch) once, matched to this host's
# CUDA. Run ONCE during host setup — not per container start — so firewall-constrained
# Workers don't download hundreds of MB at runtime. See T09 / worker/profiler.py.
#
# Why this exists: Compute4Me runs the *user's* container for real training (ADR-0006); the
# only torch the Worker itself needs is for the 30s ResNet18 yardstick (throughput_ref).
# So torch is the optional `bench` extra, and this script picks the right wheel for the host.
#
#   Usage:  scripts/setup-worker.sh
set -euo pipefail

# PyTorch publishes per-CUDA wheel indexes; pick one from the host's CUDA, else CPU.
pick_torch_index() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "cpu"; return
  fi
  # CUDA version as reported by the driver, e.g. "12.4" -> cu124.
  local cuda
  cuda="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits >/dev/null 2>&1 \
          && nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -n1 || true)"
  case "$cuda" in
    12.4|12.5|12.6|12.*) echo "cu124" ;;
    12.1|12.2|12.3)      echo "cu121" ;;
    11.8|11.*)           echo "cu118" ;;
    *)                   echo "cpu" ;;   # unknown/old → safe CPU fallback
  esac
}

INDEX="$(pick_torch_index)"
echo "[setup-worker] detected torch index: ${INDEX}"

if [ "$INDEX" = "cpu" ]; then
  TORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
else
  TORCH_INDEX_URL="https://download.pytorch.org/whl/${INDEX}"
fi

echo "[setup-worker] installing the 'bench' extra (torch) from ${TORCH_INDEX_URL}"
# uv resolves torch/torchvision from the CUDA-specific index; everything else from PyPI.
uv sync --extra bench --index "pytorch=${TORCH_INDEX_URL}" --index-strategy unsafe-best-match

echo "[setup-worker] done. Verify with:"
echo "  uv run python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'"
