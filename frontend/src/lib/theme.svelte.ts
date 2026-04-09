/**
 * theme.svelte.ts — persisted light/dark mode store.
 * Uses localStorage so the preference survives app restarts.
 */

type Theme = 'dark' | 'light';

function createTheme() {
	let current = $state<Theme>('dark');

	function apply(t: Theme) {
		current = t;
		const html = document.documentElement;
		if (t === 'dark') {
			html.classList.add('dark');
			html.classList.remove('light');
		} else {
			html.classList.add('light');
			html.classList.remove('dark');
		}
		try { localStorage.setItem('theme', t); } catch { /* SSR / private mode */ }
	}

	function init() {
		const saved = typeof localStorage !== 'undefined'
			? (localStorage.getItem('theme') as Theme | null)
			: null;
		apply(saved ?? 'dark');
	}

	function toggle() {
		apply(current === 'dark' ? 'light' : 'dark');
	}

	return {
		get current() { return current; },
		init,
		toggle,
		set: apply,
	};
}

export const theme = createTheme();
