"""Connection and authentication UI mixin for the SenNet Portal frontend."""

from __future__ import annotations

import webbrowser

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

    GCP_INSTALL_URL = "https://www.globus.org/globus-connect-personal"

    def _make_connection_section(self) -> QGroupBox:
        """Create connection controls used for optional API authentication.

        Returns
        -------
        QGroupBox
            Group box containing bearer-token input and Globus/GCP controls.
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

        self._gcp_status_label = QLabel("Checking Globus Connect Personal...")
        self._gcp_install_button = QPushButton("Install Globus Connect Personal")
        self._gcp_install_button.clicked.connect(self._open_gcp_install_page)
        self._gcp_check_again_button = QPushButton("Check again")
        self._gcp_check_again_button.clicked.connect(self._check_gcp_again)

        gcp_buttons = QHBoxLayout()
        gcp_buttons.setContentsMargins(0, 0, 0, 0)
        gcp_buttons.addWidget(self._gcp_install_button)
        gcp_buttons.addWidget(self._gcp_check_again_button)
        gcp_buttons.addStretch(1)
        gcp_widget = QWidget()
        gcp_widget.setLayout(gcp_buttons)

        form_layout.addRow("Globus status", self._globus_status_label)
        form_layout.addRow("Globus auth", globus_widget)
        form_layout.addRow("GCP status", self._gcp_status_label)
        form_layout.addRow("GCP setup", gcp_widget)
        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _refresh_globus_auth_status(self) -> None:
        """Refresh Globus and GCP labels plus action-button state.

        Returns
        -------
        None
            Connection section widgets are updated in-place.
        """
        self._refresh_gcp_status()

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

    def _refresh_gcp_status(self) -> None:
        """Refresh Globus Connect Personal availability and setup actions.

        Returns
        -------
        None
            GCP status text and install-button visibility are updated.
        """
        is_available, detail = self._backend.gcp_installation_status()
        if is_available:
            self._gcp_status_label.setText(f"Installed (endpoint: {detail})")
            self._gcp_install_button.setVisible(False)
            return

        if detail == "Globus Connect Personal not installed":
            self._gcp_status_label.setText("Not installed")
        elif detail == "Globus CLI not found":
            self._gcp_status_label.setText("Globus CLI not installed")
        else:
            self._gcp_status_label.setText("Not available")
        self._gcp_install_button.setVisible(True)

    def _check_gcp_again(self) -> None:
        """Re-run GCP checks after installation or configuration changes.

        Returns
        -------
        None
            Connection section status labels are refreshed.
        """
        self._refresh_globus_auth_status()

    def _open_gcp_install_page(self) -> None:
        """Open the official Globus Connect Personal installation page.

        Returns
        -------
        None
            Browser launch is best effort and failures are surfaced to status.
        """
        opened = webbrowser.open(self.GCP_INSTALL_URL, new=2)
        if opened:
            self._notify("Opened Globus Connect Personal install page in browser.")
            return
        self._notify(f"Open this URL to install Globus Connect Personal: {self.GCP_INSTALL_URL}")

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
            Status labels and notifications are refreshed.
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
            Status labels and notifications are refreshed.
        """
        self._refresh_globus_auth_status()
        self._notify("Globus logout successful.")


__all__ = ["SenNetPortalConnectionMixin"]
