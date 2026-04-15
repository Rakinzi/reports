<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { ArrowLeft, KeyRound, Loader2, Save, ShieldCheck } from '@lucide/svelte';
	import Auth from '$lib/illustrations/Auth.svelte';
	import Session from '$lib/illustrations/Session.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import BrowserInstallHelp from '$lib/components/BrowserInstallHelp.svelte';
	import {
		fetchJson,
		resolveBackendContext,
		type SettingsState,
		waitForBackend
	} from '$lib/backend';

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let loading = $state(true);
	let saving = $state(false);
	let openingSignIn = $state(false);
	let pageError = $state('');
	let pageMessage = $state('');
	let settings = $state<SettingsState>({
		configured: false,
		gemini_api_key_set: false,
		browser_available: false,
		browser_path: '',
		chrome_user_data_dir: '',
		chrome_profile_directory: 'Default',
		chrome_profile_label: 'App Google Session',
		app_data_dir: ''
	});

	let geminiApiKey = $state('');

	async function loadSettings() {
		settings = await fetchJson<SettingsState>(apiBaseUrl, '/settings');
	}

	async function bootstrap() {
		loading = true;
		pageError = '';
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			await waitForBackend(apiBaseUrl);
			await loadSettings();
		} catch (error) {
			pageError = error instanceof Error ? error.message : 'Could not load settings.';
		} finally {
			loading = false;
		}
	}

	async function saveSettings() {
		saving = true;
		pageError = '';
		pageMessage = '';
		try {
			settings = await fetchJson<SettingsState>(apiBaseUrl, '/settings', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					gemini_api_key: geminiApiKey
				})
			});
			geminiApiKey = '';
			pageMessage = 'Settings saved.';
		} catch (error) {
			pageError = error instanceof Error ? error.message : 'Could not save settings.';
		} finally {
			saving = false;
		}
	}

	async function openGoogleSignIn() {
		openingSignIn = true;
		pageError = '';
		pageMessage = '';
		try {
			settings = await fetchJson<SettingsState>(apiBaseUrl, '/settings', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					gemini_api_key: geminiApiKey
				})
			});
			geminiApiKey = '';
			await fetchJson<{ started: boolean; already_running: boolean }>(apiBaseUrl, '/settings/google-sign-in', {
				method: 'POST'
			});
			pageMessage =
				'A managed browser window opened. Sign in to Google and confirm you can access GA4, then close it and return here.';
		} catch (error) {
			pageError = error instanceof Error ? error.message : 'Could not open browser sign-in.';
		} finally {
			openingSignIn = false;
		}
	}

	onMount(() => {
		void bootstrap();
	});
</script>

