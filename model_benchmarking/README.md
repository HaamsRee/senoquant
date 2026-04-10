# Model Benchmarking

This benchmark is a small, file-based workflow for 2D single-channel nuclear
segmentation. It uses instance segmentation metrics:

- Objects are matched by IoU
- Metrics are computed from matched instances, not foreground pixels
- One run can evaluate multiple IoU thresholds

For this benchmark:

- Input: one 2D image per case
- Output: one predicted nuclear instance mask per case
- Comparison: predicted instances vs. ground-truth instances
- Metrics: `precision`, `recall`, `jaccard`, and `dice`

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

The benchmark script reads:

- `.npy`
- `.npz` containing exactly one array
- `.tif`
- `.tiff`

Each image and mask must be 2D.

Ground truth and predictions can be instance label images. Binary masks also
work: they are converted to connected components before instance matching.

## Running a benchmark

Run a built-in SenoQuant segmentation model:

```bash
conda activate senoquant-dev
python model_benchmarking/benchmark_nuclear_segmentation.py --model cpsam
```

By default the benchmark evaluates IoU thresholds `0.5 0.6 0.7 0.8 0.9`.

To choose your own thresholds:

```bash
python model_benchmarking/benchmark_nuclear_segmentation.py \
  --model cpsam \
  --iou-thresholds 0.5 0.75 0.9
```

For an interactive workflow, open:

- `model_benchmarking/benchmark_nuclear_segmentation.ipynb`

The notebook still imports `run_benchmark`, `write_csv`, and
`write_summary_plot` from the script entrypoint.

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

The script writes `model_benchmarking/results/<model_name>.csv`.

Each CSV contains:

- one `case` row per image and IoU threshold
- one `dataset_summary` row per IoU threshold

The dataset summary rows aggregate instance counts across the full dataset, so
the reported metrics reflect per-instance performance instead of averaging
per-image scores.

The CSV also includes instance counts (`n_true`, `n_pred`, `tp`, `fp`, `fn`)
for context, but the only reported metrics are `precision`, `recall`,
`jaccard`, and `dice`.

Example CSV:

```csv
row_type,case_id,model,criterion,iou_threshold,n_true,n_pred,tp,fp,fn,precision,recall,jaccard,dice
case,sample_01,cpsam,iou,0.5,42,44,39,5,3,0.8863636364,0.9285714286,0.829787234,0.9069767442
case,sample_01,cpsam,iou,0.75,42,44,34,10,8,0.7727272727,0.8095238095,0.6538461538,0.7906976744
dataset_summary,DATASET,cpsam,iou,0.5,1014,1038,946,92,68,0.9113680154,0.932938856,0.8552532723,0.9221153846
dataset_summary,DATASET,cpsam,iou,0.75,1014,1038,861,177,153,0.8294797688,0.849112426,0.7231332219,0.8395316804
```

## Plotting

The summary plot reads every compatible CSV in `model_benchmarking/results/`
and draws one threshold curve per model for these metrics:

- `precision`
- `recall`
- `jaccard`
- `dice`

This makes it easy to compare models across both metric type and IoU threshold.

If you want to override the plot path or title:

```bash
python model_benchmarking/benchmark_nuclear_segmentation.py \
  --model cpsam \
  --plot model_benchmarking/results/my_plot.png \
  --plot-title dataset_DAPI
```
