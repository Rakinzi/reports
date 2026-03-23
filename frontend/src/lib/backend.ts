import { getDesktopContext, type DesktopContext } from '$lib/desktop';

export type Report = {
	id: number;
	report_name: string;
	date_range: string;
	report_date: string;
	status: 'pending' | 'completed' | 'failed';
	output_path?: string | null;
	error?: string | null;
	created_at: string;
};

export type ChromeProfile = {
	profile_dir: string;
	profile_name: string;
	signed_in_email: string;
	emails_from_preferences: string[];
};

export type SettingsState = {
	configured: boolean;
	gemini_api_key_set: boolean;
	chrome_user_data_dir: string;
	chrome_profile_directory: string;
	chrome_profile_label?: string;
	app_data_dir: string;
};

export type LogResponse = {
	path: string;
	lines: string[];
};

export async function resolveBackendContext(): Promise<DesktopContext> {
	return getDesktopContext();
}

export async function fetchJson<T>(
	apiBaseUrl: string,
	path: string,
	init?: RequestInit
): Promise<T> {
	const res = await fetch(`${apiBaseUrl}${path}`, init);
	if (!res.ok) {
		let detail = `Request failed: ${res.status}`;
		try {
			const body = await res.json();
			if (body?.detail) detail = body.detail;
		} catch {
			// ignore parsing failure
		}
		throw new Error(detail);
	}
	return res.json();
}

export async function waitForBackend(
	apiBaseUrl: string,
	options: { attempts?: number; intervalMs?: number } = {}
) {
	const attempts = options.attempts ?? 180;
	const intervalMs = options.intervalMs ?? 500;

	for (let attempt = 0; attempt < attempts; attempt += 1) {
		try {
			const health = await fetchJson<SettingsState & { status: string }>(apiBaseUrl, '/health');
			if (health.status === 'ok') {
				return health;
			}
		} catch {
			// keep waiting
		}
		await new Promise((resolve) => setTimeout(resolve, intervalMs));
	}

	throw new Error('The local backend did not start in time.');
}
