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
5. Optionally use the filter row under the table headers:
   - Filters are available for all metadata columns (SenNet ID, Type, Source type, Organ, Status, Access, Files, Extensions).
   - Filters drive row selection through the **Include** checkbox column.
6. Select rows to download (or use **Select all** / **Clear all** to reset filters and update selection).
7. Set a **Destination** folder.
8. Click **Download selected**.

## Supported extensions

The portal filters files dynamically using the extensions supported by the SenoQuant reader (via BioIO plugin registration).

## Notes

- File compatibility is resolved from SenNet Search API `param-search/files`.
- Transfers use SenNet CLI manifest mode internally.
- If your selected destination is outside your home directory, SenoQuant stages the transfer and then moves files into your chosen folder.
- A `senoquant_query_metadata.json` sidecar is written in each dataset output folder.
