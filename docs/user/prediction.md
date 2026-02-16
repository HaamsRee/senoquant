# Prediction

The Prediction tab is where SenoQuant hosts computer-vision models for
senescence-associated feature prediction.

Use this tab to run models that produce prediction layers in napari
(for example, per-pixel score maps or model-derived feature images).

The Prediction tab is designed to be developer-friendly. It's model-agnostic, modular, and flexible, allowing each model to define its own user interface and input selection method. This enables support for a wide range of prediction tasks and model architectures without being constrained by a fixed set of input controls.

Currently, the Prediction tab includes a `demo_model` placeholder to illustrate the model interface and output structure. If you're interested in contributing a new prediction model, see the [developer guide](https://haamsree.github.io/senoquant/developer/prediction/) for implementation details.

## Interface overview

The tab has three parts:

- **Select model** (dropdown): choose a prediction model discovered from
  `src/senoquant/tabs/prediction/models/`.
- **Model interface** (box): displays the model-defined Qt widget.
- **Run** (button): executes the selected model with current widget settings.
  This button sits outside the **Model interface** box.

Unlike Segmentation/Spots, the base Prediction tab does not define input-layer
controls. Each model widget decides how inputs are selected from the viewer.

Tab-level UI source:

- `src/senoquant/tabs/prediction/frontend.py`

## Current placeholder model: `demo_model`

`demo_model` is a minimal example implementation in:

- `src/senoquant/tabs/prediction/models/demo_model/model.py`

Its UI contains:

- **Image layer** (dropdown): picks a napari image layer.
- **Multiplier** (spinbox): scales image values.

Runtime behavior:

1. Reads the selected image layer.
2. Multiplies all values by the multiplier.
3. Clips to the source dtype limits (`uint8`, `uint16`, float, etc.).
4. Adds output as `<layer_name>_demo_model`.

## Output and metadata

Prediction outputs are added as napari layers by:

- `src/senoquant/tabs/prediction/backend.py`

Each output layer receives run metadata in `layer.metadata.run_history`
with:

- task: `prediction`
- runner type: `prediction_model`
- runner name: selected model name
- settings: serialized widget settings

## For developers

To add a new prediction model, place it under:

- `src/senoquant/tabs/prediction/models/<model_name>/model.py`

and subclass:

- `senoquant.tabs.prediction.models.base.SenoQuantPredictionModel`

See the developer guide:

- `docs/developer/prediction.md`
