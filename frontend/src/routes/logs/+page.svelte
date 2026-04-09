<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Activity, FileText, Loader2, RefreshCw } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { fetchJson, resolveBackendContext, type LogResponse, waitForBackend } from '$lib/backend';

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let loading = $state(true);
	let pageError = $state('');
	let logPath = $state('');
	let lines = $state<string[]>([]);
	let logEl = $state<HTMLDivElement | null>(null);
	let es = $state<EventSource | null>(null);
	let autoScroll = $state(true);

	function connectSSE() {
		es?.close();
		const source = new EventSource(`${apiBaseUrl}/logs/stream`);
		es = source;

		source.onmessage = (event) => {
			if (event.data) {
				lines = [...lines, event.data];
				if (autoScroll && logEl) {
					setTimeout(() => {
						if (logEl) logEl.scrollTop = logEl.scrollHeight;
					}, 0);
				}
			}
		};

		source.onerror = () => {
			source.close();
			if (es === source) es = null;
		};
	}

	async function bootstrap() {
		loading = true;
		pageError = '';
		lines = [];
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			await waitForBackend(apiBaseUrl);
			const data = await fetchJson<LogResponse>(apiBaseUrl, '/logs?limit=0');
			logPath = data.path;
			connectSSE();
		} catch (error) {
			pageError = error instanceof Error ? error.message : 'Could not connect to backend.';
		} finally {
			loading = false;
		}
	}

	function handleScroll() {
		if (!logEl) return;
		autoScroll = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
	}

	onMount(() => void bootstrap());
	onDestroy(() => { es?.close(); es = null; });
</script>

<div class="flex h-full flex-col">
	<div class="flex items-center justify-between border-b border-zinc-800 px-8 py-5">
		<div>
			<h1 class="text-xl font-semibold text-zinc-100">Logs</h1>
			<p class="mt-0.5 text-sm text-zinc-400">
				Live backend output — sign-in, GA4 scraping, and report generation events.
			</p>
		</div>
		<Button
			type="button"
			variant="outline"
			size="sm"
			class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100"
			onclick={() => void bootstrap()}
			disabled={loading}
		>
			<RefreshCw class="mr-2 h-3.5 w-3.5" />
			Reconnect
		</Button>
	</div>

	<div class="flex-1 space-y-6 overflow-auto p-8">
		{#if loading}
			<div class="flex h-full min-h-[40vh] items-center justify-center">
				<div class="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-5 py-4 text-sm text-zinc-300">
					<Loader2 class="h-4 w-4 animate-spin" />
					Connecting to log stream...
				</div>
			</div>
		{:else}
			{#if pageError}
				<div class="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
					{pageError}
				</div>
			{/if}

			<div class="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
				<Card class="border-zinc-800 bg-zinc-900">
					<CardHeader class="border-b border-zinc-800">
						<div class="flex items-start justify-between gap-4">
							<div>
								<CardTitle class="text-zinc-100">Log Source</CardTitle>
								<CardDescription class="text-zinc-400">
									The backend writes runtime output to this file.
								</CardDescription>
							</div>
							<FileText class="h-5 w-5 text-zinc-500" />
						</div>
					</CardHeader>
					<CardContent class="space-y-4 pt-6">
						<div class="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-zinc-500">File Path</div>
							<div class="mt-2 break-all font-mono text-xs text-zinc-300">
								{logPath || 'not available yet'}
							</div>
						</div>
						<div class="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-zinc-500">Lines Received</div>
							<div class="mt-2 text-2xl font-semibold text-zinc-100">{lines.length}</div>
							<div class="mt-1 flex items-center gap-1.5 text-xs text-zinc-500">
								<span class="relative flex h-2 w-2">
									<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
									<span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
								</span>
								{es ? 'Live stream active' : 'Disconnected'}
							</div>
						</div>
						<div class="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-zinc-500">Auto-scroll</div>
							<div class="mt-2 text-sm text-zinc-300">
								{autoScroll ? 'On — scroll up to pause' : 'Paused — scroll to bottom to resume'}
							</div>
						</div>
					</CardContent>
				</Card>

				<Card class="border-zinc-800 bg-zinc-900">
					<CardHeader class="border-b border-zinc-800">
						<div class="flex items-start justify-between gap-4">
							<div>
								<CardTitle class="text-zinc-100">Runtime Feed</CardTitle>
								<CardDescription class="text-zinc-400">
									Streams in real time — open this during report generation to follow progress.
								</CardDescription>
							</div>
							<Activity class="h-5 w-5 text-zinc-500" />
						</div>
					</CardHeader>
					<CardContent class="pt-6">
						<div
							bind:this={logEl}
							onscroll={handleScroll}
							class="max-h-[65vh] overflow-auto rounded-xl border border-zinc-800 bg-black/40 p-4 font-mono text-xs leading-6 text-zinc-200"
						>
							{#if lines.length === 0}
								<div class="text-zinc-500">Waiting for log output...</div>
							{:else}
								{#each lines as line (line)}
									<div
										class:text-red-400={line.includes('[ERROR]')}
										class:text-amber-400={line.includes('[WARNING]')}
									>{line}</div>
								{/each}
							{/if}
						</div>
					</CardContent>
				</Card>
			</div>
		{/if}
	</div>
</div>
