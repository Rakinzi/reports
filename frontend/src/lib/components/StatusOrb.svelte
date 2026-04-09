<script lang="ts">
	type Status = 'idle' | 'pending' | 'running' | 'completed' | 'failed';
	let { status = 'idle', size = 10 }: { status?: Status; size?: number } = $props();
</script>

<!--
  StatusOrb — a living indicator dot.
  idle:      dim zinc pulse (very slow)
  pending:   amber, gentle breathe
  running:   blue, fast double-ring ripple
  completed: emerald, single pop then steady
  failed:    red, sharp stutter flash
-->
<span
	class="status-orb"
	data-status={status}
	style="--sz: {size}px"
	aria-label={status}
></span>

<style>
	.status-orb {
		display: inline-block;
		position: relative;
		width: var(--sz);
		height: var(--sz);
		border-radius: 50%;
		flex-shrink: 0;
	}

	/* Core dot */
	.status-orb::before {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: 50%;
		background: var(--orb-color, #52525b);
		transition: background 0.3s ease;
	}

	/* Ripple ring */
	.status-orb::after {
		content: '';
		position: absolute;
		inset: -3px;
		border-radius: 50%;
		border: 1.5px solid var(--orb-color, transparent);
		opacity: 0;
	}

	/* ── idle ── */
	[data-status='idle'] { --orb-color: #3f3f46; }
	[data-status='idle']::before {
		animation: breathe-dim 4s ease-in-out infinite;
	}

	/* ── pending ── */
	[data-status='pending'] { --orb-color: #f59e0b; }
	[data-status='pending']::before {
		animation: breathe 1.8s ease-in-out infinite;
	}

	/* ── running ── */
	[data-status='running'] { --orb-color: #60a5fa; }
	[data-status='running']::before {
		animation: breathe-fast 0.9s ease-in-out infinite alternate;
	}
	[data-status='running']::after {
		animation: ripple 1.1s ease-out infinite;
	}

	/* ── completed ── */
	[data-status='completed'] { --orb-color: #34d399; }
	[data-status='completed']::before {
		animation: pop-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) both;
	}

	/* ── failed ── */
	[data-status='failed'] { --orb-color: #f87171; }
	[data-status='failed']::before {
		animation: stutter 0.5s ease both, glow-red 2s ease-in-out 0.5s infinite;
	}

	/* ── keyframes ── */
	@keyframes breathe-dim {
		0%, 100% { opacity: 0.3; transform: scale(0.9); }
		50%       { opacity: 0.6; transform: scale(1); }
	}
	@keyframes breathe {
		0%, 100% { opacity: 0.6; transform: scale(0.85); }
		50%       { opacity: 1;   transform: scale(1); }
	}
	@keyframes breathe-fast {
		from { opacity: 0.7; transform: scale(0.9); }
		to   { opacity: 1;   transform: scale(1.05); }
	}
	@keyframes ripple {
		0%   { inset: 0px;  opacity: 0.7; }
		100% { inset: -8px; opacity: 0; }
	}
	@keyframes pop-in {
		0%   { transform: scale(0); opacity: 0; }
		70%  { transform: scale(1.3); }
		100% { transform: scale(1); opacity: 1; }
	}
	@keyframes stutter {
		0%, 100% { transform: scale(1);    opacity: 1; }
		20%       { transform: scale(1.3);  opacity: 0.8; }
		40%       { transform: scale(0.85); opacity: 1; }
		60%       { transform: scale(1.2);  opacity: 0.7; }
		80%       { transform: scale(0.95); opacity: 1; }
	}
	@keyframes glow-red {
		0%, 100% { opacity: 0.7; }
		50%       { opacity: 1; box-shadow: 0 0 6px 1px #f87171aa; }
	}
</style>
