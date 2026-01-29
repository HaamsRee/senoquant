# Quick Start

This walkthrough shows the core workflow in napari.

1. Launch napari and open your image (File -> Open).
2. Open the SenoQuant plugin (Plugins -> SenoQuant).
3. Run segmentation on a nucleus or cytoplasm channel.
4. Run spot detection if needed.
5. Configure quantification features and export metrics.
6. Use Batch for folder-scale processing.

## Segmentation output names

Segmentation writes new labels layers with predictable names:

- Nuclear: `<image layer>_nuclear_labels`
- Cytoplasmic: `<image layer>_cyto_labels`

## Spots output names

Spot detectors create labels layers named:

- `<image layer>_<detector>_labels`

## Colocalization output name

Colocalization adds a points layer named:

- `<labels A>_<labels B>_colocalization`

If a layer with that name already exists, it is replaced.
