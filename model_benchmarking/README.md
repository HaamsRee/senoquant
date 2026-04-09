# Model Benchmarking

This is a minimal benchmark for 2D single-channel nuclear segmentation.
It is intentionally narrow:

- input: one 2D image per case
- output: one predicted nuclear mask per case
- comparison: predicted mask vs ground-truth mask
- metrics: Dice and IoU

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
Dice and IoU, plus a final `MEAN` row.

Example CSV:

```csv
case_id,dice,iou,pred_pixels,gt_pixels
sample_01,0.91,0.84,15230,14980
sample_02,0.88,0.79,11102,11740
MEAN,0.895,0.815,,
```
