# Reports Desktop

This repository packages the Svelte frontend and FastAPI report generator as a cross-platform desktop application (macOS + Windows).

## Local Development

- Backend: `uv run python main.py`
- Frontend: `cd frontend && bun run dev`
- Desktop shell: `cd frontend && bun run tauri:dev`

The desktop app starts the bundled Python API locally and stores runtime data in the OS app-data directory.

## First Run Setup

The app requires:

- a Gemini API key
- a locally installed Chromium-based browser: Google Chrome, Microsoft Edge, or Chromium
- signing into Google Analytics once through the app-managed browser session

The app stores its own managed browser profile and other runtime data in the OS app-data directory.

## Building Installers

Prerequisites:

1. Install Python dependencies: `uv sync`
2. Install frontend dependencies: `cd frontend && bun install`
3. Build commands now rebuild the Python sidecar automatically before packaging.

The sidecar build script writes the platform-specific executable into `frontend/src-tauri/binaries/` using the target-triple suffix required by Tauri.

If you want to refresh the sidecar without creating an installer, run:

```sh
cd frontend
bun run desktop:build-sidecar
```

### macOS (`.app` + `.dmg`)

```sh
cd frontend
bun run tauri:build:mac
```

Output:

```
src-tauri/target/release/bundle/macos/Reports.app
src-tauri/target/release/bundle/dmg/Reports_<version>_x64.dmg
```

Install by opening the `.dmg`, dragging **Reports.app** to Applications, and launching it.

### Windows (`.msi` + `.exe` NSIS installer)

```sh
cd frontend
bun run tauri:build:win
```

Output:

```
src-tauri/target/release/bundle/msi/Reports_<version>_x64_en-US.msi
src-tauri/target/release/bundle/nsis/Reports_<version>_x64-setup.exe
```

Install by running the `.exe` setup wizard or the `.msi` package directly.

> **Note:** Tauri 2 automatically merges the platform-specific config (`tauri.macos.conf.json` / `tauri.windows.conf.json`) over the shared `tauri.conf.json` base when `--config` is passed. You do not need to edit the base config to switch platforms.

## Platform Config Files

| File | Purpose |
|---|---|
| `src-tauri/tauri.conf.json` | Shared base config (app ID, sidecar, bundle active) |
| `src-tauri/tauri.macos.conf.json` | macOS overrides — targets: `app`, `dmg`; macOS icon |
| `src-tauri/tauri.windows.conf.json` | Windows overrides — targets: `nsis`, `msi`; Windows icons |
