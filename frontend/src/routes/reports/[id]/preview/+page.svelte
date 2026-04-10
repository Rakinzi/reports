<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { Download, Loader2, Sparkles, ArrowLeft } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import {
		resolveBackendContext,
		fetchSlides,
		rewriteField,
		applyEdits,
		fetchJson,
		type Slide,
		type SlideField,
		type Report,
	} from '$lib/backend';
	import { saveReportFromDesktop } from '$lib/desktop';

	const reportId = Number($page.params.id);

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let isTauri = $state(false);
	let loading = $state(true);
	let error = $state('');
	let slides = $state<Slide[]>([]);
	let report = $state<Report | null>(null);

	let editedValues = $state<Record<string, string>>({});
	let instructions = $state<Record<string, string>>({});
	let rewriting = $state<Record<string, boolean>>({});

	let saving = $state(false);
	let saveError = $state('');
	let pdfAvailable = $state(false);

	const pdfUrl = $derived(`${apiBaseUrl}/reports/${reportId}/preview.pdf`);

	function initEdits(slides: Slide[]) {
		const vals: Record<string, string> = {};
		for (const slide of slides) {
			for (const field of slide.fields) {
				vals[field.field_id] = field.value;
			}
		}
		editedValues = vals;
	}

	async function load() {
		loading = true;
		error = '';
		try {
			const ctx = await resolveBackendContext();
			apiBaseUrl = ctx.apiBaseUrl;
			isTauri = ctx.isTauri;
			report = await fetchJson<Report>(apiBaseUrl, `/reports/${reportId}`);
			slides = await fetchSlides(apiBaseUrl, reportId);
			initEdits(slides);
			// Check if PDF preview is available
			const pdfCheck = await fetch(`${apiBaseUrl}/reports/${reportId}/preview.pdf`, { method: 'HEAD' });
			pdfAvailable = pdfCheck.ok;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load report';
		} finally {
			loading = false;
		}
	}

	async function handleRewrite(field: SlideField) {
		rewriting = { ...rewriting, [field.field_id]: true };
		try {
			const instruction = instructions[field.field_id] || 'paraphrase for a professional report';
			const result = await rewriteField(
				apiBaseUrl,
				reportId,
				field.slide_index,
				field.field_id,
				editedValues[field.field_id] ?? field.value,
				instruction
			);
			editedValues = { ...editedValues, [field.field_id]: result };
		} catch {
			// keep existing value on error
		} finally {
			rewriting = { ...rewriting, [field.field_id]: false };
		}
	}

	async function handleSaveAndExport() {
		saving = true;
		saveError = '';
		try {
			await applyEdits(apiBaseUrl, reportId, editedValues);
			slides = await fetchSlides(apiBaseUrl, reportId);
			// Re-check PDF (apply-edits triggers a re-render server-side)
			const pdfCheck = await fetch(`${apiBaseUrl}/reports/${reportId}/preview.pdf`, { method: 'HEAD' });
			pdfAvailable = pdfCheck.ok;

			const suggestedName = `${report?.report_name ?? 'report'}-edited.pptx`;
			if (isTauri) {
				await saveReportFromDesktop(apiBaseUrl, reportId, suggestedName);
			} else {
				window.open(`${apiBaseUrl}/reports/${reportId}/download`, '_blank', 'noopener,noreferrer');
			}
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	onMount(() => {
		void load();
	});
</script>

<div class="flex h-full flex-col">
	<div class="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
		<button
			class="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-100"
			onclick={() => goto('/')}
		>
			<ArrowLeft class="h-4 w-4" />
			Dashboard
		</button>
		<div class="flex items-center gap-3">
			{#if saveError}
				<span class="text-xs text-red-400">{saveError}</span>
			{/if}
			<Button
				size="sm"
				class="bg-zinc-100 font-semibold text-zinc-900 hover:bg-zinc-200"
				onclick={handleSaveAndExport}
				disabled={saving || loading}
			>
				{#if saving}
					<Loader2 class="mr-2 h-3.5 w-3.5 animate-spin" />
				{:else}
					<Download class="mr-2 h-3.5 w-3.5" />
				{/if}
				Save & Export
			</Button>
		</div>
	</div>

	{#if loading}
		<div class="flex flex-1 items-center justify-center">
			<div class="flex items-center gap-3 text-sm text-zinc-400">
				<Loader2 class="h-4 w-4 animate-spin" />
				Loading slides...
			</div>
		</div>
	{:else if error}
		<div class="flex flex-1 items-center justify-center">
			<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-300">
				{error}
			</div>
		</div>
	{:else}
		<div class="flex flex-1 overflow-hidden">
			<div class="flex w-[60%] flex-col border-r border-zinc-800 bg-zinc-950">
				{#if pdfAvailable}
					<iframe
						src={pdfUrl}
						title="Report Preview"
						class="flex-1 w-full border-none"
					></iframe>
				{:else}
					<div class="flex flex-1 flex-col items-center justify-center gap-3 text-zinc-600">
						<p class="text-sm">Slide preview unavailable</p>
						<p class="text-xs">Install LibreOffice to enable slide previews</p>
					</div>
				{/if}
			</div>

			<div class="flex w-[40%] flex-col overflow-y-auto p-6">
				{#if slides.some(s => s.fields.length > 0)}
					<div class="space-y-8">
						{#each slides.filter(s => s.fields.length > 0) as slide (slide.slide_index)}
							<div>
								<h2 class="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
									Slide {slide.slide_index + 1}
								</h2>
								<div class="space-y-5">
									{#each slide.fields as field (field.field_id)}
										<div class="space-y-2">
											<Label class="text-xs font-medium text-zinc-400">{field.label}</Label>
											<textarea
												class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500 resize-none"
												rows={editedValues[field.field_id]?.length > 100 ? 5 : 2}
												bind:value={editedValues[field.field_id]}
											></textarea>
											<div class="flex gap-2">
												<input
													type="text"
													placeholder="e.g. make it shorter, focus on new users"
													class="flex-1 rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
													bind:value={instructions[field.field_id]}
												/>
												<Button
													size="sm"
													variant="outline"
													class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 text-xs"
													onclick={() => handleRewrite(field)}
													disabled={rewriting[field.field_id]}
												>
													{#if rewriting[field.field_id]}
														<Loader2 class="mr-1.5 h-3 w-3 animate-spin" />
													{:else}
														<Sparkles class="mr-1.5 h-3 w-3" />
													{/if}
													Rewrite
												</Button>
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="flex flex-1 items-center justify-center text-sm text-zinc-600">
						No editable fields found.
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
