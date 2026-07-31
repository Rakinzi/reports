<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { FileUp, FileCheck2, Loader2, Download } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Label } from '$lib/components/ui/label';
	import { resolveBackendContext, waitForBackend, makeFillablePdf } from '$lib/backend';

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let bootError = $state('');
	let processing = $state(false);
	let formError = $state('');
	let selectedFile = $state<File | null>(null);
	let resultUrl = $state('');
	let resultFilename = $state('');

	onMount(async () => {
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			await waitForBackend(apiBaseUrl);
		} catch (err) {
			bootError = err instanceof Error ? err.message : 'Failed to reach the backend.';
		}
	});

	onDestroy(() => {
		if (resultUrl) URL.revokeObjectURL(resultUrl);
	});

	function handleFileChange(e: Event) {
		const input = e.target as HTMLInputElement;
		selectedFile = input.files?.[0] ?? null;
		formError = '';
		if (resultUrl) {
			URL.revokeObjectURL(resultUrl);
			resultUrl = '';
		}
	}

	async function handleConvert() {
		formError = '';
		if (!selectedFile) {
			formError = 'Please select a .pdf file.';
			return;
		}
		processing = true;
		try {
			const { blob, filename } = await makeFillablePdf(apiBaseUrl, selectedFile);
			if (resultUrl) URL.revokeObjectURL(resultUrl);
			resultUrl = URL.createObjectURL(blob);
			resultFilename = filename;
		} catch (err) {
			formError = err instanceof Error ? err.message : 'Conversion failed.';
		} finally {
			processing = false;
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-8 p-8">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">PDF Fillable Form</h1>
		<p class="mt-1 text-sm text-muted-foreground">
			Upload a PDF form and get back a copy with fillable text and checkbox fields detected automatically.
		</p>
	</div>

	{#if bootError}
		<div class="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
			{bootError}
		</div>
	{/if}

	<Card>
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<FileUp class="h-4 w-4" />
				Upload PDF
			</CardTitle>
			<CardDescription class="mt-1">
				The form must have a text layer (not a scanned image) so field labels can be detected.
			</CardDescription>
		</CardHeader>
		<CardContent class="space-y-4">
			{#if formError}
				<p class="text-sm text-destructive">{formError}</p>
			{/if}
			<div class="space-y-2">
				<Label for="pdf-file">PDF File</Label>
				<input
					id="pdf-file"
					type="file"
					accept=".pdf"
					onchange={handleFileChange}
					disabled={processing}
					class="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-xs file:font-medium file:text-foreground hover:file:bg-muted/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
				/>
			</div>
			<Button onclick={handleConvert} disabled={processing || !selectedFile}>
				{#if processing}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Converting…
				{:else}
					<FileCheck2 class="mr-2 h-4 w-4" />
					Make Fillable
				{/if}
			</Button>
		</CardContent>
	</Card>

	{#if resultUrl}
		<Card>
			<CardHeader>
				<div class="flex items-center justify-between gap-4">
					<div class="flex items-center gap-3">
						<FileCheck2 class="h-8 w-8 shrink-0 text-emerald-600 dark:text-emerald-400" />
						<div>
							<CardTitle class="text-base">{resultFilename}</CardTitle>
							<CardDescription>Click into the fields below to try them out</CardDescription>
						</div>
					</div>
					<Button href={resultUrl} download={resultFilename} variant="outline">
						<Download class="mr-2 h-4 w-4" />
						Download
					</Button>
				</div>
			</CardHeader>
			<CardContent>
				<iframe
					src={resultUrl}
					title="Fillable PDF preview"
					class="h-[75vh] w-full rounded-md border border-border"
				></iframe>
			</CardContent>
		</Card>
	{/if}
</div>
