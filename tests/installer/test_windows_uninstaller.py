from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = REPOSITORY_ROOT / "installer" / "windows"
UNINSTALL_SCRIPT = WINDOWS_INSTALLER / "uninstall.ps1"
MANAGED_INSTALL_MARKER = ".senoquant-managed-install"


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _run_uninstaller(
    app_dir: Path,
    *,
    check_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    powershell = _powershell()
    if powershell is None:
        raise unittest.SkipTest("PowerShell is unavailable")

    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(UNINSTALL_SCRIPT),
        "-AppDir",
        str(app_dir),
    ]
    if check_only:
        command.append("-CheckOnly")
    return subprocess.run(command, capture_output=True, text=True, check=False)


class TestWindowsUninstaller(unittest.TestCase):
    def test_removes_only_managed_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "SenoQuant"
            environment_file = app_dir / "env" / "nested" / "runtime.dll"
            environment_file.parent.mkdir(parents=True)
            environment_file.write_text("runtime", encoding="utf-8")
            (app_dir / MANAGED_INSTALL_MARKER).write_text("managed", encoding="utf-8")
            (app_dir / "installed_version").write_text("1.2.3", encoding="utf-8")
            (app_dir / "post_install.log").write_text("log", encoding="utf-8")
            user_file = app_dir / "user-data.txt"
            user_file.write_text("preserve me", encoding="utf-8")

            result = _run_uninstaller(app_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((app_dir / "env").exists())
            self.assertFalse((app_dir / "installed_version").exists())
            self.assertFalse((app_dir / "post_install.log").exists())
            self.assertTrue((app_dir / MANAGED_INSTALL_MARKER).is_file())
            self.assertEqual(user_file.read_text(encoding="utf-8"), "preserve me")

    def test_refuses_cleanup_without_ownership_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "SenoQuant"
            environment_file = app_dir / "env" / "runtime.dll"
            environment_file.parent.mkdir(parents=True)
            environment_file.write_text("runtime", encoding="utf-8")

            result = _run_uninstaller(app_dir)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(environment_file.is_file())

    def test_check_only_does_not_remove_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "SenoQuant"
            environment_file = app_dir / "env" / "runtime.dll"
            environment_file.parent.mkdir(parents=True)
            environment_file.write_text("runtime", encoding="utf-8")
            (app_dir / MANAGED_INSTALL_MARKER).write_text("managed", encoding="utf-8")

            result = _run_uninstaller(app_dir, check_only=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(environment_file.is_file())

    def test_check_only_stops_for_managed_python_process(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows process inspection is unavailable")

        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "SenoQuant"
            environment_dir = app_dir / "env"
            environment_dir.mkdir(parents=True)
            (app_dir / MANAGED_INSTALL_MARKER).write_text("managed", encoding="utf-8")
            managed_python = environment_dir / "python.exe"
            source_python = Path(sys.executable)
            shutil.copy2(source_python, managed_python)
            for runtime_library in source_python.parent.glob("python*.dll"):
                shutil.copy2(runtime_library, environment_dir / runtime_library.name)

            process_environment = os.environ.copy()
            process_environment["PYTHONHOME"] = str(source_python.parent)
            process = subprocess.Popen(
                [str(managed_python), "-c", "import time; time.sleep(30)"],
                env=process_environment,
            )
            try:
                result = _run_uninstaller(app_dir, check_only=True)
            finally:
                process.terminate()
                process.wait(timeout=10)

            self.assertEqual(result.returncode, 20, result.stderr)
            self.assertTrue(managed_python.is_file())

    def test_installer_packages_and_invokes_cleanup(self) -> None:
        build_script = (WINDOWS_INSTALLER / "build_windows_installer.ps1").read_text(
            encoding="utf-8"
        )
        inno_setup = (WINDOWS_INSTALLER / "senoquant.iss").read_text(encoding="utf-8")

        self.assertIn('".senoquant-managed-install"', build_script)
        self.assertIn('"uninstall.ps1"', build_script)
        self.assertIn("[UninstallRun]", inno_setup)
        self.assertIn("InitializeUninstall", inno_setup)
        self.assertIn("-CheckOnly", inno_setup)
