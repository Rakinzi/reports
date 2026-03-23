<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		FileText,
		Plus,
		Download,
		Clock,
		CheckCircle2,
		XCircle,
		Loader2,
		RefreshCw,
		Settings
	} from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Label } from '$lib/components/ui/label';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { fetchJson, resolveBackendContext, type Report, type SettingsState, waitForBackend } from '$lib/backend';
	import { saveReportFromDesktop } from '$lib/desktop';

	const REPORT_OPTIONS = [
		{ value: 'econet_ai', label: 'Econet AI' },
		{ value: 'econet', label: 'Econet' },
		{ value: 'ecocash', label: 'EcoCash' },
		{ value: 'ecosure', label: 'Ecosure' },
		{ value: 'zimplats', label: 'Zimplats' },
		{ value: 'cancer_serve', label: 'Cancer Serve' }
	];

	const STAT_CARDS = [
		{ label: 'Total Reports', key: 'total', icon: FileText, color: 'text-zinc-400' },
		{ label: 'Completed', key: 'completed', icon: CheckCircle2, color: 'text-emerald-400' },
		{ label: 'Pending', key: 'pending', icon: Clock, color: 'text-amber-400' },
		{ label: 'Failed', key: 'failed', icon: XCircle, color: 'text-red-400' }
	] as const;

	let apiBaseUrl = $state('http://127.0.0.1:8000');
	let isTauri = $state(false);
	let backendReady = $state(false);
	let booting = $state(true);
	let refreshError = $state('');
	let reports = $state<Report[]>([]);
	let settings = $state<SettingsState>({
		configured: false,
		gemini_api_key_set: false,
		chrome_user_data_dir: '',
		chrome_profile_directory: 'Default',
		app_data_dir: ''
	});

	let generateOpen = $state(false);
	let generating = $state(false);
	let generateError = $state('');
	let reportName = $state('econet_ai');
	let startDateRaw = $state('');
	let endDateRaw = $state('');
	let reportDateRaw = $state('');

	function toGA4Date(raw: string): string {
		if (!raw) return '';
		const d = new Date(raw + 'T00:00:00');
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}

	function toLongDate(raw: string): string {
		if (!raw) return '';
		const d = new Date(raw + 'T00:00:00');
		return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
	}

	function toReportDate(raw: string): string {
		if (!raw) return '';
		const d = new Date(raw + 'T00:00:00');
		return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' });
	}

	const dateRange = $derived(
		startDateRaw && endDateRaw ? `${toLongDate(startDateRaw)} - ${toLongDate(endDateRaw)}` : ''
	);
	const startDate = $derived(toGA4Date(startDateRaw));
	const endDate = $derived(toGA4Date(endDateRaw));
	const reportDate = $derived(toReportDate(reportDateRaw));

	const stats = $derived({
		total: reports.length,
		completed: reports.filter((r) => r.status === 'completed').length,
		pending: reports.filter((r) => r.status === 'pending').length,
		failed: reports.filter((r) => r.status === 'failed').length
	});

	function statusBadge(status: string) {
		if (status === 'completed') return 'default';
		if (status === 'pending') return 'secondary';
		return 'destructive';
	}

	function formatDate(iso: string) {
		return new Date(iso).toLocaleString('en-GB', {
			day: '2-digit',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function loadSettings() {
		settings = await fetchJson<SettingsState>(apiBaseUrl, '/settings');
	}

	async function refreshReports() {
		refreshError = '';
		try {
			reports = await fetchJson<Report[]>(apiBaseUrl, '/reports');
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not load reports.';
		}
	}

	async function bootstrap() {
		booting = true;
		try {
			const desktop = await resolveBackendContext();
			apiBaseUrl = desktop.apiBaseUrl;
			isTauri = desktop.isTauri;
			await waitForBackend(apiBaseUrl);
			backendReady = true;
			await loadSettings();
			await refreshReports();
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not start the desktop app.';
		} finally {
			booting = false;
		}
	}

	async function downloadReport(report: Report) {
		const suggestedName =
			report.output_path?.split(/[\\/]/).pop() ??
			`${report.report_name}-${report.report_date.replaceAll(' ', '-')}.pptx`;

		if (isTauri) {
			try {
				await saveReportFromDesktop(apiBaseUrl, report.id, suggestedName);
				return;
			} catch (error) {
				refreshError = error instanceof Error ? error.message : 'Could not save the report.';
				return;
			}
		}

		window.open(`${apiBaseUrl}/reports/${report.id}/download`, '_blank', 'noopener,noreferrer');
	}

	function pollReport(id: number) {
		const interval = setInterval(async () => {
			try {
				const report = await fetchJson<Report>(apiBaseUrl, `/reports/${id}`);
				await refreshReports();
				if (report.status === 'completed') {
					clearInterval(interval);
					await downloadReport(report);
				} else if (report.status === 'failed') {
					clearInterval(interval);
				}
			} catch {
				// keep polling
			}
		}, 3000);
	}

	async function handleGenerate(event: SubmitEvent) {
		event.preventDefault();
		generating = true;
		generateError = '';

		try {
			const res = await fetchJson<{ id: number }>(apiBaseUrl, '/reports/generate', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					report_name: reportName,
					date_range: dateRange,
					report_date: reportDate,
					start_date: startDate,
					end_date: endDate
				})
			});
			generateOpen = false;
			await refreshReports();
			pollReport(res.id);
		} catch (error) {
			generateError = error instanceof Error ? error.message : 'Generation failed.';
		} finally {
			generating = false;
		}
	}

	onMount(() => {
		void bootstrap();
	});
