# Model Benchmarking

This is a minimal benchmark for 2D single-channel nuclear segmentation.
It is intentionally narrow:

- input: one 2D image per case
- output: one predicted nuclear mask per case
- comparison: predicted mask vs ground-truth mask
- metrics: Precision, Recall, F1, Jaccard, and Dice

## Folder layout

Put input images here:

- `model_benchmarking/images/`

Put ground-truth masks here:

- `model_benchmarking/ground_truth/`

Optional external models go here:

- `model_benchmarking/models/`

Results are written here by default:

- `model_benchmarking/results/`

## File matching

Files are matched by basename, so `images/sample_01.tif` is compared against
`ground_truth/sample_01.tif`.

This also works for names with multiple suffixes. For example:

- `images/sample_01.ome.tif`
- `ground_truth/sample_01.npy`

Both are treated as the same case: `sample_01`.

## Supported file formats

The benchmark script currently reads:

- `.npy`
- `.npz` containing exactly one array
- `.tif`
- `.tiff`

Each image and mask must be 2D.

## Running a benchmark

Run a built-in SenoQuant segmentation model:

```bash
conda activate senoquant-dev
python model_benchmarking/benchmark_nuclear_segmentation.py --model cpsam
```

For an interactive workflow, open:

- `model_benchmarking/benchmark_nuclear_segmentation.ipynb`

The notebook is set up in batch format by default. Edit the `model_specs` list
to benchmark multiple models in one run. It currently pre-populates the built-in
2D-compatible nuclear models `cpsam` and `default_2d`.

The script also writes or updates a summary plot at:

- `model_benchmarking/results/benchmark_summary.png`

## External models

Run a model outside `src`:

```bash
python model_benchmarking/benchmark_nuclear_segmentation.py \
  --model my_model \
  --models-root model_benchmarking/models
```

External models should use the normal SenoQuant segmentation layout:

```text
model_benchmarking/models/my_model/
  details.json
  model.py
```

The benchmark always calls the model as:

```python
model.run(task="nuclear", layer=ImageLayer(image), settings=settings)
```

So this is only for nuclear models that accept the normal segmentation API.

## Settings

Optional model settings can be passed with a JSON file:

```bash
python model_benchmarking/benchmark_nuclear_segmentation.py \
  --model cpsam \
  --settings-json model_benchmarking/settings.json
```

Example:

```json
{
  "diameter": 30,
  "flow_threshold": 0.4
}
```

## Output

The script writes `model_benchmarking/results/<model_name>.csv` with per-image
metrics plus a final `MEAN` row.

Example CSV:

```csv
case_id,model,precision,recall,f1,jaccard,dice,pred_pixels,gt_pixels
sample_01,cpsam,0.93,0.89,0.91,0.84,0.91,15230,14980
sample_02,cpsam,0.9,0.86,0.88,0.79,0.88,11102,11740
MEAN,cpsam,0.915,0.875,0.895,0.815,0.895,,
```

It also writes a grouped bar chart PNG that summarizes the `MEAN` rows from all
benchmark CSVs currently in `model_benchmarking/results/`. This is what lets
multiple models appear together in one comparison figure.

If you want to override the plot path or title:

```bash
python model_benchmarking/benchmark_nuclear_segmentation.py \
  --model cpsam \
  --plot model_benchmarking/results/my_plot.png \
  --plot-title dataset_DAPI
```

For binary foreground segmentation, F1 and Dice are numerically the same, so
those two columns in the CSV and plot will match.
