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
	<div class="flex items-center justify-between border-b border-border px-8 py-5">
		<div>
			<h1 class="text-xl font-semibold text-foreground">Logs</h1>
			<p class="mt-0.5 text-sm text-muted-foreground">
				Live backend output — sign-in, GA4 scraping, and report generation events.
			</p>
		</div>
		<Button
			type="button"
			variant="outline"
			size="sm"
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
				<div class="flex items-center gap-3 rounded-xl border border-border bg-card px-5 py-4 text-sm text-foreground">
					<Loader2 class="h-4 w-4 animate-spin" />
					Connecting to log stream...
				</div>
			</div>
		{:else}
			{#if pageError}
				<div class="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
					{pageError}
				</div>
			{/if}

			<div class="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
				<Card>
					<CardHeader class="border-b border-border">
						<div class="flex items-start justify-between gap-4">
							<div>
								<CardTitle>Log Source</CardTitle>
								<CardDescription>
									The backend writes runtime output to this file.
								</CardDescription>
							</div>
							<FileText class="h-5 w-5 text-muted-foreground" />
						</div>
					</CardHeader>
					<CardContent class="space-y-4 pt-6">
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">File Path</div>
							<div class="mt-2 break-all font-mono text-xs text-foreground">
								{logPath || 'not available yet'}
							</div>
						</div>
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Lines Received</div>
							<div class="mt-2 text-2xl font-semibold text-foreground">{lines.length}</div>
							<div class="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
								<span class="relative flex h-2 w-2">
									<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
									<span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
								</span>
								{es ? 'Live stream active' : 'Disconnected'}
							</div>
						</div>
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Auto-scroll</div>
							<div class="mt-2 text-sm text-foreground">
								{autoScroll ? 'On — scroll up to pause' : 'Paused — scroll to bottom to resume'}
							</div>
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardHeader class="border-b border-border">
						<div class="flex items-start justify-between gap-4">
							<div>
								<CardTitle>Runtime Feed</CardTitle>
								<CardDescription>
									Streams in real time — open this during report generation to follow progress.
								</CardDescription>
							</div>
							<Activity class="h-5 w-5 text-muted-foreground" />
						</div>
					</CardHeader>
					<CardContent class="pt-6">
						<div
							bind:this={logEl}
							onscroll={handleScroll}
							class="max-h-[65vh] overflow-auto rounded-xl border border-border bg-muted/30 p-4 font-mono text-xs leading-6 text-foreground"
						>
							{#if lines.length === 0}
								<div class="text-muted-foreground">Waiting for log output...</div>
							{:else}
								{#each lines as line (line)}
									<div
										class:text-red-500={line.includes('[ERROR]')}
										class:text-amber-500={line.includes('[WARNING]')}
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
