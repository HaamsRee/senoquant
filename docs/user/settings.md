# Settings

The Settings tab provides global preferences for the plugin.

## Interface

The Settings tab contains a single checkbox for model preloading behavior.

## Options

### Preload Segmentation Models on Startup

**Control:** Checkbox  
**Default:** Enabled

When enabled, all discovered segmentation models (default_2d, default_3d, cpsam, nuclear_dilation, perinuclear_rings) are instantiated and loaded into memory as soon as the Segmentation tab is opened.

**Benefits:**
- Reduces latency when running segmentation for the first time
- Models are immediately ready for use without initialization delay

**Tradeoffs:**
- Increases plugin startup time (especially with ONNX models)
- Consumes more memory upfront

**When to Disable:**
- Limited system memory
- Working with a single model repeatedly
- Prefer faster initial startup over faster first segmentation

## Persistence

Settings are stored in memory for the current napari session and are not persisted across application restarts. The default behavior is to preload models.
