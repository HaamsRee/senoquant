# Data & File Formats

SenoQuant uses [**BioIO**](https://github.com/bioio-devs/bioio) with [**bioio-bioformats**](https://github.com/bioio-devs/bioio-bioformats) as its primary file reader, which provides access to the full [BioFormats](https://docs.openmicroscopy.org/bio-formats/5.8.2/supported-formats.html) ecosystem of microscopy formats. This unified reader automatically handles most common microscopy and image formats.

## Reader behavior

When you open a file in napari with SenoQuant installed:

1. **Format detection**: bioio-bioformats automatically determines the appropriate format handler.
3. **Scene processing**: Multi-scene files (e.g., `.lif`, `.czi`) have each scene loaded as separate layers.
4. **Channel splitting**: Each channel within a scene becomes an individual image layer in napari.
5. **Colormap detection**: Channel colors from OME metadata are used when available; otherwise falls back to a default colormap cycle.
6. **Metadata preservation**: Physical pixel sizes, scene names, channel information, file path, etc., are stored in layer metadata.

## Channel colormaps

### OME metadata colors

When OME metadata is present in the image file, SenoQuant extracts channel colors and applies them as custom colormaps:

- Each channel gets a colormap ranging from black to its specified color.
- If all channels have the same color (e.g., all "white"), falls back to the default colormap cycle.

### Default colormap cycle

When OME colors are not available or all channels share the same color, channels are assigned colormaps from a predefined cycle:

- blue, green, red, yellow, cyan, bop blue, bop orange, bop purple

## Scenes and channels

### Multi-scene files

Files with multiple scenes (e.g., Leica `.lif`, Zeiss `.czi`) are processed as follows:

- Each scene is loaded as a separate set of layers.
- Layer names include the scene identifier (e.g., `image.lif - Scene 1`).
- Scene metadata is accessible in the layer properties.

### Channel organization

- Each channel becomes a dedicated image layer.
- Layer names include channel indices for identification (e.g., `image.tif - Channel 0`).
- Blending mode is set to "additive" for multi-channel visualization.

## Supported file formats

SenoQuant supports most common file formats via BioFormats, including:

- **Zeiss CZI**: `.czi`
- **Leica LIF**: `.lif`
- **Nikon ND2**: `.nd2`
- **OME-TIFF**: `.ome.tiff`, `.ome.tif`, `.ome.tf2`, `.ome.tf8`, `.ome.btf`
- **TIFF**: `.tiff`, `.tif`, `.tf2`, `.tf8`, `.btf`
- **PNG/JPEG**: `.png`, `.jpg`
- **And many more**: See the [BioFormats supported formats](https://docs.openmicroscopy.org/bio-formats/5.8.2/supported-formats.html) list.

> **Note**: If you have a file that SenoQuant cannot open, please submit an issue on GitHub with the file format and sample data if possible, and we will work on adding support.

## Metadata accessibility

Layer metadata includes:

- **`bioio_metadata`**: Full BioIO metadata structure.
- **`scene_info`**: Scene identifier, index, and total scene count.
- **`path`**: Original file path.
- **`channel_index`**: Zero-based channel index.
- **`physical_pixel_sizes`**: Physical dimensions in micrometers (X, Y, Z).

Access metadata programmatically:

```python
layer = viewer.layers["image.tif - Channel 0"]
metadata = layer.metadata
scene_name = metadata["scene_info"]["scene_name"]
pixel_size_x = metadata["physical_pixel_sizes"]["X"]
```

## Dimensionality

SenoQuant supports:

- **2D images**: Single Z-plane (YX data).
- **3D images**: Z-stacks (ZYX data).
- **Multi-channel**: Any number of channels per scene.

## Fallback readers

If SenoQuant cannot open your file:

1. napari automatically tries other installed readers.
2. Use napari's built-in readers, or install plugins from napari's Plugin Manager as alternatives.

> **Warning**: Metadata-based quantification features (e.g., ones associated with physical units) will not work correctly if the SenoQuant reader is bypassed.
