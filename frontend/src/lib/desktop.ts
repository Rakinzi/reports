import { invoke } from '@tauri-apps/api/core';
import { save } from '@tauri-apps/plugin-dialog';

export type DesktopContext = {
	apiBaseUrl: string;
	isTauri: boolean;
};

export function isTauriApp() {
	return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export async function getDesktopContext(): Promise<DesktopContext> {
	if (!isTauriApp()) {
		return {
			apiBaseUrl: 'http://127.0.0.1:8000',
			isTauri: false
		};
	}

	const apiBaseUrl = await invoke<string>('get_backend_url');
	return { apiBaseUrl, isTauri: true };
}

export async function saveReportFromDesktop(
	apiBaseUrl: string,
	reportId: number,
	filename: string
) {
	const targetPath = await save({
		defaultPath: filename,
		filters: [{ name: 'PowerPoint', extensions: ['pptx'] }]
	});

	if (!targetPath) {
		return false;
	}

	await invoke('download_report', {
		backendUrl: apiBaseUrl,
		reportId,
		targetPath
	});

	return true;
}
