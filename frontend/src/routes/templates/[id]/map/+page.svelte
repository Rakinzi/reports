<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { ArrowLeft, Check, Loader2, Save, AlertTriangle } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		resolveBackendContext,
		waitForBackend,
		fetchTemplate,
		fetchTemplateShapes,
		saveTemplateConfig,
		type TemplateConfig,
		type TemplateShape,
		type SlideShapes,
		type ShapeMapping,
		type TemplatePropertySection
	} from '$lib/backend';
	import { SvelteMap } from 'svelte/reactivity';
	import { FIELD_TYPE_GROUPS, FIELD_TYPE_MAP } from '$lib/fieldTypes';

	const templateId = Number($page.params.id);

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let loading = $state(true);
	let saving = $state(false);
	let saved = $state(false);
	let pageError = $state('');
	let saveError = $state('');
	let template = $state<TemplateConfig | null>(null);
	let slides = $state<SlideShapes[]>([]);
	let selectedSlide = $state(0);

	// Config form state
	let ga4PropertyId = $state('');
	let gscUrl = $state('');
	let isSevenSlide = $state(false);
	let propertySections = $state<TemplatePropertySection[]>([]);

	// Shape → field_type mapping (shape_name → field_type string)
	let mappings = $state<Record<string, string>>({});

	// Poll until preview thumbnails are rendered
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	let currentSlide = $derived(slides.find((s) => s.slide_index === selectedSlide));

	// Computed: duplicate field_type assignments (warn user)
	let duplicateFieldTypes = $derived.by(() => {
		const seen = new SvelteMap<string, string[]>();
		for (const [name, ft] of Object.entries(mappings)) {
			if (!ft || ft === 'static_text' || ft === 'static_image') continue;
			if (!seen.has(ft)) seen.set(ft, []);
			seen.get(ft)!.push(name);
		}
		const dupes = new SvelteMap<string, string[]>();
		for (const [ft, names] of seen) {
			if (names.length > 1) dupes.set(ft, names);
		}
		return dupes;
	});

	async function bootstrap() {
		loading = true;
		pageError = '';
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			await waitForBackend(apiBaseUrl);
			await loadAll();
		} catch (err) {
			pageError = err instanceof Error ? err.message : 'Failed to load template.';
		} finally {
			loading = false;
		}
	}

	async function loadAll() {
		[template, slides] = await Promise.all([
			fetchTemplate(apiBaseUrl, templateId),
			fetchTemplateShapes(apiBaseUrl, templateId)
		]);

		if (!template) throw new Error('Template not found.');

		ga4PropertyId = template.ga4_property_id;
		gscUrl = template.gsc_url;
		isSevenSlide = Boolean(template.is_seven_slide);
		propertySections = template.property_sections ?? [];

		// Initialise mapping state from existing field_map
		const existingMap: Record<string, string> = {};
		for (const m of template.field_map as ShapeMapping[]) {
			existingMap[m.shape_name] = m.field_type;
		}
		// Ensure every shape has an entry (default = '')
		for (const slide of slides) {
			for (const shape of slide.shapes) {
				existingMap[shape.shape_name] ??= '';
			}
		}
		mappings = existingMap;

		// If no previews yet, start polling
		if (!template.preview_dir && pollTimer === null) {
			pollTimer = setInterval(refreshPreviews, 3000);
		}
	}

	async function refreshPreviews() {
		try {
			const [freshTemplate, freshSlides] = await Promise.all([
				fetchTemplate(apiBaseUrl, templateId),
				fetchTemplateShapes(apiBaseUrl, templateId)
			]);
			if (freshTemplate.preview_dir) {
				template = freshTemplate;
				slides = freshSlides;
				if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
			}
		} catch { /**/ }
	}

	onMount(bootstrap);
	onDestroy(() => { if (pollTimer) clearInterval(pollTimer); });

	async function handleSave() {
		saving = true;
		saved = false;
		saveError = '';
		try {
			const field_map: ShapeMapping[] = [];
			for (const slide of slides) {
				for (const shape of slide.shapes) {
					const ft = mappings[shape.shape_name] ?? '';
					if (ft) {
						field_map.push({
							shape_name: shape.shape_name,
							slide_index: shape.slide_index,
							field_type: ft,
							shape_type: shape.shape_type as 'text' | 'image'
						});
					}
				}
			}
			template = await saveTemplateConfig(apiBaseUrl, templateId, {
				ga4_property_id: ga4PropertyId.trim(),
				gsc_url: gscUrl.trim(),
				is_seven_slide: isSevenSlide,
				field_map,
				property_sections: propertySections.map((s, i) => ({ ...s, sort_order: i }))
			});
			saved = true;
			setTimeout(() => { saved = false; }, 3000);
		} catch (err) {
			saveError = err instanceof Error ? err.message : 'Save failed.';
		} finally {
			saving = false;
		}
	}

	function slideImageUrl(slide: SlideShapes): string | null {
		if (!slide.image_url) return null;
		return `${apiBaseUrl}${slide.image_url}`;
	}

	function shapeLabel(shape: TemplateShape): string {
		if (shape.placeholder_text) return shape.placeholder_text;
		return shape.shape_name;
	}
