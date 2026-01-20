"""Backend logic for the Quantification tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
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
        Feature type name used for routing (e.g., ``"Marker"``).
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
    Feature processors are registered per feature type and are expected to
    write outputs to the provided temporary directory. After all processors
    run, their outputs are routed into a final output structure.
    """

    def __init__(self) -> None:
        """Initialize the backend with an empty processor registry.

        Attributes
        ----------
        metrics : list
            Placeholder container for computed metrics.
        """
        self.metrics: list[object] = []
        self._processors: dict[str, Callable[[FeatureConfig, Path], Iterable[Path]]] = {}

    def register_processor(
        self,
        feature_type: str,
        processor: Callable[[FeatureConfig, Path], Iterable[Path]],
    ) -> None:
        """Register a feature export processor.

        Parameters
        ----------
        feature_type : str
            Feature type name used in the UI (e.g., ``"Marker"``).
        processor : callable
            Callable that accepts a feature config and a temp directory, and
            returns an iterable of output paths.
        """
        self._processors[feature_type] = processor

    def register_stub_processors(self, feature_types: Iterable[str]) -> None:
        """Register no-op processors for provided feature types.

        Parameters
        ----------
        feature_types : iterable of str
            Feature type names to register with stub processors.

        Notes
        -----
        This is primarily useful while wiring the UI so that processing
        can proceed without feature-specific backends implemented.
        """
        for feature_type in feature_types:
            self.register_processor(feature_type, self._noop_processor)

    @staticmethod
    def _noop_processor(_feature: FeatureConfig, _temp_dir: Path) -> list[Path]:
        """Return an empty output list for placeholder processors."""
        return []

    def process(
        self,
        features: Iterable[FeatureConfig],
        output_path: str,
        output_name: str,
        cleanup: bool = True,
    ) -> QuantificationResult:
        """Run feature exports and route their outputs.

        Parameters
        ----------
        features : iterable of FeatureConfig
            Configured features to export.
        output_path : str
            Base output folder path.
        output_name : str
            Folder name used to group exported outputs.
        cleanup : bool, optional
            Whether to delete temporary export folders after routing.

        Returns
        -------
        QuantificationResult
            Output metadata for the completed run.

        Notes
        -----
        If a processor does not return explicit output paths, the backend
        will move all files found in the feature's temp directory.
        """
        output_root = self._resolve_output_root(output_path, output_name)
        output_root.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="senoquant-quant-"))

        feature_outputs: list[FeatureExportResult] = []
        for feature in features:
            temp_dir = temp_root / feature.feature_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            processor = self._processors.get(feature.type_name)
            outputs: list[Path] = []
            if processor is not None:
                outputs = [Path(path) for path in processor(feature, temp_dir)]
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
        in the temporary directory are routed instead.
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
