#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
BINARIES_DIR = FRONTEND_DIR / "src-tauri" / "binaries"


def detect_target_triple(explicit: str | None) -> str:
    if explicit:
        return explicit
    if value := os.getenv("TAURI_TARGET_TRIPLE"):
        return value
    try:
        return subprocess.check_output(["rustc", "--print", "host-tuple"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        machine = platform.machine().lower()
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
        system = sys.platform
        if system == "darwin":
            return f"{arch}-apple-darwin"
        if system == "win32":
            return f"{arch}-pc-windows-msvc"
        return f"{arch}-unknown-linux-gnu"


def build_sidecar(target_triple: str) -> Path:
    extension = ".exe" if "windows" in target_triple else ""
    add_data_sep = ";" if sys.platform == "win32" else ":"

    with tempfile.TemporaryDirectory(prefix="reports-sidecar-") as temp_dir:
        temp_path = Path(temp_dir)
        dist_dir = temp_path / "dist"
        work_dir = temp_path / "build"
        spec_dir = temp_path / "spec"

        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "reports-api",
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--paths",
            str(ROOT),
            "--add-data",
            f"{ROOT / 'src' / 'reports' / 'report-templates'}{add_data_sep}src/reports/report-templates",
            "--collect-data",
            "matplotlib",
            "--collect-data",
            "pandas",
            "--collect-data",
            "pptx",
            "--collect-submodules",
            "google.genai",
            "--exclude-module",
            "pandas.tests",
            "--exclude-module",
            "matplotlib.tests",
            "--exclude-module",
            "google.genai.tests",
            str(ROOT / "main.py"),
        ]
        env = os.environ.copy()
        env.setdefault("MPLCONFIGDIR", str((temp_path / "mplconfig").resolve()))
        env.setdefault("PYINSTALLER_CONFIG_DIR", str((temp_path / "pyinstaller-config").resolve()))
        subprocess.run(command, cwd=ROOT, check=True, env=env)

        BINARIES_DIR.mkdir(parents=True, exist_ok=True)
        source = dist_dir / f"reports-api{extension}"
        target = BINARIES_DIR / f"reports-api-{target_triple}{extension}"
        if target.exists():
            target.unlink()
        shutil.copy2(source, target)
        if extension == "":
            target.chmod(0o755)
        return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-triple")
    args = parser.parse_args()

    target = detect_target_triple(args.target_triple)
    built = build_sidecar(target)
    print(f"Built sidecar: {built}")


if __name__ == "__main__":
    main()
