#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
TAURI_DIR="${FRONTEND_DIR}/src-tauri"
BUNDLE_DIR="${TAURI_DIR}/target/release/bundle"
APP_PATH="${BUNDLE_DIR}/macos/Reports.app"
DMG_SCRIPT="${BUNDLE_DIR}/dmg/bundle_dmg.sh"
OUTPUT_DMG="${BUNDLE_DIR}/dmg/Reports_0.1.0_x64.dmg"

if [[ ! -d "${APP_PATH}" ]]; then
	echo "Missing app bundle: ${APP_PATH}" >&2
	exit 1
fi

if [[ ! -x "${DMG_SCRIPT}" ]]; then
	echo "Missing DMG script: ${DMG_SCRIPT}" >&2
	exit 1
fi

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reports-dmg-stage.XXXXXX")"
cleanup() {
	rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

cp -R "${APP_PATH}" "${STAGING_DIR}/Reports.app"
rm -f "${OUTPUT_DMG}"

"${DMG_SCRIPT}" \
	--volname "Reports" \
	--window-size 660 400 \
	--icon-size 128 \
	--icon "Reports.app" 180 170 \
	--app-drop-link 480 170 \
	"${OUTPUT_DMG}" \
	"${STAGING_DIR}"

echo "Created DMG: ${OUTPUT_DMG}"