</script>

<div class="flex h-full flex-col">
	<div class="flex items-center justify-between border-b border-zinc-800 px-8 py-5">
		<div>
			<h1 class="text-xl font-semibold text-zinc-100">Dashboard</h1>
			<p class="mt-0.5 text-sm text-zinc-400">Generate monthly reports from the bundled backend.</p>
		</div>
		<div class="flex items-center gap-3">
			<Button
				variant="outline"
				size="sm"
				class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100"
				onclick={() => void bootstrap()}
			>
				<RefreshCw class="mr-2 h-3.5 w-3.5" />
				Refresh
			</Button>
			<Button
				variant="outline"
				size="sm"
				class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100"
				onclick={() => goto('/settings')}
			>
				<Settings class="mr-2 h-3.5 w-3.5" />
				Settings
			</Button>
			<Button
				size="sm"
				class="bg-zinc-100 font-semibold text-zinc-900 hover:bg-zinc-200"
				onclick={() => (generateOpen = true)}
				disabled={!settings.configured || booting || !backendReady}
			>
				<Plus class="mr-2 h-4 w-4" />
				Generate Report
			</Button>
		</div>
	</div>

	<div class="flex-1 space-y-6 overflow-auto p-8">
		{#if booting}
			<div class="flex h-full min-h-[40vh] items-center justify-center">
				<div class="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-5 py-4 text-sm text-zinc-300">
					<Loader2 class="h-4 w-4 animate-spin" />
					Starting local backend...
				</div>
			</div>
		{:else}
			{#if !settings.configured}
				<Card class="border-amber-500/20 bg-amber-500/10">
					<CardHeader>
						<CardTitle class="text-amber-200">Finish setup before generating reports</CardTitle>
					</CardHeader>
					<CardContent class="space-y-3 text-sm text-amber-100/80">
						<p>Add a Gemini API key and point the app at a Chrome profile already signed into GA4.</p>
						<Button size="sm" class="bg-amber-200 text-zinc-900 hover:bg-amber-100" onclick={() => goto('/settings')}>
							Open Settings
						</Button>
						<p>Application data folder: <span class="font-mono text-xs">{settings.app_data_dir}</span></p>
					</CardContent>
				</Card>
			{/if}

			{#if refreshError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
					{refreshError}
				</div>
			{/if}

			<div class="grid grid-cols-4 gap-4">
				{#each STAT_CARDS as stat (stat.key)}
					<Card class="border-zinc-800 bg-zinc-900">
						<CardHeader class="flex flex-row items-center justify-between pb-2">
							<CardTitle class="text-sm font-medium text-zinc-400">{stat.label}</CardTitle>
							<stat.icon class="h-4 w-4 {stat.color}" />
						</CardHeader>
						<CardContent>
							<p class="text-3xl font-bold text-zinc-100">{stats[stat.key]}</p>
						</CardContent>
					</Card>
				{/each}
			</div>

			<Card class="border-zinc-800 bg-zinc-900">
				<CardHeader class="border-b border-zinc-800 px-6 py-4">
					<CardTitle class="text-base font-semibold text-zinc-100">All Reports</CardTitle>
				</CardHeader>
				<CardContent class="p-0">
					{#if reports.length === 0}
						<div class="flex flex-col items-center justify-center py-16 text-center">
							<FileText class="mb-3 h-10 w-10 text-zinc-600" />
							<p class="text-sm font-medium text-zinc-400">No reports yet</p>
							<p class="mt-1 text-xs text-zinc-600">Generate your first report to get started</p>
						</div>
					{:else}
						<Table>
							<TableHeader>
								<TableRow class="border-zinc-800 hover:bg-transparent">
									<TableHead class="font-medium text-zinc-400">Report</TableHead>
									<TableHead class="font-medium text-zinc-400">Date Range</TableHead>
									<TableHead class="font-medium text-zinc-400">Report Date</TableHead>
									<TableHead class="font-medium text-zinc-400">Status</TableHead>
									<TableHead class="font-medium text-zinc-400">Created</TableHead>
									<TableHead class="text-right font-medium text-zinc-400">Actions</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each reports as report (report.id)}
									<TableRow class="border-zinc-800 hover:bg-zinc-800/40">
										<TableCell class="font-medium text-zinc-100">
											{REPORT_OPTIONS.find((r) => r.value === report.report_name)?.label ?? report.report_name}
										</TableCell>
										<TableCell class="text-sm text-zinc-400">{report.date_range}</TableCell>
										<TableCell class="text-sm text-zinc-400">{report.report_date}</TableCell>
										<TableCell>
											<Badge variant={statusBadge(report.status)} class="text-xs capitalize">
												{report.status}
											</Badge>
										</TableCell>
										<TableCell class="text-xs text-zinc-500">{formatDate(report.created_at)}</TableCell>
										<TableCell class="text-right">
											{#if report.status === 'completed' && report.output_path}
												<Button
													size="sm"
													variant="ghost"
													class="text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
													onclick={() => void downloadReport(report)}
												>
													<Download class="mr-1.5 h-3.5 w-3.5" />
													Save
												</Button>
											{:else if report.status === 'pending'}
												<div class="flex items-center justify-end gap-1.5 text-xs text-zinc-500">
													<Loader2 class="h-3 w-3 animate-spin" />
													Processing
												</div>
											{:else if report.status === 'failed'}
												<span class="text-xs text-red-400" title={report.error ?? ''}>Failed</span>
											{/if}
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					{/if}
				</CardContent>
			</Card>
		{/if}
	</div>
</div>

<Dialog bind:open={generateOpen}>
	<DialogContent class="border-zinc-800 bg-zinc-900 text-zinc-100 sm:max-w-md">
		<DialogHeader>
			<DialogTitle class="text-zinc-100">Generate Report</DialogTitle>
			<DialogDescription class="text-zinc-400">
				Fill in the date window and the backend will generate the PPTX locally.
			</DialogDescription>
		</DialogHeader>

		<form onsubmit={handleGenerate} class="space-y-4 pt-2">
			{#if generateError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
					{generateError}
				</div>
			{/if}

			<div class="space-y-2">
				<Label class="text-zinc-300">Report</Label>
				<select
					bind:value={reportName}
					class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500"
				>
					{#each REPORT_OPTIONS as opt (opt.value)}
						<option value={opt.value}>{opt.label}</option>
					{/each}
				</select>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-2">
					<Label class="text-zinc-300">Start Date</Label>
					<input
						type="date"
						bind:value={startDateRaw}
						required
						class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500 [color-scheme:dark]"
					/>
				</div>
				<div class="space-y-2">
					<Label class="text-zinc-300">End Date</Label>
					<input
						type="date"
						bind:value={endDateRaw}
						required
						class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500 [color-scheme:dark]"
					/>
				</div>
			</div>

			{#if dateRange}
				<p class="text-xs text-zinc-500">Date range: <span class="text-zinc-400">{dateRange}</span></p>
			{/if}

			<div class="space-y-2">
				<Label class="text-zinc-300">Report Date</Label>
				<input
					type="date"
					bind:value={reportDateRaw}
					required
					class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500 [color-scheme:dark]"
				/>
				{#if reportDate}
					<p class="text-xs text-zinc-500">Formatted: <span class="text-zinc-400">{reportDate}</span></p>
				{/if}
			</div>

			<div class="flex justify-end gap-3 pt-2">
				<Button
					type="button"
					variant="outline"
					class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
					onclick={() => (generateOpen = false)}
					disabled={generating}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					class="bg-zinc-100 font-semibold text-zinc-900 hover:bg-zinc-200"
					disabled={generating}
				>
					{#if generating}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Generating...
					{:else}
						Generate
					{/if}
				</Button>
			</div>
		</form>
	</DialogContent>
</Dialog>
