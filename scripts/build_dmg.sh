#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
TAURI_DIR="${FRONTEND_DIR}/src-tauri"
BUNDLE_DIR="${TAURI_DIR}/target/release/bundle"
APP_PATH="${BUNDLE_DIR}/macos/Reports.app"
APP_VERSION="$(node -p "require('${FRONTEND_DIR}/package.json').version")"
OUTPUT_DMG="${BUNDLE_DIR}/dmg/Reports_${APP_VERSION}_x64.dmg"

if [[ ! -d "${APP_PATH}" ]]; then
	echo "Missing app bundle: ${APP_PATH}" >&2
	exit 1
fi

mkdir -p "${BUNDLE_DIR}/dmg"

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reports-dmg-stage.XXXXXX")"
cleanup() {
	rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

cp -R "${APP_PATH}" "${STAGING_DIR}/Reports.app"
ln -s /Applications "${STAGING_DIR}/Applications"
rm -f "${OUTPUT_DMG}"

hdiutil create \
	-volname "Reports" \
	-srcfolder "${STAGING_DIR}" \
	-ov \
	-format UDZO \
	"${OUTPUT_DMG}"

echo "Created DMG: ${OUTPUT_DMG}"
