"""Backend logic for the Quantification tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import shutil
import tempfile

from .features import FeatureConfig


@dataclass
class FeatureExportResult:
    """Output metadata for a single feature export.

    Attributes
    ----------
    feature_id : str
        Stable identifier for the exported feature instance.
    feature_type : str
        Feature type name used for routing (e.g., ``"Markers"``).
    feature_name : str
        Display name provided by the user.
    temp_dir : Path
        Temporary directory where the feature wrote its outputs.
    outputs : list of Path
        Explicit file paths returned by the feature processor.
    """

    feature_id: str
    feature_type: str
    feature_name: str
    temp_dir: Path
    outputs: list[Path] = field(default_factory=list)


@dataclass
class QuantificationResult:
    """Aggregated output information for a quantification run.

    Attributes
    ----------
    output_root : Path
        Root output directory for the run.
    temp_root : Path
        Temporary root directory used during processing.
    feature_outputs : list of FeatureExportResult
        Per-feature export metadata for the run.
    """

    output_root: Path
    temp_root: Path
    feature_outputs: list[FeatureExportResult]


class QuantificationBackend:
    """Backend orchestrator for quantification exports.

    Notes
    -----
    Feature export routines live with their feature implementations. The
    backend iterates through configured feature contexts, asks each feature
    handler to export into a temporary directory, and then routes those
    outputs into a final output structure.
    """

    def __init__(self) -> None:
        """Initialize the backend state.

        Attributes
        ----------
        metrics : list
            Placeholder container for computed metrics.
        """
        self.metrics: list[object] = []

    def process(
        self,
        features: Iterable[object],
        output_path: str,
        output_name: str,
        export_format: str,
        cleanup: bool = True,
    ) -> QuantificationResult:
        """Run feature exports and route their outputs.

        Parameters
        ----------
        features : iterable of object
            Feature UI contexts with ``state`` and ``feature_handler``.
            Each handler should implement ``export(temp_dir, export_format)``.
        output_path : str
            Base output folder path.
        output_name : str
            Folder name used to group exported outputs.
        export_format : str
            File format requested by the user (``"csv"`` or ``"xlsx"``).
        cleanup : bool, optional
            Whether to delete temporary export folders after routing.

        Returns
        -------
        QuantificationResult
            Output metadata for the completed run.

        Notes
        -----
        If a feature export does not return explicit output paths, the backend
        will move all files found in the feature's temp directory. This allows
        feature implementations to either return specific files or simply write
        into the provided temporary directory.
        """
        output_root = self._resolve_output_root(output_path, output_name)
        output_root.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="senoquant-quant-"))

        feature_outputs: list[FeatureExportResult] = []
        for context in features:
            feature = getattr(context, "state", None)
            handler = getattr(context, "feature_handler", None)
            if not isinstance(feature, FeatureConfig):
                continue
            temp_dir = temp_root / feature.feature_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            outputs: list[Path] = []
            if handler is not None and hasattr(handler, "export"):
                outputs = [
                    Path(path)
                    for path in handler.export(temp_dir, export_format)
                ]
            feature_outputs.append(
                FeatureExportResult(
                    feature_id=feature.feature_id,
                    feature_type=feature.type_name,
                    feature_name=feature.name,
                    temp_dir=temp_dir,
                    outputs=outputs,
                )
            )

        self._route_feature_outputs(output_root, feature_outputs)
        if cleanup:
            shutil.rmtree(temp_root, ignore_errors=True)
        return QuantificationResult(
            output_root=output_root,
            temp_root=temp_root,
            feature_outputs=feature_outputs,
        )

    def _resolve_output_root(self, output_path: str, output_name: str) -> Path:
        """Resolve the final output root directory.

        Parameters
        ----------
        output_path : str
            Base output folder path.
        output_name : str
            Folder name used to group exported outputs.

        Returns
        -------
        Path
            Resolved output directory path.
        """
        base = Path(output_path) if output_path else Path.cwd()
        if output_name:
            return base / output_name
        return base

    def _route_feature_outputs(
        self,
        output_root: Path,
        feature_outputs: Iterable[FeatureExportResult],
    ) -> None:
        """Move feature outputs from temp folders to the final location.

        Parameters
        ----------
        output_root : Path
            Destination root folder.
        feature_outputs : iterable of FeatureExportResult
            Export results to route.

        Notes
        -----
        When a feature returns no explicit output list, all files present
        in the temporary directory are routed instead. Subdirectories are
        not traversed.
        """
        for feature_output in feature_outputs:
            feature_dir = output_root / self._feature_dir_name(feature_output)
            feature_dir.mkdir(parents=True, exist_ok=True)
            outputs = feature_output.outputs
            if outputs:
                for path in outputs:
                    if path.exists():
                        shutil.move(str(path), feature_dir / path.name)
            else:
                for path in feature_output.temp_dir.glob("*"):
                    if path.is_file():
                        shutil.move(str(path), feature_dir / path.name)

    def _feature_dir_name(self, feature_output: FeatureExportResult) -> str:
        """Build a filesystem-friendly folder name for a feature.

        Parameters
        ----------
        feature_output : FeatureExportResult
            Export result metadata.

        Returns
        -------
        str
            Directory name for the feature outputs.

        Notes
        -----
        Non-alphanumeric characters are replaced to avoid filesystem issues.
        """
        name = feature_output.feature_name.strip()
        if not name:
            name = feature_output.feature_type
        safe = "".join(
            char if char.isalnum() or char in "-_ " else "_" for char in name
        )
        return safe.replace(" ", "_").lower()
