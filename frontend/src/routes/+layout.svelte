<script lang="ts">
	import './layout.css';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { onNavigate } from '$app/navigation';
	import { FileText, LayoutDashboard, ChevronRight, Settings, ScrollText, Sun, Moon } from '@lucide/svelte';
	import { theme } from '$lib/theme.svelte';

	let { children } = $props();

	onMount(() => theme.init());

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
</script>

<div class="flex h-screen overflow-hidden bg-background text-foreground">
	<aside class="flex w-64 flex-col border-r border-border bg-card">
		<div class="flex h-16 items-center gap-3 border-b border-border px-6">
			<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
				<FileText class="h-4 w-4 text-foreground" />
			</div>
			<span class="font-semibold tracking-tight text-foreground">Reports</span>
		</div>

		<nav class="flex-1 space-y-1 p-4">
			<p class="px-3 pb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
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
		</nav>

		<!-- Theme toggle in sidebar footer -->
		<div class="border-t border-border p-4">
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
		</div>
	</aside>

	<main class="flex-1 overflow-auto">
		{@render children()}
	</main>
</div>
