"""Connection and authentication UI mixin for the SenNet Portal frontend."""

from __future__ import annotations

from qtpy.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SenNetPortalConnectionMixin:
    """Mixin containing connection/auth widgets and Globus auth handlers."""

    def _make_connection_section(self) -> QGroupBox:
        """Create connection controls used for optional API authentication.

        Returns
        -------
        QGroupBox
            Group box containing bearer-token input.
        """
        section = QGroupBox("Connection")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText(
            "Optional API bearer token (leave blank for public datasets)"
        )
        form_layout.addRow("API token", self._token_input)

        self._globus_status_label = QLabel("Checking Globus login status...")
        self._globus_login_button = QPushButton("Login")
        self._globus_login_button.clicked.connect(self._login_globus_from_ui)
        self._globus_logout_button = QPushButton("Logout")
        self._globus_logout_button.clicked.connect(self._logout_globus_from_ui)

        globus_buttons = QHBoxLayout()
        globus_buttons.setContentsMargins(0, 0, 0, 0)
        globus_buttons.addWidget(self._globus_login_button)
        globus_buttons.addWidget(self._globus_logout_button)
        globus_widget = QWidget()
        globus_widget.setLayout(globus_buttons)

        form_layout.addRow("Globus status", self._globus_status_label)
        form_layout.addRow("Globus auth", globus_widget)
        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _refresh_globus_auth_status(self) -> None:
        """Refresh Globus login label text and Login/Logout button state.

        Returns
        -------
        None
            Connection section widgets are updated in-place.
        """
        logged_in, detail = self._backend.globus_login_status()
        if detail == "Globus CLI not found":
            self._globus_status_label.setText("Globus CLI not installed")
            self._globus_login_button.setEnabled(False)
            self._globus_logout_button.setEnabled(False)
            return

        if logged_in:
            self._globus_status_label.setText(f"Logged in as {detail}")
            self._globus_login_button.setEnabled(False)
            self._globus_logout_button.setEnabled(True)
            return

        self._globus_status_label.setText("Not logged in")
        self._globus_login_button.setEnabled(True)
        self._globus_logout_button.setEnabled(False)

    def _login_globus_from_ui(self) -> None:
        """Start Globus login from the connection section button.

        Returns
        -------
        None
            Login runs asynchronously and updates status on completion.
        """
        self._run_background(
            button=self._globus_login_button,
            busy_text="Logging in...",
            run_callable=self._backend.login_globus,
            on_success=self._on_globus_login_complete,
            on_error_prefix="Globus login failed",
        )

    def _logout_globus_from_ui(self) -> None:
        """Start Globus logout from the connection section button.

        Returns
        -------
        None
            Logout runs asynchronously and updates status on completion.
        """
        self._run_background(
            button=self._globus_logout_button,
            busy_text="Logging out...",
            run_callable=self._backend.logout_globus,
            on_success=self._on_globus_logout_complete,
            on_error_prefix="Globus logout failed",
        )

    def _on_globus_login_complete(self, _result: object) -> None:
        """Update UI after successful background Globus login.

        Parameters
        ----------
        _result : object
            Worker payload (unused).

        Returns
        -------
        None
            Status label and notifications are refreshed.
        """
        self._refresh_globus_auth_status()
        self._notify("Globus login successful.")

    def _on_globus_logout_complete(self, _result: object) -> None:
        """Update UI after successful background Globus logout.

        Parameters
        ----------
        _result : object
            Worker payload (unused).

        Returns
        -------
        None
            Status label and notifications are refreshed.
        """
        self._refresh_globus_auth_status()
        self._notify("Globus logout successful.")

    def _ensure_globus_login_for_search(self) -> bool:
        """Ensure Globus login is present before starting dataset search.

        Returns
        -------
        bool
            ``True`` when search can proceed, otherwise ``False``.
        """
        try:
            self._backend._require_globus_login_for_search()
            return True
        except RuntimeError as exc:
            message = str(exc).strip()
            lowered = message.lower()
            if "globus login is required" not in lowered:
                self._notify(f"Dataset search failed: {message}")
                return False

        if not self._prompt_globus_login():
            self._notify("Dataset search cancelled. Globus login is required.")
            return False

        self._notify("Starting Globus login...")
        try:
            self._backend.login_globus()
            self._backend._require_globus_login_for_search()
        except RuntimeError as exc:
            self._notify(f"Dataset search failed: {exc}")
            return False
        self._refresh_globus_auth_status()
        return True

    def _prompt_globus_login(self) -> bool:
        """Show login prompt when Globus authentication is missing.

        Returns
        -------
        bool
            ``True`` when user selected **Login**, otherwise ``False``.
        """
        try:
            from qtpy.QtWidgets import QMessageBox
        except Exception:
            return False

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Globus Login Required")
        dialog.setText("You must log in to Globus before searching datasets.")
        dialog.setInformativeText("Click Login to run `globus login`, or Cancel to stop.")
        login_button = dialog.addButton("Login", QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(login_button)
        dialog.exec()
        return dialog.clickedButton() is login_button


__all__ = ["SenNetPortalConnectionMixin"]
