"""CLI for empirical receptive-field estimation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .receptive_field import infer_receptive_field, recommend_tile_overlap


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate ONNX receptive field.")
    parser.add_argument("model", type=Path, help="Path to the ONNX model.")
    parser.add_argument("--ndim", type=int, choices=(2, 3), default=None)
    parser.add_argument(
        "--shape",
        type=int,
        nargs="+",
        default=None,
        help="Spatial input shape (e.g. --shape 256 256 or --shape 64 64 64).",
    )
    parser.add_argument("--eps", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    input_shape = tuple(args.shape) if args.shape else None
    rf = infer_receptive_field(
        model_path=args.model,
        ndim=args.ndim,
        input_shape=input_shape,
        eps=args.eps,
    )
    overlap = recommend_tile_overlap(
        model_path=args.model,
        ndim=args.ndim,
        input_shape=input_shape,
        eps=args.eps,
    )

    print(f"Model: {args.model}")
    print(f"Receptive field: {rf}")
    print(f"Recommended overlap: {overlap}")


if __name__ == "__main__":
    main()
