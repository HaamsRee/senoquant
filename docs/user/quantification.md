# Quantification

The Quantification tab builds a list of features to extract and exports the
results to disk.

## Workflow

1. Click `Add feature` to add a feature block.
2. Set a name and pick a feature type.
3. Configure channels, segmentations, and ROIs as needed.
4. Choose an output path, output name, and format (`csv` or `xlsx`).
5. Click `Process`.

## Feature types

### Markers

Marker features measure channel intensity within segmentation labels.
The configuration supports:

- One or more segmentation label layers.
- One or more image channels (with optional threshold settings).
- Optional ROIs (include or exclude) based on Shapes layers.

### Spots

Spots features export measurements for spot labels. The configuration
supports:

- Optional segmentation filters to restrict spots.
- One or more channels, each with an associated spots labels layer.
- Optional ROIs (include or exclude) based on Shapes layers.
- Optional colocalization export flag.

## Output structure

Quantification output is written to `output_path/output_name` if an output
name is provided. If `output_path` is empty, the current working directory
is used. Each feature exports into its own folder named from the feature
name (or the feature type if no name is provided), with non-alphanumeric
characters replaced for filesystem safety.
