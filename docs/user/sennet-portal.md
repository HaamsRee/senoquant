# SenNet Portal

The **SenNet Portal** tab lets you discover and download SenNet datasets directly from SenoQuant.

It is designed for antibody-based imaging datasets and only allows downloads for files that match SenoQuant-supported image extensions.

## Prerequisites

- `globus-cli` (which provides `globus`) is installed automatically with SenoQuant dependencies.
- `atlas-consortia-clt` (which provides `sennet-clt`) is installed automatically with SenoQuant dependencies.
- Install and configure **Globus Connect Personal (GCP)** for local downloads.
- Use the **Login** button in the **Connection** section to authenticate with Globus.
- (Optional) If you need non-public datasets, provide a bearer token in the tab.

## Connection panel

The **Connection** section includes runtime checks for Globus tools:

- **Globus status** and **Login/Logout** controls for CLI authentication.
- **GCP status** row for local endpoint availability.
- **Install Globus Connect Personal** button when GCP is not detected.
- **Check again** button to refresh status after installing/configuring GCP.

If your environment is behind a corporate firewall, GCP may require a **Setup Key**.
See the official Globus instructions:

- <https://docs.globus.org/globus-connect-personal/troubleshooting-guide/#generating-gcp-setup-key>

## Workflow

1. Open **SenNet Portal**.
2. Choose dataset filters:

    - **Dataset type** (or keep `Any antibody-based imaging`).
    - **Status** (default `Published`).
    - **Max results**.

3. Click **Find datasets**.
4. Review compatible datasets in the table:

    - Only antibody-imaging datasets are included.
    - Only datasets with at least one supported file extension are shown.
    - The table columns are: **SenNet ID**, **Type**, **Source type**, **Organ**, **Age**, **Status**, **Access**, and **Files**.

5. Optionally use the filter row under the table headers:

    - Filters are available for all metadata columns (SenNet ID, Type, Source type, Organ, Age, Status, Access, Files).
    - Filters hide non-matching rows and exclude them from download.

6. Select rows to download:

    - **Select all** / **Clear all** apply only to rows currently visible in the table.
    - **Clear filters** resets all filters and shows all rows again.

7. Set a **Destination** folder.
8. Click **Download selected**.

## Supported extensions

The portal filters files dynamically using the extensions supported by the SenoQuant reader (via BioIO plugin registration).

## Dataset table columns and filters

- **Age column**:

    - `Age` is a best-effort normalized sample age value from SenNet metadata.
    - Age is shown as a display string such as `30 years` or `18 months`.
    - For `Mouse` sources, age is displayed in **months**; for other sources, age is displayed in **years**.
    - If age cannot be derived from available metadata, `Age` is shown as `Unknown`.

- **Age filter**:

    - The Age filter uses **Min** and **Max** numeric fields in the filter row under the `Age` header.
    - Rows match only when their numeric age value is within the specified bounds.
    - Rows with `Unknown` (non-numeric) age are excluded whenever a Min or Max age filter is active.
    - Non-numeric Min/Max inputs are ignored.

- **Filter selection behavior**:

    - When any filter is active, matching rows remain visible and selected, while non-matching rows are hidden and unchecked.
    - **Select all** / **Clear all** affect only currently visible rows.
    - **Clear filters** resets all categorical and age-range filters.

## Notes

- File compatibility is resolved from SenNet Search API `param-search/files`.
- Transfers use SenNet CLI manifest mode internally.
- If your selected destination is outside your home directory, SenoQuant stages the transfer and then moves files into your chosen folder.
- A `sennet_dataset_metadata.json` is written in each dataset output folder, including the full Entity API payload for that dataset.
