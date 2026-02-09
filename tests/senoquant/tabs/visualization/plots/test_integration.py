"""Tests for visualization backend integration."""

import pandas as pd
import pytest
from senoquant.tabs.visualization.backend import VisualizationBackend
from senoquant.tabs.visualization.plots import PlotConfig, build_plot_data
from senoquant.tabs.visualization.plots.spatialplot import SpatialPlot
from senoquant.tabs.visualization.plots.umap import UMAPPlot
from senoquant.tabs.visualization.plots.double_expression import DoubleExpressionPlot

class MockContext:
    """Mock context for plot handlers."""
    def __init__(self, state, plot_handler=None):
        self.state = state
        self.plot_handler = plot_handler

@pytest.fixture
def input_data(tmp_path):
    """Create a dummy CSV file for testing."""
    df = pd.DataFrame({
        "centroid_x_pixels": [10, 20, 30, 40, 50],
        "centroid_y_pixels": [10, 20, 30, 40, 50],
        "p16_mean_intensity": [10, 50, 10, 50, 10],
        "p21_mean_intensity": [10, 10, 50, 50, 10],
        "Ki67_mean_intensity": [5, 5, 5, 5, 5],
    })
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    csv_path = input_dir / "data.csv"
    df.to_csv(csv_path, index=False)
    return input_dir

@pytest.fixture
def input_data_no_coords(tmp_path):
    """Create a dummy CSV file without coordinate columns."""
    df = pd.DataFrame({
        "p16_mean_intensity": [10, 50, 10, 50, 10],
    })
    input_dir = tmp_path / "input_no_coords"
    input_dir.mkdir()
    csv_path = input_dir / "data.csv"
    df.to_csv(csv_path, index=False)
    return input_dir

def test_spatial_plot(input_data, tmp_path):
    """Test spatial plot generation."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_spatial"
    
    plot_type = "Spatial Plot"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = SpatialPlot(None, context)
    context.plot_handler = handler
    
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_spatial",
        export_format="png",
        markers=["p16"],
        save=True
    )
    
    assert result.output_root.exists()
    files = list(result.output_root.glob("*.png"))
    # Should generate one plot for p16
    assert len(files) == 1
    assert files[0].name == "test_spatial.png"

def test_spatial_plot_missing_coords(input_data_no_coords, tmp_path):
    """Test spatial plot handles missing coordinates gracefully."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_spatial_fail"
    
    plot_type = "Spatial Plot"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = SpatialPlot(None, context)
    context.plot_handler = handler
    
    result = backend.process(
        plots=[context],
        input_path=str(input_data_no_coords),
        output_path=str(output_dir),
        output_name="test_spatial_fail",
        export_format="png",
        markers=["p16"],
        save=True
    )
    
    # Should produce no output files
    files = list(result.output_root.glob("*.png"))
    assert len(files) == 0

def test_double_expression_plot(input_data, tmp_path):
    """Test double expression plot generation."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_de"
    
    plot_type = "Double Expression"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = DoubleExpressionPlot(None, context)
    context.plot_handler = handler
    
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_de",
        export_format="png",
        markers=["p16", "p21"],
        thresholds={"p16": 20, "p21": 20},
        save=True
    )
    
    assert result.output_root.exists()
    files = list(result.output_root.glob("*.png"))
    assert len(files) == 1
    assert files[0].name == "test_de.png"

def test_double_expression_plot_validation(input_data, tmp_path):
    """Test double expression plot validation logic."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_de_val"
    
    plot_type = "Double Expression"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = DoubleExpressionPlot(None, context)
    context.plot_handler = handler
    
    # Case 1: Only 1 marker
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_de_1",
        export_format="png",
        markers=["p16"],
        save=True
    )
    assert len(list(result.output_root.glob("*.png"))) == 0

    # Case 2: 3 markers
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_de_3",
        export_format="png",
        markers=["p16", "p21", "Ki67"],
        save=True
    )
    assert len(list(result.output_root.glob("*.png"))) == 0

def test_umap_plot(input_data, tmp_path):
    """Test UMAP plot generation."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_umap"
    
    plot_type = "UMAP"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = UMAPPlot(None, context)
    context.plot_handler = handler
    
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_umap",
        export_format="png",
        markers=["p16", "p21", "Ki67"],
        save=True
    )
    
    assert result.output_root.exists()
    files = list(result.output_root.glob("*.png"))
    assert len(files) == 1
    assert files[0].name == "test_umap.png"

def test_backend_save_flag(input_data, tmp_path):
    """Test backend save=False behavior."""
    backend = VisualizationBackend()
    output_dir = tmp_path / "output_nosave"
    
    plot_type = "Spatial Plot"
    data = build_plot_data(plot_type)
    config = PlotConfig(type_name=plot_type, data=data)
    context = MockContext(config, None)
    handler = SpatialPlot(None, context)
    context.plot_handler = handler
    
    result = backend.process(
        plots=[context],
        input_path=str(input_data),
        output_path=str(output_dir),
        output_name="test_nosave",
        export_format="png",
        markers=["p16"],
        save=False,
        cleanup=False
    )
    
    # Output dir should be empty (files not routed)
    assert result.output_root.exists()
    assert len(list(result.output_root.glob("*.png"))) == 0
    
    # Temp dir should contain the file
    plot_temp = result.plot_outputs[0].temp_dir
    assert len(list(plot_temp.glob("*.png"))) == 1