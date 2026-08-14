from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = REPOSITORY_ROOT / "installer" / "windows"
MACOS_INSTALLER = REPOSITORY_ROOT / "installer" / "macos"


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


class TestPlatformScripts(unittest.TestCase):
    def test_windows_arm64_detection_accepts_known_names(self) -> None:
        powershell = _powershell()
        if powershell is None:
            self.skipTest("PowerShell is unavailable")

        helper = str(WINDOWS_INSTALLER / "platform.ps1").replace("'", "''")
        for architecture in ("ARM64", "Arm64", "aarch64"):
            with self.subTest(architecture=architecture):
                command = (
                    f". '{helper}'; "
                    "if (-not (Test-SenoQuantWindowsArm64 "
                    f"-Architecture @('{architecture}'))) {{ exit 1 }}"
                )
                subprocess.run(
                    [
                        powershell,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ],
                    check=True,
                )

    def test_windows_arm64_detection_rejects_x64(self) -> None:
        powershell = _powershell()
        if powershell is None:
            self.skipTest("PowerShell is unavailable")

        helper = str(WINDOWS_INSTALLER / "platform.ps1").replace("'", "''")
        command = (
            f". '{helper}'; "
            "if (Test-SenoQuantWindowsArm64 -Architecture @('AMD64', 'x86_64')) "
            "{ exit 1 }"
        )
        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=True,
        )

    def test_windows_installer_packages_arm_helper_and_cpu_path(self) -> None:
        build_script = (
            WINDOWS_INSTALLER / "build_windows_installer.ps1"
        ).read_text(encoding="utf-8")
        post_install = (WINDOWS_INSTALLER / "post_install.ps1").read_text(
            encoding="utf-8",
        )
        inno_setup = (WINDOWS_INSTALLER / "senoquant.iss").read_text(
            encoding="utf-8",
        )

        self.assertIn('"platform.ps1"', build_script)
        self.assertIn("Test-SenoQuantWindowsArm64", post_install)
        self.assertIn(
            "Installing CPU PyTorch for Windows ARM64 x64 emulation",
            post_install,
        )
        self.assertIn("https://download.pytorch.org/whl/cpu", post_install)
        self.assertIn("$windowsBuild -lt 26100", post_install)
        self.assertIn("CPUExecutionProvider", post_install)
        self.assertIn("& $uvExe pip install", post_install)
        self.assertIn("ForEach-Object { $_.ToString() }", post_install)
        self.assertIn('$ErrorActionPreference = "Continue"', post_install)
        self.assertNotIn("senoquant_uv_install.py", post_install)
        self.assertNotIn('"--force-reinstall"', post_install)
        self.assertIn("ArchitecturesAllowed=x64compatible", inno_setup)
        self.assertLess(
            post_install.index("Installing CPU PyTorch"),
            post_install.index("Installing napari"),
        )
        self.assertLess(
            post_install.index("Installing napari"),
            post_install.index("Installing SenoQuant wheel"),
        )

    def test_development_setup_scripts_install_editable_package(self) -> None:
        for script_name in (
            "setup_linux.sh",
            "setup_macos.sh",
            "setup_windows.ps1",
        ):
            with self.subTest(script_name=script_name):
                script = (
                    REPOSITORY_ROOT / "scripts" / "development" / script_name
                ).read_text(encoding="utf-8")

                self.assertIn("senoquant-dev", script)
                self.assertIn("python=3.11", script)
                self.assertIn("requirements-test.txt", script)
                self.assertIn("napari[all]", script)
                self.assertIn("editable", script)
                if script_name == "setup_windows.ps1":
                    self.assertIn('@("--platform", "win-64")', script)

    def test_native_launchers_keep_models_in_managed_environment(self) -> None:
        windows_launcher = (WINDOWS_INSTALLER / "launch_senoquant.ps1").read_text(
            encoding="utf-8"
        )
        macos_launcher = (MACOS_INSTALLER / "launch_senoquant.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '$env:SENOQUANT_MODEL_DIR = Join-Path $envDir "models"',
            windows_launcher,
        )
        self.assertIn(
            'export SENOQUANT_MODEL_DIR="${ENV_DIR}/models"',
            macos_launcher,
        )
