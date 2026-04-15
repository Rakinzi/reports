<script lang="ts">
	import { ExternalLink } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { openExternalUrl } from '$lib/desktop';

	const CHROME_URL = 'https://www.google.com/chrome/';
	const EDGE_URL = 'https://www.microsoft.com/en-us/edge/download';
	const CHROMIUM_URL = 'https://www.chromium.org/getting-involved/download-chromium/';

	type Variant = 'inline' | 'card';

	let {
		variant = 'inline'
	}: {
		variant?: Variant;
	} = $props();
</script>

<div class={variant === 'card' ? 'rounded-xl border border-border bg-muted/50 p-4' : ''}>
	<div class="space-y-3">
		<div>
			<p class="text-sm font-medium text-foreground">Install a compatible browser</p>
			<p class="mt-1 text-xs text-muted-foreground">
				This app needs Google Chrome, Microsoft Edge, or Chromium for the app-managed Google Analytics session.
			</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<Button size="sm" variant="outline" onclick={() => void openExternalUrl(CHROME_URL)}>
				<ExternalLink class="mr-2 h-3.5 w-3.5" />
				Install Chrome
			</Button>
			<Button size="sm" variant="outline" onclick={() => void openExternalUrl(EDGE_URL)}>
				<ExternalLink class="mr-2 h-3.5 w-3.5" />
				Install Edge
			</Button>
			<Button size="sm" variant="outline" onclick={() => void openExternalUrl(CHROMIUM_URL)}>
				<ExternalLink class="mr-2 h-3.5 w-3.5" />
				Chromium Options
			</Button>
		</div>
	</div>
</div>
