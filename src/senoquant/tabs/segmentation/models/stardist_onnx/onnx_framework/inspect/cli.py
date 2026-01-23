"""CLI for inspecting StarDist ONNX models."""

from __future__ import annotations

import argparse
from pathlib import Path

from .divisibility import infer_div_by, summarize_model_io


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect an ONNX model.")
    parser.add_argument("model", type=Path, help="Path to the ONNX model.")
    parser.add_argument("--ndim", type=int, choices=(2, 3), default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    # Summarize model IO shapes to show dynamic/static dims.
    summary = summarize_model_io(args.model)
    # Infer the spatial divisibility required by the graph.
    div_by = infer_div_by(args.model, ndim=args.ndim)

    print(f"Model: {args.model}")
    print("Inputs:")
    for idx, dims in enumerate(summary["inputs"]):
        print(f"  [{idx}] {dims}")
    print("Outputs:")
    for idx, dims in enumerate(summary["outputs"]):
        print(f"  [{idx}] {dims}")
    print(f"Inferred div_by: {div_by}")


if __name__ == "__main__":
    main()
