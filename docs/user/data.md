# Data & File Formats

SenoQuant uses [**BioIO**](https://github.com/bioio-devs/bioio) as its primary file reader. BioIO automatically selects the appropriate reader plugin based on the file format, providing seamless support for most common microscopy and image formats.

## Reader behavior

When you open a file in napari with SenoQuant installed:

1. **Format detection**: BioIO automatically determines the appropriate reader plugin for the file.
2. **Scene processing**: Multi-scene files (e.g., `.lif`, `.czi`) have each scene loaded as separate layers.
3. **Channel splitting**: Each channel within a scene becomes an individual image layer in napari.
4. **Metadata preservation**: Physical pixel sizes, scene names, channel information, file path, etc., are stored in layer metadata.

## Scenes and channels

### Multi-scene files

Files with multiple scenes (e.g., Leica `.lif`, Zeiss `.czi`) are processed as follows:

- Each scene is loaded as a separate set of layers.
- Layer names include the scene identifier (e.g., `image.lif - Scene 1`).
- Scene metadata is accessible in the layer properties.

### Channel organization

- Each channel becomes a dedicated image layer.
- Channels are automatically assigned colormaps from a predefined cycle (blue, green, red, cyan, magenta, yellow).
- Layer names include channel indices for identification (e.g., `image.tif - Channel 0`).
- Blending mode is set to "additive" for multi-channel visualization.

## Supported file formats

SenoQuant supports the following file patterns:

### Common formats
- **TIFF**: `.tif`, `.tiff`, `.ome.tif`, `.ome.tiff`.
- **ND2**: `.nd2` (Nikon NIS-Elements).
- **LIF**: `.lif` (Leica Image Format).
- **CZI**: `.czi` (Zeiss).
- **Zarr**: `.zarr` (chunked array storage).

### Additional formats
See the [BioIO documentation](https://bioio-devs.github.io/bioio/) for a full list of supported formats via plugins. SenoQuant includes:

- bioio-czi
- bioio-dv
- bioio-imageio
- bioio-lif
- bioio-nd2
- bioio-ome-tiff
- bioio-ome-zarr
- bioio-sldy
- bioio-tifffile
- bioio-tiff-glob


> **Note**: Actual support depends on installed BioIO reader plugins. If BioIO cannot open a file, napari will attempt to use other available readers. Additional formats may be supported upon request.

## Metadata accessibility

Layer metadata includes:

- **`bioio_metadata`**: Full BioIO metadata structure.
- **`scene_info`**: Scene identifier, index, and total scene count.
- **`path`**: Original file path.
- **`channel_index`**: Zero-based channel index.
- **`physical_pixel_sizes`**: Physical dimensions in micrometers (X, Y, Z).

Access metadata programmatically"

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

If BioIO cannot determine a reader for your file:

1. SenoQuant returns `None` from its reader function.
2. napari automatically tries other installed readers.
3. Use napari's built-in readers, or install plugins from napari's Plugin Manager as alternatives.

> **Warning**: Metadata-based quantification features (e.g., ones associated with physical units) will not work correctly if the SenoQuant reader is bypassed.
