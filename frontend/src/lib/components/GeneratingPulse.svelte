<script lang="ts">
	let { stage = 'Processing...' }: { stage?: string } = $props();
</script>

<!--
  GeneratingPulse — shown while a report is being generated.
  Three staggered bars that compress/expand like an audio waveform,
  plus the current stage label beneath.
  Pure CSS — zero JS, zero deps.
-->
<div class="gen-pulse" aria-label="Generating report: {stage}">
	<div class="bars">
		<span class="bar" style="--d: 0s"></span>
		<span class="bar" style="--d: 0.12s"></span>
		<span class="bar" style="--d: 0.24s"></span>
		<span class="bar" style="--d: 0.08s"></span>
		<span class="bar" style="--d: 0.18s"></span>
	</div>
	<span class="stage">{stage}</span>
</div>

<style>
	.gen-pulse {
		display: inline-flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
	}

	.bars {
		display: flex;
		align-items: center;
		gap: 3px;
		height: 18px;
	}

	.bar {
		display: block;
		width: 3px;
		border-radius: 2px;
		background: #a1a1aa; /* zinc-400 */
		animation: wave 1s ease-in-out infinite;
		animation-delay: var(--d);
	}

	/* each bar starts at a different height */
	.bar:nth-child(1) { height: 6px; }
	.bar:nth-child(2) { height: 14px; }
	.bar:nth-child(3) { height: 18px; }
	.bar:nth-child(4) { height: 10px; }
	.bar:nth-child(5) { height: 6px;  }

	@keyframes wave {
		0%, 100% { transform: scaleY(0.4); opacity: 0.4; }
		50%       { transform: scaleY(1);   opacity: 1;   }
	}

	.stage {
		font-size: 11px;
		color: #71717a; /* zinc-500 */
		letter-spacing: 0.04em;
		font-family: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace;
		white-space: nowrap;
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
