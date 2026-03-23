<script lang="ts">
	import './layout.css';
	import { page } from '$app/stores';
	import { FileText, LayoutDashboard, ChevronRight, Settings, ScrollText } from '@lucide/svelte';

	let { children } = $props();
</script>

<div class="flex h-screen overflow-hidden bg-zinc-950 text-zinc-100">
	<aside class="flex w-64 flex-col border-r border-zinc-800 bg-zinc-900">
		<div class="flex h-16 items-center gap-3 border-b border-zinc-800 px-6">
			<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-700">
				<FileText class="h-4 w-4 text-zinc-100" />
			</div>
			<span class="font-semibold tracking-tight text-zinc-100">Reports</span>
		</div>

		<nav class="flex-1 space-y-1 p-4">
			<p class="px-3 pb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
				Navigation
			</p>
			<a
				href="/"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/'
						? 'bg-zinc-800 text-zinc-100'
						: 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-100'}"
			>
				<LayoutDashboard class="h-4 w-4" />
				Dashboard
				{#if $page.url.pathname === '/'}
					<ChevronRight class="ml-auto h-3 w-3 text-zinc-500" />
				{/if}
			</a>
			<a
				href="/settings"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/settings'
						? 'bg-zinc-800 text-zinc-100'
						: 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-100'}"
			>
				<Settings class="h-4 w-4" />
				Settings
				{#if $page.url.pathname === '/settings'}
					<ChevronRight class="ml-auto h-3 w-3 text-zinc-500" />
				{/if}
			</a>
			<a
				href="/logs"
				class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
						{$page.url.pathname === '/logs'
						? 'bg-zinc-800 text-zinc-100'
						: 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-100'}"
			>
				<ScrollText class="h-4 w-4" />
				Logs
				{#if $page.url.pathname === '/logs'}
					<ChevronRight class="ml-auto h-3 w-3 text-zinc-500" />
				{/if}
			</a>
		</nav>
	</aside>

	<main class="flex-1 overflow-auto">
		{@render children()}
	</main>
</div>
