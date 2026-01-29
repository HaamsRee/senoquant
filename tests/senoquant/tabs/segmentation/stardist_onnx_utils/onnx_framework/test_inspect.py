"""Tests for ONNX inspection helpers.

Notes
-----
Exercises internal attribute parsing helpers without requiring ONNX.
"""

from __future__ import annotations

from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect import divisibility


class DummyAttr:
    """Minimal attribute stub."""

    INT = 0
    INTS = 1

    def __init__(self, name: str, value, kind: int) -> None:
        self.name = name
        self.type = kind
        self.ints = value if isinstance(value, (list, tuple)) else []
        self.i = value if isinstance(value, int) else 0


class DummyNode:
    """Minimal node stub."""

    def __init__(self, attrs) -> None:
        self.attribute = attrs


def test_get_attr_ints_reads_values() -> None:
    """Read integer attributes from a node.

    Returns
    -------
    None
    """
    node = DummyNode([DummyAttr("strides", [2, 2], DummyAttr.INTS)])
    assert divisibility._get_attr_ints(node, "strides") == [2, 2]


def test_get_attr_ints_handles_missing() -> None:
    """Return None when attribute is missing.

    Returns
    -------
    None
    """
    node = DummyNode([])
    assert divisibility._get_attr_ints(node, "strides") is None


class DummyDim:
    """Dim stub for shape formatting."""

    def __init__(self, dim_value=0, dim_param="") -> None:
        self.dim_value = dim_value
        self.dim_param = dim_param


class DummyShape:
    """Shape stub containing dims."""

    def __init__(self, dims) -> None:
        self.dim = dims


def test_format_shape_labels() -> None:
    """Format dynamic and static dimensions.

    Returns
    -------
    None
    """
    shape = DummyShape([DummyDim(dim_value=1), DummyDim(dim_param="H")])
    formatted = divisibility._format_shape(shape)
    assert formatted == ["1", "H (dynamic)"]
