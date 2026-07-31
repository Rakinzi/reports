<script lang="ts">
	import './layout.css';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { onNavigate } from '$app/navigation';
	import {
		FileText,
		LayoutDashboard,
		ChevronRight,
		Settings,
		ScrollText,
		Sun,
		Moon,
		Layers,
		RefreshCw,
		FileCheck2
	} from '@lucide/svelte';
	import { theme } from '$lib/theme.svelte';
	import { resolveBackendContext, waitForBackend } from '$lib/backend';
	import { restartBackendProcess } from '$lib/desktop';

	let { children } = $props();
	let isTauri = $state(false);
	let restartingBackend = $state(false);
	let backendActionMessage = $state('');
	let backendActionError = $state('');
	let pageTitle = $derived.by(() => {
		const pathname = $page.url.pathname;

		if (pathname === '/') return 'Dashboard | Reports';
		if (pathname === '/settings') return 'Settings | Reports';
		if (pathname === '/logs') return 'Logs | Reports';
		if (pathname === '/templates') return 'Report Templates | Reports';
		if (pathname === '/pdf-fillable') return 'PDF Fillable Form | Reports';
		if (/^\/templates\/[^/]+\/map\/?$/.test(pathname)) return 'Template Mapping | Reports';
		if (/^\/reports\/[^/]+\/preview\/?$/.test(pathname)) return 'Report Preview | Reports';

		return 'Reports';
	});

	onMount(() => {
		theme.init();
		void (async () => {
			try {
				const desktop = await resolveBackendContext();
				isTauri = desktop.isTauri;
			} catch {
				isTauri = false;
			}
		})();
	});

	// Smooth page transitions via the native View Transitions API (Chromium/Tauri = full support)
	onNavigate((navigation) => {
		if (!document.startViewTransition) return;
		return new Promise((resolve) => {
			document.startViewTransition(async () => {
				resolve();
				await navigation.complete;
			});
		});
	});

	async function restartBackend() {
		restartingBackend = true;
		backendActionMessage = '';
		backendActionError = '';
		try {
			const desktop = await resolveBackendContext();
			await restartBackendProcess();
			await waitForBackend(desktop.apiBaseUrl, { attempts: 120, intervalMs: 500 });
			backendActionMessage = 'Backend restarted. Reloading...';
			window.location.reload();
		} catch (error) {
			backendActionError =
				error instanceof Error ? error.message : 'Could not restart the backend.';
		} finally {
			restartingBackend = false;
		}
	}
</script>

<svelte:head>
	<title>{pageTitle}</title>
</svelte:head>

<div class="flex h-screen overflow-hidden bg-background text-foreground">
	<aside class="flex w-64 flex-col border-r border-border bg-card">
		<div class="flex h-16 items-center gap-3 border-b border-border px-6">
			<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
				<FileText class="h-4 w-4 text-foreground" />
			</div>
			<span class="font-semibold tracking-tight text-foreground">Reports</span>
		</div>

		<nav class="flex-1 space-y-1 p-4">
			<p class="px-3 pb-2 text-xs font-medium tracking-wider text-muted-foreground uppercase">
				Navigation
			</p>
			<a
				href="/"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/'
					? 'bg-muted text-foreground'
					: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
			>
				<LayoutDashboard class="h-4 w-4" />
				Dashboard
				{#if $page.url.pathname === '/'}
					<ChevronRight class="ml-auto h-3 w-3 text-muted-foreground" />
				{/if}
			</a>
			<a
				href="/settings"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/settings'
					? 'bg-muted text-foreground'
					: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
			>
				<Settings class="h-4 w-4" />
				Settings
				{#if $page.url.pathname === '/settings'}
					<ChevronRight class="ml-auto h-3 w-3 text-muted-foreground" />
				{/if}
			</a>
			<a
				href="/logs"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/logs'
					? 'bg-muted text-foreground'
					: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
			>
				<ScrollText class="h-4 w-4" />
				Logs
				{#if $page.url.pathname === '/logs'}
					<ChevronRight class="ml-auto h-3 w-3 text-muted-foreground" />
				{/if}
			</a>
			<a
				href="/templates"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname.startsWith('/templates')
					? 'bg-muted text-foreground'
					: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
			>
				<Layers class="h-4 w-4" />
				Templates
				{#if $page.url.pathname.startsWith('/templates')}
					<ChevronRight class="ml-auto h-3 w-3 text-muted-foreground" />
				{/if}
			</a>
			<a
				href="/pdf-fillable"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/pdf-fillable'
					? 'bg-muted text-foreground'
					: 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}"
			>
				<FileCheck2 class="h-4 w-4" />
				PDF Fillable Form
				{#if $page.url.pathname === '/pdf-fillable'}
					<ChevronRight class="ml-auto h-3 w-3 text-muted-foreground" />
				{/if}
			</a>
		</nav>

		<!-- Theme toggle in sidebar footer -->
		<div class="space-y-2 border-t border-border p-4">
			{#if isTauri}
				<button
					onclick={() => void restartBackend()}
					disabled={restartingBackend}
					class="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
					title="Restart the bundled backend"
				>
					<RefreshCw class={`h-4 w-4 ${restartingBackend ? 'animate-spin' : ''}`} />
					{restartingBackend ? 'Restarting backend...' : 'Restart Backend'}
				</button>
			{/if}
			<button
				onclick={() => theme.toggle()}
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
				title="Toggle light/dark mode"
			>
				{#if theme.current === 'dark'}
					<Sun class="h-4 w-4" />
					Light mode
				{:else}
					<Moon class="h-4 w-4" />
					Dark mode
				{/if}
			</button>
			{#if backendActionMessage}
				<p class="px-3 text-xs text-emerald-600 dark:text-emerald-300">{backendActionMessage}</p>
			{/if}
			{#if backendActionError}
				<p class="px-3 text-xs text-red-600 dark:text-red-300">{backendActionError}</p>
			{/if}
		</div>
	</aside>

	<main class="flex-1 overflow-auto">
		{@render children()}
	</main>
</div>