<div class="flex h-full flex-col">
	<div class="flex items-center justify-between border-b border-border px-8 py-5">
		<div>
			<h1 class="text-xl font-semibold text-foreground">Settings</h1>
			<p class="mt-0.5 text-sm text-muted-foreground">
				Configure the local Gemini key and the app-managed Google session used for report generation.
			</p>
		</div>
		<div class="flex items-center gap-3">
			<Button
				variant="outline"
				size="sm"
				onclick={() => goto('/')}
			>
				<ArrowLeft class="mr-2 h-3.5 w-3.5" />
				Dashboard
			</Button>
			<Button
				size="sm"
				onclick={() => void saveSettings()}
				disabled={saving || loading}
			>
				{#if saving}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Saving...
				{:else}
					<Save class="mr-2 h-4 w-4" />
					Save Settings
				{/if}
			</Button>
		</div>
	</div>

	<div class="flex-1 space-y-6 overflow-auto p-8">
		{#if loading}
			<div class="flex h-full min-h-[40vh] items-center justify-center">
				<div class="flex items-center gap-3 rounded-xl border border-border bg-card px-5 py-4 text-sm text-foreground">
					<Loader2 class="h-4 w-4 animate-spin" />
					Loading backend settings...
				</div>
			</div>
		{:else}
			{#if pageError}
				<div class="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
					{pageError}
				</div>
			{/if}

			{#if pageMessage}
				<div class="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
					{pageMessage}
				</div>
			{/if}

			<div class="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
				<Card>
					<CardHeader class="border-b border-border">
						<div class="flex items-start justify-between gap-4">
							<div>
								<CardTitle>API Configuration</CardTitle>
								<CardDescription>
									Store the Gemini API key used by the local backend.
								</CardDescription>
							</div>
							<div class="flex flex-col items-end gap-2">
								<Badge variant={settings.gemini_api_key_set ? 'default' : 'secondary'}>
									{settings.gemini_api_key_set ? 'Configured' : 'Missing'}
								</Badge>
								<Auth class="h-14 w-14 text-muted-foreground/25 shrink-0" />
							</div>
						</div>
					</CardHeader>
					<CardContent class="space-y-4 pt-6">
						<div class="space-y-2">
							<Label>Gemini API Key</Label>
							<Input
								type="password"
								bind:value={geminiApiKey}
								placeholder={settings.gemini_api_key_set ? 'Stored locally. Enter a new value to replace it.' : 'AIza...'}
							/>
							<p class="text-xs text-muted-foreground">
								If a key is already saved, leave this blank unless you want to replace it.
							</p>
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardHeader class="border-b border-border">
						<CardTitle>Local Runtime</CardTitle>
						<CardDescription>
							App data and the managed browser session are stored on this machine.
						</CardDescription>
					</CardHeader>
					<CardContent class="space-y-4 pt-6">
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Compatible Browser</div>
							<div class="mt-2 text-sm text-foreground">
								{settings.browser_available ? 'Detected' : 'Not found'}
							</div>
							<div class="mt-2 break-all font-mono text-xs text-muted-foreground">
								{settings.browser_path || 'Install Google Chrome, Microsoft Edge, or Chromium'}
							</div>
							{#if !settings.browser_available}
								<div class="mt-4">
									<BrowserInstallHelp />
								</div>
							{/if}
						</div>
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Application Data</div>
							<div class="mt-2 break-all font-mono text-xs text-foreground">
								{settings.app_data_dir || 'not available yet'}
							</div>
							<p class="mt-3 text-xs text-muted-foreground">
								On macOS this folder survives uninstall, so desktop cache/session data can outlive the
								app bundle.
							</p>
						</div>
						<div class="rounded-xl border border-border bg-muted/50 p-4">
							<div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Session Profile</div>
							<div class="mt-2 text-sm text-foreground">
								{settings.chrome_profile_label || 'App Google Session'}
							</div>
							<div class="mt-2 break-all font-mono text-xs text-muted-foreground">
								{settings.chrome_user_data_dir || 'not available yet'}
							</div>
						</div>
					</CardContent>
				</Card>
			</div>

			<Card>
				<CardHeader class="border-b border-border">
					<div class="flex items-start justify-between gap-4">
						<div>
							<CardTitle>Google Session</CardTitle>
							<CardDescription>
								Sign in once with the app-managed browser profile, then reuse that session for future reports.
							</CardDescription>
						</div>
						<ShieldCheck class="h-5 w-5 text-muted-foreground" />
					</div>
				</CardHeader>
				<CardContent class="flex items-start gap-6 pt-6">
					<div class="flex-1 space-y-4">
						<div class="rounded-xl border border-border bg-muted/50 p-4 text-sm text-foreground">
							The sign-in window should stay open until you close it. Once you confirm GA4 access there, later reports reuse the same saved session in the app-managed profile directory.
						</div>
						<div class="flex items-center gap-3">
							<Button
								type="button"
								variant="outline"
								onclick={() => void openGoogleSignIn()}
								disabled={openingSignIn || !settings.browser_available}
							>
								{#if openingSignIn}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Opening browser...
								{:else}
									<KeyRound class="mr-2 h-4 w-4" />
									Open Browser Sign-In
								{/if}
							</Button>
						</div>
					</div>
					<Session class="hidden xl:block shrink-0 h-28 w-28 text-muted-foreground/25" />
				</CardContent>
			</Card>
		{/if}
	</div>
</div>
