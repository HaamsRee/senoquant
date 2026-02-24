"""Dataset-table and filter UI mixin for the SenNet Portal frontend."""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QComboBox, QTableWidgetItem

from senoquant.tabs.sennet_portal.backend import SenNetDataset


class SenNetPortalDatasetMixin:
    """Mixin containing dataset table, selection, and filter helpers."""

    _FILTER_ROW_INDEX = 0
    _TABLE_COLUMN_COUNT = 9

    def _refresh_dataset_types(self) -> None:
        """Fetch and repopulate available antibody dataset-type options."""
        self._run_background(
            button=self._refresh_dataset_types_button,
            busy_text="Refreshing...",
            run_callable=lambda: self._backend.available_antibody_dataset_types(
                token=self._token_input.text().strip() or None,
            ),
            on_success=self._on_dataset_types_refreshed,
            on_error_prefix="Dataset-type refresh failed",
        )

    def _on_dataset_types_refreshed(self, dataset_types: list[str]) -> None:
        """Update dataset-type combo with backend-discovered values.

        Parameters
        ----------
        dataset_types : list of str
            Dataset-type options returned by backend discovery.
        """
        clean_types = [str(value).strip() for value in dataset_types if str(value).strip()]
        if not clean_types:
            clean_types = list(self._backend.ANTIBODY_DATASET_TYPES)
        clean_types = sorted(set(clean_types))
        self._dataset_type_options = clean_types

        previous = self._dataset_type_combo.currentText().strip()
        self._dataset_type_combo.clear()
        self._dataset_type_combo.addItem("Any antibody-based imaging")
        self._dataset_type_combo.addItems(clean_types)
        if previous == "Any antibody-based imaging":
            self._dataset_type_combo.setCurrentText(previous)
            return
        if previous in clean_types:
            self._dataset_type_combo.setCurrentText(previous)

    def _populate_table(self) -> None:
        """Render currently loaded datasets into the selection table."""
        self._dataset_table.setRowCount(1)
        self._column_filter_combos: dict[int, QComboBox] = {}
        self._column_filter_values: dict[int, str] = {}
        self._init_filter_row()

        for dataset in self._datasets:
            row = self._dataset_table.rowCount()
            self._dataset_table.insertRow(row)

            include_item = QTableWidgetItem()
            include_item.setCheckState(Qt.Checked)
            include_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self._dataset_table.setItem(row, 0, include_item)

            self._dataset_table.setItem(row, 1, self._readonly_item(dataset.sennet_id))
            self._dataset_table.setItem(row, 2, self._readonly_item(dataset.dataset_type))
            self._dataset_table.setItem(row, 3, self._readonly_item(dataset.source_type))
            self._dataset_table.setItem(row, 4, self._readonly_item(dataset.organ))
            self._dataset_table.setItem(row, 5, self._readonly_item(dataset.status))
            self._dataset_table.setItem(row, 6, self._readonly_item(dataset.access_level))
            self._dataset_table.setItem(
                row,
                7,
                self._readonly_item(str(len(dataset.compatible_paths))),
            )
            self._dataset_table.setItem(
                row,
                8,
                self._readonly_item(", ".join(dataset.compatible_extensions)),
            )

        self._populate_column_filter_combos()
        self._apply_column_filters_to_selection()

    def _init_filter_row(self) -> None:
        """Create filter widgets embedded in the first table row."""
        self._dataset_table.setItem(self._FILTER_ROW_INDEX, 0, self._readonly_item(""))
        for column in range(1, self._TABLE_COLUMN_COUNT):
            combo = QComboBox()
            combo.addItem("All")
            combo.currentTextChanged.connect(self._on_column_filter_changed)
            self._dataset_table.setCellWidget(self._FILTER_ROW_INDEX, column, combo)
            self._column_filter_combos[column] = combo
            self._column_filter_values[column] = "All"

    def _populate_column_filter_combos(self) -> None:
        """Populate per-column filter options from current dataset rows."""
        for column in range(1, self._TABLE_COLUMN_COUNT):
            combo = self._column_filter_combos.get(column)
            if combo is None:
                continue
            values: set[str] = set()
            for row in range(1, self._dataset_table.rowCount()):
                item = self._dataset_table.item(row, column)
                if item is None:
                    continue
                text = item.text().strip()
                if text:
                    values.add(text)
            self._replace_combo_items(combo, ["All", *sorted(values)])

    @staticmethod
    def _replace_combo_items(combo: QComboBox, items: list[str]) -> None:
        """Replace all options in a combo box while preserving prior value."""
        previous = combo.currentText().strip()
        combo.clear()
        combo.addItems(items)
        if previous in items:
            combo.setCurrentText(previous)
            return
        if items:
            combo.setCurrentText(items[0])

    def _on_column_filter_changed(self, _text: str) -> None:
        """Store active filter values and apply selection filtering."""
        for column, combo in self._column_filter_combos.items():
            self._column_filter_values[column] = combo.currentText().strip()
        self._apply_column_filters_to_selection()

    def _apply_column_filters_to_selection(self) -> None:
        """Select dataset rows that match all active column filters."""
        for row in range(1, self._dataset_table.rowCount()):
            include_item = self._dataset_table.item(row, 0)
            if include_item is None:
                continue
            matches = self._row_matches_active_filters(row)
            include_item.setCheckState(Qt.Checked if matches else Qt.Unchecked)

    def _row_matches_active_filters(self, row: int) -> bool:
        """Return whether one table row satisfies all active filters.

        Parameters
        ----------
        row : int
            Table row index for a dataset row.

        Returns
        -------
        bool
            ``True`` when row values satisfy every active column filter.
        """
        for column, active in self._column_filter_values.items():
            if not active or active == "All":
                continue

            item = self._dataset_table.item(row, column)
            text = item.text().strip() if item is not None else ""
            if text != active:
                return False
        return True

    def _select_all_datasets(self) -> None:
        """Mark all dataset rows as selected."""
        self._reset_column_filters()
        self._set_all_dataset_check_state(Qt.Checked)

    def _clear_all_datasets(self) -> None:
        """Clear dataset selection for all rows."""
        self._reset_column_filters()
        self._set_all_dataset_check_state(Qt.Unchecked)

    def _reset_column_filters(self) -> None:
        """Reset all active column filters back to ``All``."""
        combos = getattr(self, "_column_filter_combos", {})
        if not isinstance(combos, dict):
            return
        for column, combo in combos.items():
            combo.blockSignals(True)
            combo.setCurrentText("All")
            combo.blockSignals(False)
            self._column_filter_values[column] = "All"
        self._apply_column_filters_to_selection()

    def _set_all_dataset_check_state(self, state: int) -> None:
        """Apply one checkbox state to every dataset include row.

        Parameters
        ----------
        state : int
            Qt check-state value (for example ``Qt.Checked``).
        """
        for row in range(1, self._dataset_table.rowCount()):
            include_item = self._dataset_table.item(row, 0)
            if include_item is None:
                continue
            include_item.setCheckState(state)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        """Return a non-editable table item for display-only columns."""
        item = QTableWidgetItem(text)
        flags = Qt.ItemIsEnabled
        selectable = getattr(Qt, "ItemIsSelectable", 0)
        if isinstance(selectable, int) and selectable:
            flags |= selectable
        item.setFlags(flags)
        return item

    def _selected_datasets(self) -> list[SenNetDataset]:
        """Collect datasets whose include checkbox is enabled."""
        selected: list[SenNetDataset] = []
        for row in range(1, self._dataset_table.rowCount()):
            include_item = self._dataset_table.item(row, 0)
            if include_item is None:
                continue
            if include_item.checkState() != Qt.Checked:
                continue
            dataset_index = row - 1
            if dataset_index < len(self._datasets):
                selected.append(self._datasets[dataset_index])
        return selected


__all__ = ["SenNetPortalDatasetMixin"]
