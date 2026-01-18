"""Colocalization feature UI."""

from ..base import SenoQuantFeature


class ColocalizationFeature(SenoQuantFeature):
    """Colocalization feature controls."""

    def build(self) -> None:
        """Build the colocalization feature UI."""
        self._tab._build_colocalization_section(self._config)
