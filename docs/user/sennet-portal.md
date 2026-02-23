# SenNet Portal

The **SenNet Portal** tab lets you discover and download SenNet datasets directly from SenoQuant.

It is designed for antibody-based imaging datasets and only allows downloads for files that match SenoQuant-supported image extensions.

## Prerequisites

- Install the SenNet CLI (`sennet-clt`) from the SenNet docs.
- Install the Globus CLI (`globus-cli`) and authenticate:

```bash
globus login
```

- Authenticate once from a terminal:

```bash
sennet-clt login
```

- (Optional) If you need non-public datasets, provide a bearer token in the tab.

## Workflow

1. Open **SenNet Portal**.
2. Check **Globus status** in the Connection section.
   - If not logged in, click **Login**.
   - If already logged in, you can click **Logout** to switch accounts.
3. Choose dataset filters:
   - **Dataset type** (or keep `Any antibody-based imaging`).
   - **Status** (default `Published`).
   - **Max results**.
4. Click **Find datasets**.
   - If Globus login is missing, a prompt appears with **Login** and **Cancel**.
   - Click **Login** to launch `globus login` and continue.
5. Review compatible datasets in the table:
   - Only antibody-imaging datasets are included.
   - Only datasets with at least one supported file extension are shown.
6. Select rows to download.
7. Set a **Destination** folder.
8. Click **Download selected**.

## Supported extensions

The portal currently accepts:

- `.ome.tif`, `.ome.tiff`
- `.tif`, `.tiff`
- `.png`, `.jpg`, `.jpeg`
- `.czi`, `.nd2`, `.lif`
- `.zarr`

## Notes

- Transfers use SenNet CLI manifest mode internally.
- If your selected destination is outside your home directory, SenoQuant stages the transfer and then moves files into your chosen folder.
