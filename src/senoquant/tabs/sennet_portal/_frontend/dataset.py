"""Dataset-table and filter UI mixin for the SenNet Portal frontend."""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QTableWidgetItem, QWidget

from senoquant.tabs.sennet_portal.backend import SenNetDataset


def _qt_sort_order_value(order: object) -> int:
    """Normalize Qt sort-order enums across Qt5/Qt6 bindings."""
    if order == getattr(Qt, "DescendingOrder", None):
        return 1
    if order == getattr(Qt, "AscendingOrder", None):
        return 0
    value = getattr(order, "value", order)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class SenNetPortalDatasetMixin:
    """Mixin containing dataset table, selection, and filter helpers."""

    _FILTER_ROW_INDEX = 0
    _TABLE_COLUMN_COUNT = 9
    _AGE_COLUMN = 5
    _CATEGORICAL_FILTER_COLUMNS = (1, 2, 3, 4, 6, 7, 8)
    _SORT_ASC = getattr(Qt, "AscendingOrder", 0)
    _SORT_DESC = getattr(Qt, "DescendingOrder", 1)
    _SORT_ASC_VALUE = _qt_sort_order_value(_SORT_ASC)
    _SORT_DESC_VALUE = _qt_sort_order_value(_SORT_DESC)

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

    def _populate_table(
        self,
        *,
        checked_by_identity: dict[str, object] | None = None,
        preserve_filters: bool = False,
    ) -> None:
        """Render currently loaded datasets into the selection table.

        Parameters
        ----------
        checked_by_identity : dict of str to object or None, optional
            Mapping of dataset identity to checkbox state to preserve when
            rebuilding the table.
        preserve_filters : bool, optional
            Whether existing column-filter values should be restored.
        """
        previous_filters = (
            dict(getattr(self, "_column_filter_values", {})) if preserve_filters else {}
        )
        previous_age_min = (
            self._age_filter_min_input.text().strip()
            if preserve_filters and hasattr(self, "_age_filter_min_input")
            else ""
        )
        previous_age_max = (
            self._age_filter_max_input.text().strip()
            if preserve_filters and hasattr(self, "_age_filter_max_input")
            else ""
        )
        self._dataset_table.setRowCount(1)
        self._column_filter_combos: dict[int, QComboBox] = {}
        self._column_filter_values: dict[int, str] = {}
        self._init_filter_row()

        for dataset in self._datasets:
            row = self._dataset_table.rowCount()
            self._dataset_table.insertRow(row)

            include_item = QTableWidgetItem()
            dataset_id = self._dataset_identity(dataset)
            if checked_by_identity is not None and dataset_id in checked_by_identity:
                include_item.setCheckState(checked_by_identity[dataset_id])
            else:
                include_item.setCheckState(Qt.Checked)
            include_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self._dataset_table.setItem(row, 0, include_item)

            self._dataset_table.setItem(row, 1, self._readonly_item(dataset.sennet_id))
            self._dataset_table.setItem(row, 2, self._readonly_item(dataset.dataset_type))
            self._dataset_table.setItem(row, 3, self._readonly_item(dataset.source_type))
            self._dataset_table.setItem(row, 4, self._readonly_item(dataset.organ))
            self._dataset_table.setItem(row, 5, self._readonly_item(dataset.sample_age))
            self._dataset_table.setItem(row, 6, self._readonly_item(dataset.status))
            self._dataset_table.setItem(row, 7, self._readonly_item(dataset.access_level))
            self._dataset_table.setItem(
                row,
                8,
                self._readonly_item(self._files_column_text(dataset)),
            )

        self._populate_column_filter_combos()
        self._restore_column_filters(previous_filters, previous_age_min, previous_age_max)
        self._apply_column_filters()

    def _init_filter_row(self) -> None:
        """Create filter widgets embedded in the first table row."""
        self._dataset_table.setItem(self._FILTER_ROW_INDEX, 0, self._readonly_item(""))
        for column in self._CATEGORICAL_FILTER_COLUMNS:
            combo = QComboBox()
            combo.addItem("All")
            combo.currentTextChanged.connect(self._on_column_filter_changed)
            self._dataset_table.setCellWidget(self._FILTER_ROW_INDEX, column, combo)
            self._column_filter_combos[column] = combo
            self._column_filter_values[column] = "All"
        self._init_age_range_filter_widget()

    def _init_age_range_filter_widget(self) -> None:
        """Create min/max range filter widget for the Age column."""
        container = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        self._age_filter_min_input = QLineEdit()
        self._age_filter_min_input.setPlaceholderText("Min")
        if hasattr(self._age_filter_min_input, "setMaximumWidth"):
            self._age_filter_min_input.setMaximumWidth(44)
        self._age_filter_min_input.textChanged.connect(self._on_age_filter_changed)
        self._age_filter_max_input = QLineEdit()
        self._age_filter_max_input.setPlaceholderText("Max")
        if hasattr(self._age_filter_max_input, "setMaximumWidth"):
            self._age_filter_max_input.setMaximumWidth(44)
        self._age_filter_max_input.textChanged.connect(self._on_age_filter_changed)
        row.addWidget(self._age_filter_min_input)
        row.addWidget(self._age_filter_max_input)
        container.setLayout(row)
        self._dataset_table.setCellWidget(self._FILTER_ROW_INDEX, self._AGE_COLUMN, container)

    def _populate_column_filter_combos(self) -> None:
        """Populate per-column filter options from current dataset rows."""
        for column in self._CATEGORICAL_FILTER_COLUMNS:
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
    def _files_column_text(dataset: SenNetDataset) -> str:
        """Return user-facing text for the Files column."""
        if dataset.compatible_paths == ["/"]:
            return "All"
        return str(len(dataset.compatible_paths))

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
        """Store active filter values and apply filtering to rows."""
        for column, combo in self._column_filter_combos.items():
            self._column_filter_values[column] = combo.currentText().strip()
        self._apply_column_filters()

    def _on_age_filter_changed(self, _text: str) -> None:
        """Apply table filtering after age range bounds change."""
        self._apply_column_filters()

    def _age_filter_range(self) -> tuple[float | None, float | None]:
        """Return optional numeric min/max bounds from age filter inputs."""
        minimum = self._parse_optional_float(self._age_filter_min_input.text().strip())
        maximum = self._parse_optional_float(self._age_filter_max_input.text().strip())
        return minimum, maximum

    def _apply_column_filters(self) -> None:
        """Apply filters by updating row visibility and include state."""
        age_min, age_max = self._age_filter_range()
        has_active_filter = any(
            active and active != "All" for active in self._column_filter_values.values()
        ) or age_min is not None or age_max is not None
        for row in range(1, self._dataset_table.rowCount()):
            matches = self._row_matches_active_filters(row)
            include_item = self._dataset_table.item(row, 0)
            if include_item is not None and has_active_filter:
                include_item.setCheckState(Qt.Checked if matches else Qt.Unchecked)
            self._dataset_table.setRowHidden(row, not matches)

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

        age_min, age_max = self._age_filter_range()
        if age_min is None and age_max is None:
            return True
        dataset_index = row - 1
        if dataset_index >= len(self._datasets):
            return False
        age_value = self._datasets[dataset_index].sample_age_value
        if age_value is None:
            return False
        if age_min is not None and age_value < age_min:
            return False
        if age_max is not None and age_value > age_max:
            return False
        return True

    def _select_all_datasets(self) -> None:
        """Mark all visible dataset rows as selected."""
        self._set_all_dataset_check_state(Qt.Checked)

    def _clear_all_datasets(self) -> None:
        """Clear selection for all visible dataset rows."""
        self._set_all_dataset_check_state(Qt.Unchecked)

    def _clear_filters(self) -> None:
        """Reset active filters and show all table rows."""
        self._reset_column_filters()

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
        self._age_filter_min_input.blockSignals(True)
        self._age_filter_min_input.setText("")
        self._age_filter_min_input.blockSignals(False)
        self._age_filter_max_input.blockSignals(True)
        self._age_filter_max_input.setText("")
        self._age_filter_max_input.blockSignals(False)
        self._apply_column_filters()

    def _set_all_dataset_check_state(self, state: object) -> None:
        """Apply one checkbox state to every dataset include row.

        Parameters
        ----------
        state : object
            Qt check-state value (for example ``Qt.Checked``).
        """
        for row in range(1, self._dataset_table.rowCount()):
            if self._dataset_table.isRowHidden(row):
                continue
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

    @staticmethod
    def _dataset_identity(dataset: SenNetDataset) -> str:
        """Return stable identity used to preserve row check states."""
        clean_uuid = dataset.dataset_uuid.strip()
        if clean_uuid:
            return f"{dataset.sennet_id}:{clean_uuid}"
        return dataset.sennet_id

    def _checked_states_by_identity(self) -> dict[str, object]:
        """Return checkbox states keyed by stable dataset identity."""
        states: dict[str, object] = {}
        for row in range(1, self._dataset_table.rowCount()):
            dataset_index = row - 1
            if dataset_index >= len(self._datasets):
                continue
            include_item = self._dataset_table.item(row, 0)
            if include_item is None:
                continue
            dataset = self._datasets[dataset_index]
            states[self._dataset_identity(dataset)] = include_item.checkState()
        return states

    def _restore_column_filters(
        self,
        previous_filters: dict[int, str],
        previous_age_min: str,
        previous_age_max: str,
    ) -> None:
        """Restore previously selected filter values when still available."""
        for column, active in previous_filters.items():
            combo = self._column_filter_combos.get(column)
            if combo is None:
                continue
            if combo.findText(active) < 0:
                continue
            combo.blockSignals(True)
            combo.setCurrentText(active)
            combo.blockSignals(False)
            self._column_filter_values[column] = active
        self._age_filter_min_input.blockSignals(True)
        self._age_filter_min_input.setText(previous_age_min)
        self._age_filter_min_input.blockSignals(False)
        self._age_filter_max_input.blockSignals(True)
        self._age_filter_max_input.setText(previous_age_max)
        self._age_filter_max_input.blockSignals(False)

    def _on_table_header_clicked(self, column: int) -> None:
        """Sort datasets by one table column when a header section is clicked."""
        if column < 0 or column >= self._TABLE_COLUMN_COUNT:
            return
        previous_column = getattr(self, "_sort_column", None)
        previous_order = _qt_sort_order_value(getattr(self, "_sort_order", self._SORT_ASC))
        if previous_column == column:
            order = (
                self._SORT_DESC if previous_order == self._SORT_ASC_VALUE else self._SORT_ASC
            )
        else:
            order = self._SORT_ASC

        checked_states = self._checked_states_by_identity()
        self._datasets.sort(
            key=lambda dataset: self._dataset_sort_key(
                dataset,
                column=column,
                checked_states=checked_states,
            ),
            reverse=(_qt_sort_order_value(order) == self._SORT_DESC_VALUE),
        )
        self._sort_column = column
        self._sort_order = order
        self._populate_table(checked_by_identity=checked_states, preserve_filters=True)

        header = self._dataset_table.horizontalHeader()
        if hasattr(header, "setSortIndicator"):
            header.setSortIndicator(column, order)

    def _dataset_sort_key(
        self,
        dataset: SenNetDataset,
        *,
        column: int,
        checked_states: dict[str, object],
    ) -> object:
        """Return sorting key for one dataset and target table column."""
        if column == 0:
            checked = checked_states.get(self._dataset_identity(dataset), Qt.Checked)
            return int(checked != Qt.Checked)
        if column == 1:
            return dataset.sennet_id.lower()
        if column == 2:
            return dataset.dataset_type.lower()
        if column == 3:
            return dataset.source_type.lower()
        if column == 4:
            return dataset.organ.lower()
        if column == 5:
            return dataset.sample_age_value if dataset.sample_age_value is not None else float("inf")
        if column == 6:
            return dataset.status.lower()
        if column == 7:
            return dataset.access_level.lower()
        if column == 8:
            return len(dataset.compatible_paths)
        return dataset.sennet_id.lower()

    @staticmethod
    def _parse_optional_float(text: str) -> float | None:
        """Parse one optional float filter bound from user input."""
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None


__all__ = ["SenNetPortalDatasetMixin"]
