# Reports Desktop

This repository now packages the Svelte frontend and FastAPI report generator as a desktop application.

## Local Development

- Backend: `uv run python main.py`
- Frontend: `cd frontend && bun run dev`
- Desktop shell: `cd frontend && bun run tauri:dev`

The desktop app starts the bundled Python API locally and stores runtime data in the OS app-data directory.

## First Run Setup

The app requires:

- a Gemini API key
- a Chrome user data directory that already contains a profile signed into Google Analytics
- the Chrome profile directory name, such as `Default` or `Profile 1`

These values are saved locally by the backend in the app-data directory.

## Building Installers

1. Install Python dependencies with `uv sync`.
2. Install frontend dependencies with `cd frontend && bun install`.
3. Build the Python sidecar with `cd frontend && bun run desktop:build-sidecar`.
4. Build the desktop installer with `cd frontend && bun run tauri:build`.

The sidecar build script writes the platform-specific executable into `frontend/src-tauri/binaries/` using the target-triple suffix required by Tauri.
