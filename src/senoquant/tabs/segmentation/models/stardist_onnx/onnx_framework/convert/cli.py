"""CLI for converting StarDist models to ONNX."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import (
    DEFAULT_2D_MODEL,
    DEFAULT_3D_MODEL,
    convert_pretrained_2d,
    convert_pretrained_3d,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert StarDist models to ONNX.")
    parser.add_argument(
        "--dim",
        choices=("2", "3", "2d", "3d"),
        default="2d",
        help="Model dimensionality.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Pretrained model name/alias or model directory path.",
    )
    parser.add_argument(
        "--output",
        default=".",
        help="Output directory or ONNX file path.",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=18,
        help="ONNX opset version to export.",
    )
    args = parser.parse_args()

    dim = 2 if args.dim in ("2", "2d") else 3
    model_name = args.model or (DEFAULT_2D_MODEL if dim == 2 else DEFAULT_3D_MODEL)
    output = Path(args.output)

    if dim == 2:
        path = convert_pretrained_2d(model_name, output, opset=args.opset)
    else:
        path = convert_pretrained_3d(model_name, output, opset=args.opset)

    print(f"Saved ONNX model to {path}")


if __name__ == "__main__":
    main()
