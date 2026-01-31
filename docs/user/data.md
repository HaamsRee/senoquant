# Data & File Formats

SenoQuant uses **BioIO** as its primary file reader. BioIO automatically selects the appropriate reader plugin based on the file format, providing seamless support for 50+ microscopy and image formats.

## Reader Behavior

When you open a file in napari with SenoQuant installed:

1. **Format Detection**: BioIO automatically determines the appropriate reader plugin for the file
2. **Scene Processing**: Multi-scene files (e.g., `.lif`, `.czi`) have each scene loaded as separate layers
3. **Channel Splitting**: Each channel within a scene becomes an individual image layer in napari
4. **Metadata Preservation**: Physical pixel sizes, scene names, and channel information are stored in layer metadata

## Scenes and Channels

### Multi-Scene Files

Files with multiple scenes (e.g., Leica `.lif`, Zeiss `.czi`) are processed as follows:

- Each scene is loaded as a separate set of layers
- Layer names include the scene identifier (e.g., `image.lif - Scene 1`)
- Scene metadata is accessible in the layer properties

### Channel Organization

- Each channel becomes a dedicated image layer
- Channels are automatically assigned colormaps from a predefined cycle (blue, green, red, cyan, magenta, yellow)
- Layer names include channel indices for identification (e.g., `image.tif - Channel 0`)
- Blending mode is set to "additive" for multi-channel visualization

## Supported File Formats

SenoQuant advertises support for the following file patterns in its napari reader registration:

### Common Formats
- **TIFF**: `.tif`, `.tiff`, `.ome.tif`, `.ome.tiff`
- **ND2**: `.nd2` (Nikon NIS-Elements)
- **LIF**: `.lif` (Leica Image Format)
- **CZI**: `.czi` (Zeiss)
- **Zarr**: `.zarr` (chunked array storage)

### Additional Formats
`.3fr`, `.3g2`, `.264`, `.265`, `.a64`, `.adp`, `.amr`, `.amv`, `.apng`, `.arw`, `.asf`, `.avc`, `.avi`, `.avs`, `.avs2`, `.bay`, `.bif`, `.bmp`, `.cdg`, `.cgi`, `.cif`, `.ct`, `.dcr`, `.dib`, `.dip`, `.dng`, `.dnxhd`, `.dv`, `.dvd`, `.erf`, `.exr`, `.fff`, `.gif`, `.icb`, `.if`, `.iiq`, `.ism`, `.jfif`, `.jif`, `.jng`, `.jp2`, `.jpg`, `.mcidas`, `.mov`, `.mp4`, `.mpo`, `.msp`, `.pcx`, `.pdf`, `.png`, `.ppm`, `.ps`, `.r3d`, `.sldy`, `.spider`, `.xvthumb`, `.zif`, and more.

**Note**: Actual support depends on installed BioIO reader plugins. If BioIO cannot open a file, napari will attempt to use other available readers.

## BioIO Reader Plugins

SenoQuant relies on BioIO's plugin ecosystem. For best results, install format-specific reader plugins:

```bash
# Common plugins
pip install bioio-tifffile      # General TIFF support
pip install bioio-ome-tiff      # OME-TIFF support
pip install bioio-nd2           # Nikon ND2
pip install bioio-lif           # Leica LIF
pip install bioio-czi           # Zeiss CZI
pip install bioio-bioformats    # Java-based Bio-Formats (many formats)
```

## Metadata Accessibility

Layer metadata includes:

- **`bioio_metadata`**: Full BioIO metadata structure
- **`scene_info`**: Scene identifier, index, and total scene count
- **`path`**: Original file path
- **`channel_index`**: Zero-based channel index
- **`physical_pixel_sizes`**: Physical dimensions in micrometers (X, Y, Z)

Access metadata programmatically:
```python
layer = viewer.layers["image.tif - Channel 0"]
metadata = layer.metadata
scene_name = metadata["scene_info"]["scene_name"]
pixel_size_x = metadata["physical_pixel_sizes"]["X"]
```

## Dimensionality

SenoQuant supports:
- **2D images**: Single Z-plane (YX data)
- **3D images**: Z-stacks (ZYX data)
- **Multi-channel**: Any number of channels per scene
- **Time series**: Currently treated as separate scenes (T dimension not explicitly supported in quantification)

## Fallback Readers

If BioIO cannot determine a reader for your file:
1. SenoQuant returns `None` from its reader function
2. napari automatically tries other installed readers
3. Use napari's built-in readers (e.g., `napari-imread`, `napari-aicsimageio`) as alternatives
