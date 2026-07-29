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
		Settings,
		Square,
		Trash2,
		ChevronLeft,
		ChevronRight
	} from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import BootScreen from '$lib/components/BootScreen.svelte';
	import NoData from '$lib/illustrations/NoData.svelte';
	import Setup from '$lib/illustrations/Setup.svelte';
	import BrowserInstallHelp from '$lib/components/BrowserInstallHelp.svelte';
	import StatusOrb from '$lib/components/StatusOrb.svelte';
	import GeneratingPulse from '$lib/components/GeneratingPulse.svelte';
	import SpinnerArc from '$lib/components/SpinnerArc.svelte';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
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
	import { fetchJson, fetchReportOptions, generateQuickReport, resolveBackendContext, type Report, type ReportOption, type SettingsState, waitForBackend } from '$lib/backend';
	import { saveReportFromDesktop } from '$lib/desktop';

	const FALLBACK_REPORT_OPTIONS: ReportOption[] = [
		{ value: 'econet_ai', label: 'Econet AI', source: 'builtin' },
		{ value: 'econet', label: 'Econet', source: 'builtin' },
		{ value: 'infraco', label: 'Infraco', source: 'builtin' },
		{ value: 'ecocash', label: 'Eco Cash', source: 'builtin' },
		{ value: 'ecosure', label: 'Ecosure', source: 'builtin' },
		{ value: 'zimplats', label: 'Zimplats', source: 'builtin' },
		{ value: 'cancer_serve', label: 'Cancer Serve', source: 'builtin' },
		{ value: 'dicomm', label: 'Dicomm McCann', source: 'builtin' },
		{ value: 'delta', label: 'Delta', source: 'builtin' },
		{ value: 'bancabc', label: 'BancABC', source: 'builtin' },
		{ value: 'mimosa', label: 'Mimosa', source: 'builtin' }
	];

	let reportOptions = $state<ReportOption[]>(FALLBACK_REPORT_OPTIONS);

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
		browser_available: false,
		browser_path: '',
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
	let slide1Name = $state('');
	let slide1LogoDataUrl = $state('');
	let slide1LogoFileName = $state('');
	let redoingReportId = $state<number | null>(null);

	let quickOpen = $state(false);
	let quickGenerating = $state(false);
	let quickError = $state('');
	let quickPropertyId = $state('');
	let quickClientName = $state('');
	let quickGscUrl = $state('');
	let quickStartDateRaw = $state('');
	let quickEndDateRaw = $state('');
	let quickReportDateRaw = $state('');
	let quickLogoDataUrl = $state('');
	let quickLogoFileName = $state('');

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
	const selectedReportLabel = $derived(
		reportOptions.find((option) => option.value === reportName)?.label ?? reportName
	);
	const preserveSlide1Logo = $derived(
		reportName === 'dicomm' || selectedReportLabel.trim().toLowerCase() === 'dicomm mccann'
	);

	$effect(() => {
		if (preserveSlide1Logo) {
			slide1LogoDataUrl = '';
			slide1LogoFileName = '';
		}
	});

	const today = new Date().toISOString().slice(0, 10);
	const dateValidationError = $derived((() => {
		if (!startDateRaw || !endDateRaw) return '';
		if (startDateRaw > today) return 'Start date cannot be in the future.';
		if (endDateRaw > today) return 'End date cannot be in the future.';
		if (startDateRaw > endDateRaw) return 'Start date must be before end date.';
		return '';
	})());

	const quickDateRange = $derived(
		quickStartDateRaw && quickEndDateRaw
			? `${toLongDate(quickStartDateRaw)} - ${toLongDate(quickEndDateRaw)}`
			: ''
	);
	const quickStartDate = $derived(toGA4Date(quickStartDateRaw));
	const quickEndDate = $derived(toGA4Date(quickEndDateRaw));
	const quickReportDate = $derived(toReportDate(quickReportDateRaw));

	const quickDateValidationError = $derived((() => {
		if (!quickStartDateRaw || !quickEndDateRaw) return '';
		if (quickStartDateRaw > today) return 'Start date cannot be in the future.';
		if (quickEndDateRaw > today) return 'End date cannot be in the future.';
		if (quickStartDateRaw > quickEndDateRaw) return 'Start date must be before end date.';
		return '';
	})());

	function handleQuickLogoChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		quickLogoDataUrl = '';
		quickLogoFileName = '';
		if (!file) return;

		const reader = new FileReader();
		reader.onload = () => {
			quickLogoDataUrl = typeof reader.result === 'string' ? reader.result : '';
			quickLogoFileName = file.name;
		};
		reader.onerror = () => {
			quickError = 'Could not read the selected logo file.';
		};
		reader.readAsDataURL(file);
	}

	async function handleQuickGenerate(event: SubmitEvent) {
		event.preventDefault();
		if (quickDateValidationError) return;
		quickGenerating = true;
		quickError = '';

		try {
			const res = await generateQuickReport(apiBaseUrl, {
				ga4_property_id: quickPropertyId.trim(),
				client_name: quickClientName.trim(),
				gsc_url: quickGscUrl.trim(),
				date_range: quickDateRange,
				report_date: quickReportDate,
				start_date: quickStartDate,
				end_date: quickEndDate,
				slide1_logo_data_url: quickLogoDataUrl,
				slide1_logo_filename: quickLogoFileName
			});
			quickOpen = false;
			await refreshReports();
			pollReport(res.id);
		} catch (error) {
			quickError = error instanceof Error ? error.message : 'Generation failed.';
		} finally {
			quickGenerating = false;
		}
	}

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
			try {
				reportOptions = await fetchReportOptions(apiBaseUrl);
			} catch {
				// Keep fallback options if endpoint not yet available
			}
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not start the desktop app.';
		} finally {
			booting = false;
		}
	}

	// Parse report dates back to local YYYY-MM-DD without UTC offset shifts.
	function toLocalISO(s: string) {
		const d = new Date(s + ' 00:00:00');
		if (isNaN(d.getTime())) return '';
		const y = d.getFullYear();
		const m = String(d.getMonth() + 1).padStart(2, '0');
		const day = String(d.getDate()).padStart(2, '0');
		return `${y}-${m}-${day}`;
	}

	function reportDateParts(report: Report) {
		const parts = report.date_range.split(' - ');
		return {
			startRaw: parts.length === 2 ? toLocalISO(parts[0].trim()) : '',
			endRaw: parts.length === 2 ? toLocalISO(parts[1].trim()) : '',
			reportRaw: toLocalISO(report.report_date)
		};
	}

	function retryReport(report: Report) {
		const dates = reportDateParts(report);
		startDateRaw = dates.startRaw;
		endDateRaw = dates.endRaw;
		// Parse "03 March 2026" back to YYYY-MM-DD
		reportDateRaw = dates.reportRaw;
		reportName = report.report_name;
		slide1Name = '';
		slide1LogoDataUrl = '';
		slide1LogoFileName = '';
		generateError = '';
		generateOpen = true;
	}

	async function redoReport(report: Report) {
		const dates = reportDateParts(report);
		if (!dates.startRaw || !dates.endRaw || !dates.reportRaw) {
			refreshError = 'Could not reuse this report’s dates.';
			return;
		}

		redoingReportId = report.id;
		refreshError = '';
		try {
			const option = reportOptions.find((item) => item.value === report.report_name);
			const response = await fetchJson<{ id: number }>(apiBaseUrl, '/reports/generate', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					report_name: report.report_name,
					date_range: report.date_range,
					report_date: report.report_date,
					start_date: toGA4Date(dates.startRaw),
					end_date: toGA4Date(dates.endRaw),
					slide1_source_name: option?.label ?? report.report_name,
					slide1_name: '',
					slide1_logo_data_url: '',
					slide1_logo_filename: ''
				})
			});
			await refreshReports();
			pollReport(response.id);
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not redo the report.';
		} finally {
			redoingReportId = null;
		}
	}

	function handleLogoChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		slide1LogoDataUrl = '';
		slide1LogoFileName = '';
		if (preserveSlide1Logo) {
			input.value = '';
			return;
		}
		if (!file) return;

		const reader = new FileReader();
		reader.onload = () => {
			slide1LogoDataUrl = typeof reader.result === 'string' ? reader.result : '';
			slide1LogoFileName = file.name;
		};
		reader.onerror = () => {
			generateError = 'Could not read the selected logo file.';
		};
		reader.readAsDataURL(file);
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

	async function stopReport(id: number) {
		try {
			await fetchJson(apiBaseUrl, `/reports/${id}/cancel`, { method: 'POST' });
			await refreshReports();
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not stop the report.';
		}
	}

	const PAGE_SIZE = 10;
	let currentPage = $state(1);
	const totalPages = $derived(Math.max(1, Math.ceil(reports.length / PAGE_SIZE)));
	const pagedReports = $derived(reports.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE));

	$effect(() => {
		// Reset to page 1 whenever the report list changes length (delete / new report)
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		reports.length;
		currentPage = 1;
	});

	let deleteOpen = $state(false);
	let deleteTargetId = $state<number | null>(null);

	function promptDelete(id: number) {
		deleteTargetId = id;
		deleteOpen = true;
	}

	async function confirmDelete() {
		if (deleteTargetId === null) return;
		const id = deleteTargetId;
		deleteOpen = false;
		deleteTargetId = null;
		try {
			await fetchJson(apiBaseUrl, `/reports/${id}`, { method: 'DELETE' });
			await refreshReports();
		} catch (error) {
			refreshError = error instanceof Error ? error.message : 'Could not delete the report.';
		}
	}

	function pollReport(id: number) {
		const interval = setInterval(async () => {
			try {
				const report = await fetchJson<Report>(apiBaseUrl, `/reports/${id}`);
				await refreshReports();
				if (report.status === 'completed') {
					clearInterval(interval);
					goto(`/reports/${id}/preview`);
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
		if (dateValidationError) return;
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
					end_date: endDate,
					slide1_source_name: selectedReportLabel,
					slide1_name: slide1Name.trim(),
					slide1_logo_data_url: slide1LogoDataUrl,
					slide1_logo_filename: slide1LogoFileName
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
	<div class="flex items-center justify-between border-b border-border px-8 py-5">
		<div>
			<h1 class="text-xl font-semibold text-foreground">Dashboard</h1>
			<p class="mt-0.5 text-sm text-muted-foreground">Generate monthly reports from the bundled backend.</p>
		</div>
		<div class="flex items-center gap-3">
			<Button
				variant="outline"
				size="sm"
				onclick={() => void bootstrap()}
			>
				<RefreshCw class="mr-2 h-3.5 w-3.5" />
				Refresh
			</Button>
			<Button
				variant="outline"
				size="sm"
				onclick={() => goto('/settings')}
			>
				<Settings class="mr-2 h-3.5 w-3.5" />
				Settings
			</Button>
			<Button
				size="sm"
				onclick={() => (generateOpen = true)}
				disabled={!settings.configured || booting || !backendReady}
			>
				<Plus class="mr-2 h-4 w-4" />
				Generate Report
			</Button>
			<Button
				size="sm"
				variant="outline"
				onclick={() => (quickOpen = true)}
				disabled={!settings.configured || booting || !backendReady}
			>
				<Plus class="mr-2 h-4 w-4" />
				Quick Report
			</Button>
		</div>
	</div>

	<div class="flex-1 space-y-6 overflow-auto p-8">
		{#if booting}
			<div class="flex h-full min-h-[40vh] items-center justify-center">
				<BootScreen message="Starting local backend..." />
			</div>
		{:else}
			{#if !settings.configured}
				<Card class="border-amber-500/20 bg-amber-500/10">
					<CardHeader>
						<CardTitle class="text-amber-700 dark:text-amber-200">Finish setup before generating reports</CardTitle>
					</CardHeader>
						<CardContent class="flex items-start gap-6 text-sm text-amber-800/80 dark:text-amber-100/80">
							<div class="flex-1 space-y-3">
								<p>Add a Gemini API key and make sure Google Chrome, Microsoft Edge, or Chromium is installed for the app-managed session.</p>
								<Button size="sm" class="bg-amber-200 text-zinc-900 hover:bg-amber-100" onclick={() => goto('/settings')}>
									Open Settings
								</Button>
								{#if !settings.browser_available}
									<p>No compatible Chromium browser detected on this machine yet.</p>
									<BrowserInstallHelp />
								{/if}
								<p>Application data folder: <span class="font-mono text-xs">{settings.app_data_dir}</span></p>
							</div>
							<Setup class="hidden shrink-0 xl:block h-24 w-24 text-amber-600/50 dark:text-amber-300/40" />
						</CardContent>
					</Card>
				{/if}

			{#if refreshError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
					{refreshError}
				</div>
			{/if}

			<div class="grid grid-cols-4 gap-4">
				{#each STAT_CARDS as stat (stat.key)}
					<Card>
						<CardHeader class="flex flex-row items-center justify-between pb-2">
							<CardTitle class="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
							<stat.icon class="h-4 w-4 {stat.color}" />
						</CardHeader>
						<CardContent>
							<p class="text-3xl font-bold text-foreground">{stats[stat.key]}</p>
						</CardContent>
					</Card>
				{/each}
			</div>

			<Card>
				<CardHeader class="border-b border-border px-6 py-4">
					<CardTitle class="text-base font-semibold text-foreground">All Reports</CardTitle>
				</CardHeader>
				<CardContent class="p-0">
					{#if reports.length === 0}
						<div class="flex flex-col items-center justify-center py-16 text-center">
							<NoData class="mb-6 h-40 w-40 text-muted-foreground/30" />
							<p class="text-sm font-medium text-muted-foreground">No reports yet</p>
							<p class="mt-1 text-xs text-muted-foreground/60">Generate your first report to get started</p>
						</div>
					{:else}
						<Table>
							<TableHeader>
								<TableRow class="border-border hover:bg-transparent">
									<TableHead class="font-medium text-muted-foreground">Report</TableHead>
									<TableHead class="font-medium text-muted-foreground">Date Range</TableHead>
									<TableHead class="font-medium text-muted-foreground">Report Date</TableHead>
									<TableHead class="font-medium text-muted-foreground">Status</TableHead>
									<TableHead class="font-medium text-muted-foreground">Created</TableHead>
									<TableHead class="text-right font-medium text-muted-foreground">Actions</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each pagedReports as report (report.id)}
									<TableRow class="border-border">
										<TableCell class="font-medium text-foreground">
											{reportOptions.find((r) => r.value === report.report_name)?.label ?? report.report_name}
										</TableCell>
										<TableCell class="text-sm text-muted-foreground">{report.date_range}</TableCell>
										<TableCell class="text-sm text-muted-foreground">{report.report_date}</TableCell>
										<TableCell>
											<div class="flex items-center gap-2">
												<StatusOrb
													status={report.status === 'pending' ? 'running' : report.status as 'idle' | 'completed' | 'failed'}
													size={8}
												/>
												<span class="text-xs capitalize text-muted-foreground">{report.status}</span>
											</div>
										</TableCell>
										<TableCell class="text-xs text-muted-foreground/70">{formatDate(report.created_at)}</TableCell>
										<TableCell class="text-right">
											{#if report.status === 'completed' && report.output_path}
												<div class="flex items-center justify-end gap-2">
													{#if reportOptions.some((option) => option.value === report.report_name)}
														<Button
															size="sm"
															variant="ghost"
															disabled={redoingReportId === report.id}
															onclick={() => void redoReport(report)}
															title="Generate this report again with the same dates"
														>
															{#if redoingReportId === report.id}
																<Loader2 class="mr-1.5 h-3.5 w-3.5 animate-spin" />
															{:else}
																<RefreshCw class="mr-1.5 h-3.5 w-3.5" />
															{/if}
															Redo
														</Button>
													{/if}
													<Button
														size="sm"
														variant="ghost"
														onclick={() => goto(`/reports/${report.id}/preview`)}
													>
														Preview & Edit
													</Button>
													<Button
														size="sm"
														variant="ghost"
														onclick={() => void downloadReport(report)}
													>
														<Download class="mr-1.5 h-3.5 w-3.5" />
														Save
													</Button>
													<Button
														size="sm"
														variant="ghost"
														class="text-destructive hover:bg-destructive/10 hover:text-destructive"
														onclick={() => promptDelete(report.id)}
														title="Delete report"
													>
														<Trash2 class="h-3.5 w-3.5" />
													</Button>
												</div>
											{:else if report.status === 'pending'}
												<div class="flex items-center justify-end gap-3">
													<GeneratingPulse stage={report.stage ?? 'Processing...'} />
													<Button
														size="sm"
														variant="ghost"
														class="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
														onclick={() => goto('/logs')}
													>
														Logs
													</Button>
													<Button
														size="sm"
														variant="ghost"
														class="h-6 px-2 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
														onclick={() => void stopReport(report.id)}
														title="Stop generation"
													>
														<Square class="mr-1 h-3 w-3 fill-current" />
														Stop
													</Button>
												</div>
											{:else if report.status === 'failed'}
												<div class="flex items-center justify-end gap-2">
													<Button
														size="sm"
														variant="ghost"
														class="text-destructive hover:bg-destructive/10 hover:text-destructive"
														title={report.error ?? 'Report failed'}
														onclick={() => retryReport(report)}
													>
														<RefreshCw class="mr-1.5 h-3.5 w-3.5" />
														Retry
													</Button>
													<Button
														size="sm"
														variant="ghost"
														class="text-destructive hover:bg-destructive/10 hover:text-destructive"
														onclick={() => promptDelete(report.id)}
														title="Delete report"
													>
														<Trash2 class="h-3.5 w-3.5" />
													</Button>
												</div>
											{/if}
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
						{#if totalPages > 1}
							<div class="flex items-center justify-between border-t border-border px-4 py-3">
								<p class="text-xs text-muted-foreground">
									Page {currentPage} of {totalPages} &middot; {reports.length} reports
								</p>
								<div class="flex items-center gap-1">
									<Button
										size="sm"
										variant="ghost"
										class="h-7 w-7 p-0"
										disabled={currentPage === 1}
										onclick={() => (currentPage -= 1)}
									>
										<ChevronLeft class="h-4 w-4" />
									</Button>
									<Button
										size="sm"
										variant="ghost"
										class="h-7 w-7 p-0"
										disabled={currentPage === totalPages}
										onclick={() => (currentPage += 1)}
									>
										<ChevronRight class="h-4 w-4" />
									</Button>
								</div>
							</div>
						{/if}
					{/if}
				</CardContent>
			</Card>
		{/if}
	</div>
</div>

<Dialog bind:open={generateOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>Generate Report</DialogTitle>
			<DialogDescription>
				Fill in the date window and the backend will generate the PPTX locally.
			</DialogDescription>
		</DialogHeader>

		<form onsubmit={handleGenerate} class="space-y-4 pt-2">
			{#if generateError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
					{generateError}
				</div>
			{/if}

			<div class="space-y-2">
				<Label>Report</Label>
				<select
					bind:value={reportName}
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				>
					{#each reportOptions.filter((o) => o.source === 'builtin') as opt (opt.value)}
						<option value={opt.value}>{opt.label}</option>
					{/each}
					{#if reportOptions.some((o) => o.source === 'user')}
						<optgroup label="Custom Templates">
							{#each reportOptions.filter((o) => o.source === 'user') as opt (opt.value)}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</optgroup>
					{/if}
				</select>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-2">
					<Label>Start Date</Label>
					<input
						type="date"
						bind:value={startDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
				<div class="space-y-2">
					<Label>End Date</Label>
					<input
						type="date"
						bind:value={endDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
			</div>

			{#if dateValidationError}
				<div class="date-error-toast" role="alert" aria-live="assertive">
					<span class="date-error-bar"></span>
					<svg class="date-error-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<span class="date-error-text">{dateValidationError}</span>
				</div>
			{:else if dateRange}
				<p class="text-xs text-muted-foreground">Date range: <span class="text-foreground/70">{dateRange}</span></p>
			{/if}

			<div class="space-y-2">
				<Label>Report Date</Label>
				<input
					type="date"
					bind:value={reportDateRaw}
					required
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
				/>
				{#if reportDate}
					<p class="text-xs text-muted-foreground">Formatted: <span class="text-foreground/70">{reportDate}</span></p>
				{/if}
			</div>

			<div class="space-y-3 rounded-md border border-border bg-muted/20 p-3">
				<div class="space-y-1">
					<Label>Slide 1 Name</Label>
					<input
						type="text"
						bind:value={slide1Name}
						placeholder="Leave blank to keep the template name"
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
					/>
				</div>
				<div class="space-y-1">
					<Label>Slide 1 Top Left Logo</Label>
					<input
						type="file"
						accept="image/png,image/jpeg,image/jpg,image/gif,image/bmp,image/tiff"
						onchange={handleLogoChange}
						disabled={preserveSlide1Logo}
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs file:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
					/>
					{#if preserveSlide1Logo}
						<p class="text-xs text-muted-foreground">Dicomm McCann keeps the template logo.</p>
					{:else if slide1LogoFileName}
						<p class="text-xs text-muted-foreground">{slide1LogoFileName}</p>
					{/if}
				</div>
			</div>

			<div class="flex justify-end gap-3 pt-2">
				<Button
					type="button"
					variant="outline"
					onclick={() => (generateOpen = false)}
					disabled={generating}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					disabled={generating || !!dateValidationError}
				>
					{#if generating}
						<span class="mr-2 inline-flex"><SpinnerArc size={16} stroke={2} color="currentColor" /></span>
						Generating...
					{:else}
						Generate
					{/if}
				</Button>
			</div>
		</form>
	</DialogContent>
</Dialog>

<Dialog bind:open={deleteOpen}>
	<DialogContent class="sm:max-w-sm">
		<DialogHeader>
			<DialogTitle>Delete report?</DialogTitle>
			<DialogDescription>This cannot be undone.</DialogDescription>
		</DialogHeader>
		<DialogFooter>
			<Button variant="outline" onclick={() => (deleteOpen = false)}>Cancel</Button>
			<Button variant="destructive" onclick={() => void confirmDelete()}>Delete</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>

<Dialog bind:open={quickOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>Quick Report</DialogTitle>
			<DialogDescription>
				Generate a report for any GA4 property — no template upload required.
			</DialogDescription>
		</DialogHeader>

		<form onsubmit={handleQuickGenerate} class="space-y-4 pt-2">
			{#if quickError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
					{quickError}
				</div>
			{/if}

			<div class="space-y-2">
				<Label>GA4 Property ID</Label>
				<input
					type="text"
					bind:value={quickPropertyId}
					required
					placeholder="e.g. 523115644"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
			</div>

			<div class="space-y-2">
				<Label>Client Name</Label>
				<input
					type="text"
					bind:value={quickClientName}
					required
					placeholder="e.g. Union Hardware"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
			</div>

			<div class="space-y-2">
				<Label>GSC Site URL (optional)</Label>
				<input
					type="text"
					bind:value={quickGscUrl}
					placeholder="https://example.com/"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
				<p class="text-xs text-muted-foreground">Leave blank to skip the Search Performance slide.</p>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-2">
					<Label>Start Date</Label>
					<input
						type="date"
						bind:value={quickStartDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
				<div class="space-y-2">
					<Label>End Date</Label>
					<input
						type="date"
						bind:value={quickEndDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
			</div>

			{#if quickDateValidationError}
				<div class="date-error-toast" role="alert" aria-live="assertive">
					<span class="date-error-bar"></span>
					<svg class="date-error-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<span class="date-error-text">{quickDateValidationError}</span>
				</div>
			{:else if quickDateRange}
				<p class="text-xs text-muted-foreground">Date range: <span class="text-foreground/70">{quickDateRange}</span></p>
			{/if}

			<div class="space-y-2">
				<Label>Report Date</Label>
				<input
					type="date"
					bind:value={quickReportDateRaw}
					required
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
				/>
				{#if quickReportDate}
					<p class="text-xs text-muted-foreground">Formatted: <span class="text-foreground/70">{quickReportDate}</span></p>
				{/if}
			</div>

			<div class="space-y-1">
				<Label>Logo (optional)</Label>
				<input
					type="file"
					accept="image/png,image/jpeg,image/jpg,image/gif,image/bmp,image/tiff"
					onchange={handleQuickLogoChange}
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs file:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if quickLogoFileName}
					<p class="text-xs text-muted-foreground">{quickLogoFileName}</p>
				{/if}
			</div>

			<div class="flex justify-end gap-3 pt-2">
				<Button
					type="button"
					variant="outline"
					onclick={() => (quickOpen = false)}
					disabled={quickGenerating}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					disabled={quickGenerating || !!quickDateValidationError}
				>
					{#if quickGenerating}
						<span class="mr-2 inline-flex"><SpinnerArc size={16} stroke={2} color="currentColor" /></span>
						Generating...
					{:else}
						Generate
					{/if}
				</Button>
			</div>
		</form>
	</DialogContent>
</Dialog>
