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
		fetchReportPptxBlob,
		uploadReportSlideImage,
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
	let previewRendering = $state(false);
	let previewError = $state('');
	let previewCacheBust = $state(Date.now());
	let rendering = false;

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
			previewError = '';
			if (!slides.some((slide) => slide.image_url) && !rendering) {
				void renderSlidesClientSide().catch((err) => {
					previewError = err instanceof Error ? err.message : 'Slide preview render failed.';
				});
			}
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
			previewError = '';
			previewCacheBust = Date.now();
			void renderSlidesClientSide().catch((err) => {
				previewError = err instanceof Error ? err.message : 'Slide preview render failed.';
			});

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

	function slideImageUrl(slide: Slide): string | null {
		if (!slide.image_url) return null;
		return `${apiBaseUrl}${slide.image_url}?v=${previewCacheBust}`;
	}

	async function renderSlidesClientSide() {
		if (rendering) return;
		rendering = true;
		previewRendering = true;
		previewError = '';
		try {
			const pptxBuffer = await fetchReportPptxBlob(apiBaseUrl, reportId);
			const { PPTXViewer } = await import('pptxviewjs');

			const canvas = document.createElement('canvas');
			canvas.width = 1280;
			canvas.height = 720;

			const viewer = new PPTXViewer({ canvas, slideSizeMode: 'fit' });
			await viewer.loadFile(pptxBuffer);
			const count = viewer.getSlideCount();

			for (let i = 0; i < count; i++) {
				await viewer.renderSlide(i, canvas);
				const blob = await new Promise<Blob>((resolve, reject) => {
					canvas.toBlob((b) => {
						if (b) resolve(b);
						else reject(new Error('toBlob returned null'));
					}, 'image/png');
				});
				await uploadReportSlideImage(apiBaseUrl, reportId, i, blob);
			}

			viewer.destroy();
			previewCacheBust = Date.now();
			slides = await fetchSlides(apiBaseUrl, reportId);
		} finally {
			previewRendering = false;
			rendering = false;
		}
	}
</script>

<div class="flex h-full flex-col">
	<div class="flex items-center justify-between border-b border-border px-6 py-4">
		<button
			class="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
			onclick={() => goto('/')}
		>
			<ArrowLeft class="h-4 w-4" />
			Dashboard
		</button>
		<div class="flex items-center gap-3">
			{#if saveError}
				<span class="text-xs text-red-500">{saveError}</span>
			{/if}
			<Button
				size="sm"
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
			<div class="flex items-center gap-3 text-sm text-muted-foreground">
				<Loader2 class="h-4 w-4 animate-spin" />
				Loading slides...
			</div>
		</div>
	{:else if error}
		<div class="flex flex-1 items-center justify-center">
			<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-600 dark:text-red-300">
				{error}
			</div>
		</div>
	{:else}
		<div class="flex flex-1 overflow-hidden">
			<div class="flex w-[60%] flex-col border-r border-border bg-muted/20 relative">
				{#if previewError}
					<div class="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
						<p class="text-sm">Slide preview unavailable</p>
						<p class="max-w-md text-center text-xs">{previewError}</p>
					</div>
				{:else}
					{#if previewRendering}
						<div class="absolute inset-0 flex items-center justify-center gap-3 text-muted-foreground bg-muted/20 z-10">
							<Loader2 class="h-4 w-4 animate-spin" />
							<p class="text-sm">Rendering preview...</p>
						</div>
					{/if}
					<div class="flex-1 overflow-y-auto px-6 py-5">
						<div class="mx-auto flex max-w-5xl flex-col gap-5">
							{#each slides as slide (slide.slide_index)}
								{@const imgUrl = slideImageUrl(slide)}
								<div class="overflow-hidden rounded-md border border-border bg-background shadow-sm">
									{#if imgUrl}
										<img
											src={imgUrl}
											alt="Slide {slide.slide_index + 1}"
											class="block w-full"
										/>
									{:else}
										<div class="flex aspect-video items-center justify-center bg-muted text-sm text-muted-foreground">
											{#if previewRendering}
												<Loader2 class="h-4 w-4 animate-spin" />
											{:else}
												Slide {slide.slide_index + 1}
											{/if}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>

			<div class="flex w-[40%] flex-col overflow-y-auto p-6">
				{#if slides.some(s => s.fields.length > 0)}
					<div class="space-y-8">
						{#each slides.filter(s => s.fields.length > 0) as slide (slide.slide_index)}
							<div>
								<h2 class="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
									Slide {slide.slide_index + 1}
								</h2>
								<div class="space-y-5">
									{#each slide.fields as field (field.field_id)}
										<div class="space-y-2">
											<Label class="text-xs font-medium text-muted-foreground">{field.label}</Label>
											<textarea
												class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
												rows={editedValues[field.field_id]?.length > 100 ? 5 : 2}
												bind:value={editedValues[field.field_id]}
											></textarea>
											<div class="flex gap-2">
												<input
													type="text"
													placeholder="e.g. make it shorter, focus on new users"
													class="flex-1 rounded-md border border-border bg-muted/50 px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
													bind:value={instructions[field.field_id]}
												/>
												<Button
													size="sm"
													variant="outline"
													class="text-xs"
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
					<div class="flex flex-1 items-center justify-center text-sm text-muted-foreground">
						No editable fields found.
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
