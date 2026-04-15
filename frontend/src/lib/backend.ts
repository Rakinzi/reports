import { getDesktopContext, type DesktopContext } from '$lib/desktop';
import { invoke } from '@tauri-apps/api/core';

export type Report = {
	id: number;
	report_name: string;
	date_range: string;
	report_date: string;
	status: 'pending' | 'completed' | 'failed';
	output_path?: string | null;
	error?: string | null;
	stage?: string | null;
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
	browser_available: boolean;
	browser_path: string;
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
			if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
				try {
					const startup = await invoke<{
						state: string;
						pid: number | null;
						exit_code: number | null;
						message: string | null;
						recent_output: string[];
					}>('get_backend_startup_status');

					if (startup.state === 'failed') {
						throw new Error(startup.message ?? 'The local backend process exited during startup.');
					}
				} catch (error) {
					if (error instanceof Error) {
						throw error;
					}
					throw new Error(String(error));
				}
			}
		}
		await new Promise((resolve) => setTimeout(resolve, intervalMs));
	}

	throw new Error('The local backend did not start in time.');
}

export type SlideField = {
	field_id: string;
	label: string;
	value: string;
	slide_index: number;
	shape_name: string;
	para_index: number;
};

export type Slide = {
	slide_index: number;
	image_url: string | null;
	fields: SlideField[];
};

export async function fetchSlides(apiBaseUrl: string, reportId: number): Promise<Slide[]> {
	return fetchJson<Slide[]>(apiBaseUrl, `/reports/${reportId}/slides`);
}

export async function rewriteField(
	apiBaseUrl: string,
	reportId: number,
	slideIndex: number,
	fieldId: string,
	currentText: string,
	instruction: string
): Promise<string> {
	const res = await fetchJson<{ rewritten_text: string }>(
		apiBaseUrl,
		`/reports/${reportId}/slides/${slideIndex}/rewrite`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ field_id: fieldId, current_text: currentText, instruction }),
		}
	);
	return res.rewritten_text;
}

export async function applyEdits(
	apiBaseUrl: string,
	reportId: number,
	edits: Record<string, string>
): Promise<{ output_path: string; download_url: string }> {
	return fetchJson(apiBaseUrl, `/reports/${reportId}/apply-edits`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ edits }),
	});
}

// ---------------------------------------------------------------------------
// Template types
// ---------------------------------------------------------------------------

export type TemplateShape = {
	id: number;
	template_id: number;
	slide_index: number;
	shape_name: string;
	shape_type: 'text' | 'image';
	placeholder_text: string;
	left_emu: number | null;
	top_emu: number | null;
	width_emu: number | null;
	height_emu: number | null;
};

export type ShapeMapping = {
	shape_name: string;
	slide_index: number;
	field_type: string;
	shape_type: 'text' | 'image';
};

export type TemplateConfig = {
	id: number;
	label: string;
	slug: string;
	slide_count: number;
	ga4_property_id: string;
	gsc_url: string;
	is_seven_slide: number;
	field_map: ShapeMapping[];
	preview_dir: string | null;
	has_field_map: boolean;
	created_at: string;
};

export type SlideShapes = {
	slide_index: number;
	image_url: string | null;
	shapes: TemplateShape[];
};

export type ReportOption = {
	value: string;
	label: string;
	source: 'builtin' | 'user';
};

// ---------------------------------------------------------------------------
// Template API helpers
// ---------------------------------------------------------------------------

export function fetchReportOptions(apiBaseUrl: string): Promise<ReportOption[]> {
	return fetchJson<ReportOption[]>(apiBaseUrl, '/templates/report-options');
}

export function fetchTemplates(apiBaseUrl: string): Promise<TemplateConfig[]> {
	return fetchJson<TemplateConfig[]>(apiBaseUrl, '/templates');
}

export function fetchTemplate(apiBaseUrl: string, id: number): Promise<TemplateConfig> {
	return fetchJson<TemplateConfig>(apiBaseUrl, `/templates/${id}`);
}

export function fetchTemplateShapes(apiBaseUrl: string, id: number): Promise<SlideShapes[]> {
	return fetchJson<SlideShapes[]>(apiBaseUrl, `/templates/${id}/shapes`);
}

export async function uploadTemplate(
	apiBaseUrl: string,
	file: File,
	label: string,
	slug: string
): Promise<{ id: number; slug: string; slide_count: number }> {
	const form = new FormData();
	form.append('file', file);
	form.append('label', label);
	form.append('slug', slug);
	const res = await fetch(`${apiBaseUrl}/templates/upload`, { method: 'POST', body: form });
	if (!res.ok) {
		let detail = `Upload failed: ${res.status}`;
		try { const b = await res.json(); if (b?.detail) detail = b.detail; } catch { /**/ }
		throw new Error(detail);
	}
	return res.json();
}

export function saveTemplateConfig(
	apiBaseUrl: string,
	id: number,
	config: { ga4_property_id: string; gsc_url: string; is_seven_slide: boolean; field_map: ShapeMapping[] }
): Promise<TemplateConfig> {
	return fetchJson<TemplateConfig>(apiBaseUrl, `/templates/${id}/config`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(config),
	});
}

export async function deleteTemplate(apiBaseUrl: string, id: number): Promise<void> {
	await fetchJson(apiBaseUrl, `/templates/${id}`, { method: 'DELETE' });
}

export function searchGa4Properties(apiBaseUrl: string, query: string): Promise<{ results: string[] }> {
	return fetchJson<{ results: string[] }>(apiBaseUrl, '/templates/ga4-search', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ query }),
	});
}
