# Data & Readers

SenoQuant registers a napari reader that relies on BioIO. When a file is
opened, the reader first checks if BioIO can determine a plugin for that
file. If so, it loads the data with BioIO and returns napari layers.

## Scenes and channels

- Multi-scene files are opened scene-by-scene.
- Each scene becomes one or more layers, one per channel.
- Layer metadata includes the scene index and name.

## Supported filename patterns

SenoQuant advertises the following filename patterns in `napari.yaml`:

```
*.czi
*.dv
*.r3d
*.264
*.265
*.3fr
*.3g2
*.a64
*.imt
*.mcidas
*.pcx
*.spider
*.xvthumb
*.adp
*.amr
*.amv
*.apng
*.arw
*.asf
*.avc
*.avi
*.avs
*.avs2
*.bay
*.bif
*.bmp
*.cdg
*.cgi
*.cif
*.ct
*.dcr
*.dib
*.dip
*.dng
*.dnxhd
*.dvd
*.erf
*.exr
*.fff
*.gif
*.icb
*.if
*.iiq
*.ism
*.jif
*.jfif
*.jng
*.jp2
*.jpg
*.mov
*.mp4
*.mpo
*.msp
*.pdf
*.png
*.ppm
*.ps
*.zif
*.lif
*.nd2
*.ome.tiff
*.tiff
*.ome.tif
*.tif
*.zarr
*.sldy
*.dir
```

BioIO plugins determine which formats are actually supported at runtime.
If BioIO cannot open a file, napari will fall back to other readers.
