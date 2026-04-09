<script lang="ts">
	let {
		size = 20,
		stroke = 2.5,
		color = 'currentColor',
		speed = 'normal'
	}: {
		size?: number;
		stroke?: number;
		color?: string;
		speed?: 'slow' | 'normal' | 'fast';
	} = $props();

	const r = $derived((size - stroke) / 2);
	const circ = $derived(2 * Math.PI * r);
	const dash = $derived(circ * 0.72); // arc covers ~72% of circle
	const dur = $derived(speed === 'slow' ? '1.6s' : speed === 'fast' ? '0.65s' : '1s');
</script>

<!--
  SpinnerArc — conic SVG arc spinner.
  A single stroke arc that rotates. Clean, minimal, no flicker.
  Unlike border-spinner it has a precise tapered tail via stroke-linecap.
-->
<svg
	width={size}
	height={size}
	viewBox="0 0 {size} {size}"
	fill="none"
	aria-hidden="true"
	class="spinner-arc"
	style="--dur: {dur}"
>
	<!-- track -->
	<circle
		cx={size / 2}
		cy={size / 2}
		r={r}
		stroke="currentColor"
		stroke-width={stroke}
		opacity="0.15"
	/>
	<!-- arc -->
	<circle
		cx={size / 2}
		cy={size / 2}
		r={r}
		stroke={color}
		stroke-width={stroke}
		stroke-linecap="round"
		stroke-dasharray="{dash} {circ - dash}"
		stroke-dashoffset={circ * 0.25}
		class="arc"
	/>
</svg>

<style>
	.spinner-arc {
		animation: rotate var(--dur) linear infinite;
		display: inline-block;
		flex-shrink: 0;
	}
	.arc {
		transform-origin: center;
	}
	@keyframes rotate {
		to { transform: rotate(360deg); }
	}
</style>