</script>

<div class="flex h-full flex-col">
	<!-- Header -->
	<div class="flex items-center gap-3 border-b border-border px-6 py-4">
		<Button variant="ghost" size="sm" onclick={() => void goto('/templates')}>
			<ArrowLeft class="mr-1 h-4 w-4" />
			Templates
		</Button>
		<span class="text-muted-foreground">/</span>
		<span class="text-sm font-semibold">{template?.label ?? '…'}</span>
		{#if template?.has_field_map}
			<Badge variant="default" class="ml-2 text-xs">Mapped</Badge>
		{/if}
		<div class="ml-auto flex items-center gap-2">
			{#if saved}
				<span class="flex items-center gap-1 text-sm text-green-600">
					<Check class="h-4 w-4" /> Saved
				</span>
			{/if}
			<Button onclick={handleSave} disabled={saving}>
				{#if saving}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{:else}
					<Save class="mr-2 h-4 w-4" />
				{/if}
				Save Mapping
			</Button>
		</div>
	</div>

	{#if pageError}
		<div class="mx-6 mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
			{pageError}
		</div>
	{/if}

	{#if loading}
		<div class="flex flex-1 items-center justify-center">
			<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
		</div>
	{:else}
		<div class="flex flex-1 overflow-hidden">
			<!-- Slide thumbnail panel -->
			<div class="flex w-48 shrink-0 flex-col gap-1.5 overflow-y-auto border-r border-border bg-muted/20 p-2">
				<p class="px-1 pb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
					Slides
				</p>
				{#each slides as slide (slide.slide_index)}
					{@const imgUrl = slideImageUrl(slide)}
					<button
						class="relative w-full overflow-hidden rounded-md border-2 transition-colors {selectedSlide === slide.slide_index
							? 'border-primary'
							: 'border-transparent hover:border-muted-foreground/30'}"
						onclick={() => { selectedSlide = slide.slide_index; }}
					>
						<div class="relative w-full" style="aspect-ratio: 16/9;">
							{#if imgUrl}
								<img
									src={imgUrl}
									alt="Slide {slide.slide_index + 1}"
									class="absolute inset-0 h-full w-full object-cover"
								/>
							{:else}
								<div class="absolute inset-0 flex items-center justify-center bg-muted">
									{#if template && !template.preview_dir}
										<Loader2 class="h-3.5 w-3.5 animate-spin text-muted-foreground" />
									{:else}
										<span class="text-xs text-muted-foreground">{slide.slide_index + 1}</span>
									{/if}
								</div>
							{/if}
							<span class="absolute bottom-0 left-0 right-0 bg-black/60 px-1 py-0.5 text-center text-[10px] leading-tight text-white">
								{slide.slide_index + 1}{#if slide.shapes.length > 0}<span class="ml-1 opacity-60">·{slide.shapes.length}</span>{/if}
							</span>
						</div>
					</button>
				{/each}
			</div>

			<!-- Mapping panel -->
			<div class="flex flex-1 flex-col overflow-y-auto">
				<!-- Config strip -->
				<div class="border-b border-border bg-muted/10 px-6 py-4">
					<div class="grid gap-4 sm:grid-cols-3">
						<div class="space-y-1.5">
							<Label for="ga4-prop">GA4 Property ID</Label>
							<Input
								id="ga4-prop"
								bind:value={ga4PropertyId}
								placeholder="e.g. 123456789"
								class="font-mono text-sm"
							/>
						</div>
						<div class="space-y-1.5">
							<Label for="gsc-url">Google Search Console URL</Label>
							<Input
								id="gsc-url"
								bind:value={gscUrl}
								placeholder="e.g. https://example.com"
							/>
						</div>
						<div class="flex items-end pb-0.5">
							<label class="flex cursor-pointer items-center gap-2 text-sm">
								<input
									type="checkbox"
									bind:checked={isSevenSlide}
									class="h-4 w-4 rounded border-input accent-primary"
								/>
								7-slide template (no last recommendations slide)
							</label>
						</div>
					</div>
				</div>

				<!-- Property Sections editor -->
				<div class="border-b border-border bg-muted/5 px-6 py-4">
					<div class="mb-3 flex items-center justify-between">
						<div>
							<p class="text-sm font-semibold">Property Sections</p>
							<p class="text-xs text-muted-foreground">
								For combined reports — map slide ranges to different GA4 properties.
								Leave empty to use the single property ID above.
							</p>
						</div>
						<Button
							variant="outline"
							size="sm"
							onclick={() => {
								propertySections = [
									...propertySections,
									{
										section_name: '',
										start_slide: 0,
										end_slide: 0,
										ga4_property_id: '',
										gsc_url: '',
										sort_order: propertySections.length
									}
								];
							}}
						>
							+ Add Section
						</Button>
					</div>
					{#if propertySections.length > 0}
						<div class="overflow-hidden rounded-md border border-border">
							<table class="w-full text-sm">
								<thead class="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
									<tr>
										<th class="px-3 py-2 text-left">Section Name</th>
										<th class="px-3 py-2 text-left w-24">Start Slide</th>
										<th class="px-3 py-2 text-left w-24">End Slide</th>
										<th class="px-3 py-2 text-left">GA4 Property ID</th>
										<th class="px-3 py-2 text-left">GSC URL</th>
										<th class="px-3 py-2 w-8"></th>
									</tr>
								</thead>
								<tbody class="divide-y divide-border">
									{#each propertySections as section, i (i)}
										<tr class="hover:bg-muted/20">
											<td class="px-3 py-1.5">
												<input
													type="text"
													bind:value={section.section_name}
													placeholder="e.g. EcoCash"
													class="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
												/>
											</td>
											<td class="px-3 py-1.5">
												<input
													type="number"
													min="0"
													bind:value={section.start_slide}
													class="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
												/>
											</td>
											<td class="px-3 py-1.5">
												<input
													type="number"
													min="0"
													bind:value={section.end_slide}
													class="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
												/>
											</td>
											<td class="px-3 py-1.5">
												<input
													type="text"
													bind:value={section.ga4_property_id}
													placeholder="123456789"
													class="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
												/>
											</td>
											<td class="px-3 py-1.5">
												<input
													type="text"
													bind:value={section.gsc_url}
													placeholder="https://example.com"
													class="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
												/>
											</td>
											<td class="px-3 py-1.5 text-center">
												<button
													type="button"
													onclick={() => {
														propertySections = propertySections.filter((_, idx) => idx !== i);
													}}
													class="text-muted-foreground hover:text-destructive"
													aria-label="Remove section"
												>
													✕
												</button>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
						<p class="mt-2 text-xs text-muted-foreground">
							Slide indices are 0-based (slide 1 = index 0). Sections should not overlap.
						</p>
					{/if}
				</div>

				{#if saveError}
					<div class="mx-6 mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
						{saveError}
					</div>
				{/if}

				{#if duplicateFieldTypes.size > 0}
					<div class="mx-6 mt-4 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
						<AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
						<span>
							Duplicate field types detected:
							{#each [...duplicateFieldTypes] as [ft, names] (ft)}
								<strong>{FIELD_TYPE_MAP.get(ft)?.label ?? ft}</strong> (assigned to {names.join(', ')})
							{/each}
						</span>
					</div>
				{/if}

				<!-- Shape mapping table for the selected slide -->
				{#if currentSlide}
					<div class="px-6 py-4">
						<h2 class="mb-3 text-sm font-semibold">
							Slide {currentSlide.slide_index + 1} — {currentSlide.shapes.length} shape{currentSlide.shapes.length !== 1 ? 's' : ''}
						</h2>

						{#if currentSlide.shapes.length === 0}
							<p class="text-sm text-muted-foreground">No mappable shapes on this slide.</p>
						{:else}
							<div class="overflow-hidden rounded-md border border-border">
								<table class="w-full text-sm">
									<thead class="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
										<tr>
											<th class="px-4 py-2.5 text-left">Shape</th>
											<th class="px-4 py-2.5 text-left">Type</th>
											<th class="px-4 py-2.5 text-left">Preview text</th>
											<th class="px-4 py-2.5 text-left w-56">Field type</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-border">
										{#each currentSlide.shapes as shape (shape.id)}
											{@const isDuplicate = (() => {
												const ft = mappings[shape.shape_name];
												if (!ft || ft === 'static_text' || ft === 'static_image') return false;
												return duplicateFieldTypes.has(ft);
											})()}
											<tr class="transition-colors hover:bg-muted/30 {isDuplicate ? 'bg-amber-50/50 dark:bg-amber-950/10' : ''}">
												<td class="px-4 py-2.5 font-mono text-xs text-muted-foreground">
													{shape.shape_name}
												</td>
												<td class="px-4 py-2.5">
													<Badge variant="outline" class="text-xs">
														{shape.shape_type}
													</Badge>
												</td>
												<td class="max-w-xs truncate px-4 py-2.5 text-xs text-muted-foreground">
													{shapeLabel(shape)}
												</td>
												<td class="px-4 py-2.5">
													<select
														class="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring {isDuplicate ? 'border-amber-400' : ''}"
														bind:value={mappings[shape.shape_name]}
													>
														<option value="">— no mapping —</option>
														{#each FIELD_TYPE_GROUPS as { group, types } (group)}
															{@const filtered = types.filter((ft) => ft.shapeType === shape.shape_type)}
															{#if filtered.length > 0}
																<optgroup label={group}>
																	{#each filtered as ft (ft.value)}
																		<option value={ft.value}>{ft.label}</option>
																	{/each}
																</optgroup>
															{/if}
														{/each}
													</select>
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
