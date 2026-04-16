<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { FileUp, Layers, Loader2, PlusCircle, Trash2 } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		resolveBackendContext,
		waitForBackend,
		fetchTemplates,
		uploadTemplate,
		deleteTemplate,
		type TemplateConfig
	} from '$lib/backend';
	import Analytics from '$lib/illustrations/Analytics.svelte';

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let loading = $state(true);
	let uploading = $state(false);
	let pageError = $state('');
	let templates = $state<TemplateConfig[]>([]);

	// Upload form state
	let uploadLabel = $state('');
	let uploadSlug = $state('');
	let uploadFile = $state<File | null>(null);
	let uploadError = $state('');

	async function bootstrap() {
		loading = true;
		pageError = '';
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			await waitForBackend(apiBaseUrl);
			templates = await fetchTemplates(apiBaseUrl);
		} catch (err) {
			pageError = err instanceof Error ? err.message : 'Failed to load templates.';
		} finally {
			loading = false;
		}
	}

	onMount(bootstrap);

	function handleFileChange(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0] ?? null;
		uploadFile = file;
		// Auto-derive label and slug from filename if not set
		if (file && !uploadLabel) {
			const base = file.name.replace(/\.pptx$/i, '').replace(/[-\s]+/g, ' ').trim();
			uploadLabel = base.replace(/\b\w/g, (c) => c.toUpperCase());
		}
		if (file && !uploadSlug) {
			uploadSlug = file.name
				.replace(/\.pptx$/i, '')
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, '_')
				.replace(/^_+|_+$/g, '');
		}
	}

	async function handleUpload() {
		uploadError = '';
		if (!uploadFile) { uploadError = 'Please select a .pptx file.'; return; }
		if (!uploadLabel.trim()) { uploadError = 'Label is required.'; return; }
		if (!uploadSlug.trim()) { uploadError = 'Slug is required.'; return; }
		if (!/^[a-z0-9_]+$/.test(uploadSlug)) {
			uploadError = 'Slug must only contain lowercase letters, numbers, and underscores.';
			return;
		}

		uploading = true;
		try {
			const result = await uploadTemplate(apiBaseUrl, uploadFile, uploadLabel.trim(), uploadSlug.trim());
			// Navigate directly to the mapping page
			void goto(`/templates/${result.id}/map`);
		} catch (err) {
			uploadError = err instanceof Error ? err.message : 'Upload failed.';
			uploading = false;
		}
	}

	async function handleDelete(t: TemplateConfig) {
		if (!confirm(`Delete template "${t.label}"? This cannot be undone.`)) return;
		try {
			await deleteTemplate(apiBaseUrl, t.id);
			templates = templates.filter((x) => x.id !== t.id);
		} catch (err) {
			pageError = err instanceof Error ? err.message : 'Delete failed.';
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-8 p-8">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Report Templates</h1>
			<p class="mt-1 text-sm text-muted-foreground">
				Upload a custom .pptx and map its shapes to GA4 data fields.
			</p>
		</div>
	</div>

	{#if pageError}
		<div class="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
			{pageError}
		</div>
	{/if}

	<!-- Upload card -->
	<Card>
		<CardHeader>
			<div class="flex items-start gap-4">
				<div class="flex-1">
					<CardTitle class="flex items-center gap-2">
						<FileUp class="h-4 w-4" />
						Upload New Template
					</CardTitle>
					<CardDescription class="mt-1">
						Upload a PowerPoint (.pptx) file. You'll map each shape to a data field on the next screen.
					</CardDescription>
				</div>
				<Analytics class="hidden shrink-0 xl:block h-20 w-20 text-muted-foreground/20" />
			</div>
		</CardHeader>
		<CardContent class="space-y-4">
			{#if uploadError}
				<p class="text-sm text-destructive">{uploadError}</p>
			{/if}
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="space-y-2">
					<Label for="upload-label">Display Label</Label>
					<Input
						id="upload-label"
						bind:value={uploadLabel}
						placeholder="e.g. Acme Corp Report"
						disabled={uploading}
					/>
				</div>
				<div class="space-y-2">
					<Label for="upload-slug">Slug (report ID)</Label>
					<Input
						id="upload-slug"
						bind:value={uploadSlug}
						placeholder="e.g. acme_corp"
						disabled={uploading}
					/>
					<p class="text-xs text-muted-foreground">Lowercase letters, numbers, underscores only.</p>
				</div>
			</div>
			<div class="space-y-2">
				<Label for="upload-file">PowerPoint File</Label>
				<input
					id="upload-file"
					type="file"
					accept=".pptx"
					onchange={handleFileChange}
					disabled={uploading}
					class="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-xs file:font-medium file:text-foreground hover:file:bg-muted/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
				/>
			</div>
			<Button onclick={handleUpload} disabled={uploading || !uploadFile}>
				{#if uploading}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Uploading…
				{:else}
					<PlusCircle class="mr-2 h-4 w-4" />
					Upload &amp; Map
				{/if}
			</Button>
		</CardContent>
	</Card>

	<!-- Existing templates -->
	{#if loading}
		<div class="flex items-center justify-center py-16">
			<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
		</div>
	{:else if templates.length === 0}
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<Layers class="mb-4 h-12 w-12 text-muted-foreground/30" />
			<p class="text-sm font-medium text-muted-foreground">No custom templates yet</p>
			<p class="mt-1 text-xs text-muted-foreground/60">Upload a .pptx above to create your first template.</p>
		</div>
	{:else}
		<div class="space-y-3">
			<h2 class="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Your Templates</h2>
			{#each templates as t (t.id)}
				<Card class="transition-colors hover:bg-muted/30">
					<CardContent class="flex items-center gap-4 py-4">
						<Layers class="h-8 w-8 shrink-0 text-muted-foreground/40" />
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<span class="font-semibold truncate">{t.label}</span>
								<Badge variant="secondary" class="text-xs">{t.slug}</Badge>
								{#if t.has_field_map}
									<Badge variant="default" class="text-xs">Mapped</Badge>
								{:else}
									<Badge variant="outline" class="text-xs text-amber-600">Needs mapping</Badge>
								{/if}
							</div>
							<p class="mt-0.5 text-xs text-muted-foreground">
								{t.slide_count} slide{t.slide_count !== 1 ? 's' : ''} ·
								{t.ga4_property_id ? `GA4 property ${t.ga4_property_id}` : 'No GA4 property set'} ·
								Created {new Date(t.created_at).toLocaleDateString()}
							</p>
						</div>
						<div class="flex items-center gap-2 shrink-0">
							<Button variant="outline" size="sm" onclick={() => void goto(`/templates/${t.id}/map`)}>
								{t.has_field_map ? 'Edit Mapping' : 'Set Up Mapping'}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								class="text-destructive hover:text-destructive"
								onclick={() => handleDelete(t)}
							>
								<Trash2 class="h-4 w-4" />
							</Button>
						</div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
</div>
