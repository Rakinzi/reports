export type FieldType = {
	value: string;
	label: string;
	group: string;
	shapeType: 'text' | 'image';
	description: string;
};

export const FIELD_TYPES: FieldType[] = [
	// --- Dates ---
	{
		value: 'perf_month',
		label: 'Performance Month',
		group: 'Dates',
		shapeType: 'text',
		description: 'Month + year of the report period (e.g. "March 2026")'
	},
	{
		value: 'date_range',
		label: 'Date Range',
		group: 'Dates',
		shapeType: 'text',
		description: 'Full date range label (e.g. "1 March 2026 - 31 March 2026")'
	},
	{
		value: 'report_date',
		label: 'Report Date',
		group: 'Dates',
		shapeType: 'text',
		description: 'Report generation date (e.g. "03 April 2026")'
	},

	// --- Core Metrics ---
	{
		value: 'active_users',
		label: 'Active Users',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Total active users from GA4 home (e.g. "12,456")'
	},
	{
		value: 'new_users',
		label: 'New Users',
		group: 'Metrics',
		shapeType: 'text',
		description: 'New users count from GA4 home'
	},
	{
		value: 'new_users_pct',
		label: 'New Users %',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Percentage of new visitors'
	},
	{
		value: 'engagement_time',
		label: 'Avg Engagement Time',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Average engagement time per active user'
	},
	{
		value: 'ctr',
		label: 'CTR',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Click-through rate from GSC or snapshot'
	},
	{
		value: 'bounce_rate',
		label: 'Bounce Rate',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Session bounce rate'
	},
	{
		value: 'sessions',
		label: 'Sessions',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Total sessions'
	},
	{
		value: 'page_views',
		label: 'Page Views',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Total page views'
	},
	{
		value: 'conversion_rate',
		label: 'Conversion Rate',
		group: 'Metrics',
		shapeType: 'text',
		description: 'Goal conversion rate'
	},

	// --- Channel Metrics ---
	{
		value: 'organic_search_users',
		label: 'Organic Search Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Organic Search channel'
	},
	{
		value: 'direct_users',
		label: 'Direct Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Direct channel'
	},
	{
		value: 'referral_users',
		label: 'Referral Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Referral channel'
	},
	{
		value: 'social_users',
		label: 'Social Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Social channel'
	},
	{
		value: 'email_users',
		label: 'Email Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Email channel'
	},
	{
		value: 'paid_search_users',
		label: 'Paid Search Users',
		group: 'Channel Metrics',
		shapeType: 'text',
		description: 'New users from Paid Search channel'
	},

	// --- GSC Metrics ---
	{
		value: 'gsc_impressions',
		label: 'GSC Impressions',
		group: 'Search Console',
		shapeType: 'text',
		description: 'Total impressions from Google Search Console'
	},
	{
		value: 'gsc_clicks',
		label: 'GSC Clicks',
		group: 'Search Console',
		shapeType: 'text',
		description: 'Total clicks from Google Search Console'
	},
	{
		value: 'gsc_avg_position',
		label: 'GSC Avg Position',
		group: 'Search Console',
		shapeType: 'text',
		description: 'Average ranking position from Google Search Console'
	},

	// --- Narrative / AI-generated ---
	{
		value: 'narrative_overview',
		label: 'Narrative: Overview',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph summarising overall performance'
	},
	{
		value: 'narrative_traffic',
		label: 'Narrative: Traffic',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph about traffic trends'
	},
	{
		value: 'narrative_channels',
		label: 'Narrative: Channels',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph about acquisition channels'
	},
	{
		value: 'narrative_countries',
		label: 'Narrative: Countries',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph about geographic traffic'
	},
	{
		value: 'narrative_pages',
		label: 'Narrative: Pages',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph about top pages'
	},
	{
		value: 'narrative_search',
		label: 'Narrative: Search',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated paragraph about search performance'
	},
	{
		value: 'subtitle_overview',
		label: 'Subtitle: Overview',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Short Gemini-generated subtitle/caption for overview section'
	},
	{
		value: 'subtitle_traffic',
		label: 'Subtitle: Traffic',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Short Gemini-generated subtitle for traffic section'
	},
	{
		value: 'recommendations',
		label: 'Recommendations',
		group: 'AI Narrative',
		shapeType: 'text',
		description: 'Gemini-generated numbered recommendations list'
	},

	// --- Charts ---
	{
		value: 'chart_country_bar',
		label: 'Chart: Country Bar',
		group: 'Charts',
		shapeType: 'image',
		description: 'Bar chart of top 5 countries by traffic'
	},
	{
		value: 'chart_traffic_pie',
		label: 'Chart: Traffic Source Pie',
		group: 'Charts',
		shapeType: 'image',
		description: 'Pie chart of traffic by acquisition channel'
	},
	{
		value: 'chart_line',
		label: 'Chart: Weekly Line',
		group: 'Charts',
		shapeType: 'image',
		description: 'Weekly users trend line chart'
	},
	{
		value: 'chart_page_views_bar',
		label: 'Chart: Page Views Bar',
		group: 'Charts',
		shapeType: 'image',
		description: 'Bar chart of top pages by page views'
	},

	// --- Screenshots ---
	{
		value: 'screenshot_snapshot_card',
		label: 'Screenshot: Snapshot Card',
		group: 'Screenshots',
		shapeType: 'image',
		description: 'Screenshot of the GA4 Reports Snapshot overview card'
	},
	{
		value: 'screenshot_countries_table',
		label: 'Screenshot: Countries Table',
		group: 'Screenshots',
		shapeType: 'image',
		description: 'Screenshot of the GA4 countries breakdown table'
	},
	{
		value: 'screenshot_pages_table',
		label: 'Screenshot: Pages Table',
		group: 'Screenshots',
		shapeType: 'image',
		description: 'Screenshot of the GA4 top pages table'
	},
	{
		value: 'screenshot_search_console',
		label: 'Screenshot: Search Console',
		group: 'Screenshots',
		shapeType: 'image',
		description: 'Screenshot of the Google Search Console performance view'
	},

	// --- Decorative / Static ---
	{
		value: 'static_text',
		label: 'Static Text (no change)',
		group: 'Other',
		shapeType: 'text',
		description: 'Leave this text shape unchanged — it is a label, heading, or decoration'
	},
	{
		value: 'static_image',
		label: 'Static Image (no change)',
		group: 'Other',
		shapeType: 'image',
		description: 'Leave this image shape unchanged — it is a logo, icon, or decoration'
	},
];

export const FIELD_TYPE_MAP = new Map(FIELD_TYPES.map((f) => [f.value, f]));

export const FIELD_TYPE_GROUPS: { group: string; types: FieldType[] }[] = Array.from(
	FIELD_TYPES.reduce((acc, ft) => {
		if (!acc.has(ft.group)) acc.set(ft.group, []);
		acc.get(ft.group)!.push(ft);
		return acc;
	}, new Map<string, FieldType[]>())
).map(([group, types]) => ({ group, types }));
