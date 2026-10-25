from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = REPOSITORY_ROOT / "installer" / "windows"
MACOS_INSTALLER = REPOSITORY_ROOT / "installer" / "macos"
BOOTSTRAP_SECURITY_PACKAGES = (
    "pip>=26.2.2",
    "conda-forge::ca-certificates>=2026.10.19",
    "conda-forge::certifi>=2026.10.19",
)


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

    def test_postinstall_requires_bundled_constraints_before_setup(self) -> None:
        powershell = _powershell()
        if powershell is None:
            self.skipTest("PowerShell is unavailable")

        with tempfile.TemporaryDirectory(prefix="senoquant constraints ") as app_dir:
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(WINDOWS_INSTALLER / "post_install.ps1"),
                    "-AppDir",
                    app_dir,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Constraints file not found", result.stdout + result.stderr)
            self.assertEqual(list(Path(app_dir).iterdir()), [])

    def test_windows_uv_bootstrap_uses_constraints_and_stops_after_pip_failure(self) -> None:
        powershell = _powershell()
        if powershell is None:
            self.skipTest("PowerShell is unavailable")

        with tempfile.TemporaryDirectory(prefix="senoquant uv bootstrap ") as directory:
            checkout = Path(directory)
            script = checkout / "scripts" / "development" / "setup_windows.ps1"
            script.parent.mkdir(parents=True)
            shutil.copy2(
                REPOSITORY_ROOT / "scripts" / "development" / script.name, script,
            )
            for name in ("pyproject.toml", "constraints.txt"):
                shutil.copy2(REPOSITORY_ROOT / name, checkout / name)
            script_literal = str(script).replace("'", "''")
            for exists in (False, True):
                for failure_stage in ("", "native", "pip"):
                    with self.subTest(exists=exists, failure_stage=failure_stage):
                        command = f"""
$global:CondaCalls = [System.Collections.Generic.List[object]]::new()
$global:EnvironmentExists = ${str(exists).lower()}
$global:FailureStage = '{failure_stage}'
function conda {{
    $global:CondaCalls.Add(@($args))
    $global:LASTEXITCODE = 0
    if ($args[-1] -eq '--version') {{
        if (-not $global:EnvironmentExists) {{ $global:LASTEXITCODE = 17 }}
    }} elseif ($args -contains '-c') {{
        'AMD64'
    }} elseif (($global:FailureStage -eq 'native' -and
                $args[0] -in @('create', 'install')) -or
               ($global:FailureStage -eq 'pip' -and
                $args -contains '--upgrade')) {{
        $global:LASTEXITCODE = 17
    }}
}}
$failure = $null
try {{ & '{script_literal}' }} catch {{ $failure = $_.Exception.Message }}
@{{calls = $global:CondaCalls.ToArray(); failure = $failure}} |
    ConvertTo-Json -Depth 5 -Compress
"""
                        result = subprocess.run(
                            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-Command", command],
                            cwd=checkout, capture_output=True, text=True, check=True,
                        )
                        receipt = json.loads(result.stdout.splitlines()[-1])
                        calls = receipt["calls"]
                        native_calls = [c for c in calls if c[0] in {"create", "install"}]
                        self.assertEqual(len(native_calls), 1)
                        self.assertEqual(native_calls[0][0], "install" if exists else "create")
                        for requirement in BOOTSTRAP_SECURITY_PACKAGES:
                            self.assertIn(requirement, native_calls[0])
                        pip_calls = [c for c in calls if "python" in c and "pip" in c]
                        uv_calls = [c for c in pip_calls if c[-1] == "uv"]
                        dependency_calls = [c for c in calls if "--editable" in c]
                        if failure_stage == "native":
                            self.assertIn("Failed to create or update", receipt["failure"])
                            self.assertEqual(pip_calls, [])
                            self.assertEqual(dependency_calls, [])
                            continue
                        self.assertLess(calls.index(native_calls[0]), calls.index(pip_calls[0]))
                        if failure_stage == "pip":
                            self.assertIn("Failed to upgrade pip", receipt["failure"])
                            self.assertEqual(uv_calls, [])
                            self.assertEqual(dependency_calls, [])
                        else:
                            self.assertIsNone(receipt["failure"])
                            self.assertEqual(len(uv_calls), 1)
                            constraint = Path(
                                uv_calls[0][uv_calls[0].index("--constraint") + 1]
                            )
                            self.assertEqual(constraint.resolve(), checkout / "constraints.txt")
                            self.assertTrue(constraint.is_file())
                            self.assertEqual(len(dependency_calls), 1)
                            self.assertLess(calls.index(uv_calls[0]), calls.index(dependency_calls[0]))

    def test_unix_bootstrap_updates_certificates_before_pip(self) -> None:
        bash = shutil.which("bash") if os.name != "nt" else None
        if os.name == "nt" and (git := shutil.which("git")):
            candidate = Path(git).parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                bash = str(candidate)
        if bash is None:
            self.skipTest("Bash is unavailable")

        with tempfile.TemporaryDirectory(prefix="senoquant native bootstrap ") as directory:
            checkout = Path(directory)
            scripts = checkout / "scripts" / "development"
            scripts.mkdir(parents=True)
            for name in ("setup_linux.sh", "setup_macos.sh"):
                (scripts / name).write_text(
                    (REPOSITORY_ROOT / "scripts" / "development" / name).read_text(
                        encoding="utf-8",
                    ), encoding="utf-8", newline="\n",
                )
            shutil.copy2(REPOSITORY_ROOT / "constraints.txt", checkout / "constraints.txt")
            test_bin = checkout / "test-bin"
            test_bin.mkdir()
            stubs = {
                "uname": """#!/usr/bin/env bash
case "$1" in
    -s) printf '%s\n' "$SENOQUANT_TEST_OS" ;;
    -m) printf 'arm64\n' ;;
    *) exit 17 ;;
esac
""",
                "conda": r"""#!/usr/bin/env bash
printf '%s\0' "$@" >> "$SENOQUANT_TEST_LOG"
printf '\0' >> "$SENOQUANT_TEST_LOG"
if [[ "${@: -1}" == --version ]]; then
    exit "$SENOQUANT_TEST_PROBE_EXIT"
fi
if [[ "$SENOQUANT_TEST_FAIL" == native && "$1" != run ]] ||
   [[ "$SENOQUANT_TEST_FAIL" == pip && " $* " == *" --upgrade "* ]]; then
    exit 17
fi
""",
            }
            for name, source in stubs.items():
                executable = test_bin / name
                executable.write_text(source, encoding="utf-8", newline="\n")
                executable.chmod(0o755)
            for system, name in (("Linux", "setup_linux.sh"), ("Darwin", "setup_macos.sh")):
                for exists in (False, True):
                    for failure_stage in ("", "native", "pip"):
                        with self.subTest(system=system, exists=exists, failure_stage=failure_stage):
                            log = checkout / "calls.bin"
                            log.unlink(missing_ok=True)
                            environment = dict(
                                os.environ, SENOQUANT_TEST_OS=system,
                                SENOQUANT_TEST_LOG="calls.bin",
                                SENOQUANT_TEST_PROBE_EXIT="0" if exists else "17",
                                SENOQUANT_TEST_FAIL=failure_stage,
                            )
                            environment.pop("BASH_ENV", None)
                            result = subprocess.run(
                                [bash, "-c", 'unset -f conda uname; '
                                 'export PATH="$PWD/test-bin:$PATH"; exec bash "$1"',
                                 "bootstrap-test", f"scripts/development/{name}"],
                                cwd=checkout, env=environment, capture_output=True, text=True,
                            )
                            calls = [
                                entry.decode().split("\0")
                                for entry in log.read_bytes().split(b"\0\0") if entry
                            ]
                            native_calls = [c for c in calls if c[0] in {"create", "install"}]
                            self.assertEqual(len(native_calls), 1)
                            self.assertEqual(native_calls[0][0], "install" if exists else "create")
                            for requirement in BOOTSTRAP_SECURITY_PACKAGES:
                                self.assertIn(requirement, native_calls[0])
                            pip_calls = [c for c in calls if "python" in c and "pip" in c]
                            dependency_calls = [c for c in calls if "--editable" in c]
                            self.assertEqual(result.returncode, 17 if failure_stage else 0,
                                             result.stdout + result.stderr)
                            if failure_stage == "native":
                                self.assertEqual(pip_calls, [])
                            else:
                                self.assertLess(calls.index(native_calls[0]), calls.index(pip_calls[0]))
                            if failure_stage:
                                self.assertFalse(any(c[-1] == "uv" for c in pip_calls))
                                self.assertEqual(dependency_calls, [])
                            else:
                                self.assertEqual(len(dependency_calls), 1)

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
