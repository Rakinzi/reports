<script lang="ts">
	let { message = 'Starting local backend...' }: { message?: string } = $props();
</script>

<!--
  BootScreen — full-area loader shown while the desktop backend starts.
  Aesthetic: dark terminal, scan-line texture, typewriter cursor.
  Pure CSS — no JS animation deps.
-->
<div class="boot" aria-live="polite" aria-label={message}>
	<div class="frame">
		<!-- Rotating arcs (outer + inner) -->
		<div class="ring ring-outer"></div>
		<div class="ring ring-inner"></div>

		<!-- Centre dot -->
		<div class="core"></div>

		<!-- Scan lines overlay -->
		<div class="scanlines" aria-hidden="true"></div>
	</div>

	<p class="msg">
		{message}<span class="cursor" aria-hidden="true">_</span>
	</p>
</div>

<style>
	.boot {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 28px;
		padding: 24px;
	}

	/* ── ring container ── */
	.frame {
		position: relative;
		width: 64px;
		height: 64px;
	}

	.ring {
		position: absolute;
		border-radius: 50%;
		border: 1.5px solid transparent;
	}

	.ring-outer {
		inset: 0;
		border-top-color: #a1a1aa;   /* zinc-400 */
		border-right-color: #52525b; /* zinc-600 */
		animation: spin-cw 1.4s linear infinite;
	}

	.ring-inner {
		inset: 10px;
		border-bottom-color: #71717a; /* zinc-500 */
		border-left-color: #3f3f46;   /* zinc-700 */
		animation: spin-ccw 0.9s linear infinite;
	}

	.core {
		position: absolute;
		inset: 27px;
		border-radius: 50%;
		background: #a1a1aa;
		animation: core-pulse 1.4s ease-in-out infinite;
	}

	/* fake scan-line texture */
	.scanlines {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		background: repeating-linear-gradient(
			0deg,
			transparent,
			transparent 2px,
			rgba(0, 0, 0, 0.08) 2px,
			rgba(0, 0, 0, 0.08) 4px
		);
		pointer-events: none;
	}

	/* ── label ── */
	.msg {
		font-family: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace;
		font-size: 11px;
		letter-spacing: 0.08em;
		color: #71717a;
		display: flex;
		align-items: baseline;
		gap: 1px;
	}

	.cursor {
		animation: blink 1s step-end infinite;
		color: #a1a1aa;
	}

	/* ── keyframes ── */
	@keyframes spin-cw  { to { transform: rotate(360deg); } }
	@keyframes spin-ccw { to { transform: rotate(-360deg); } }

	@keyframes core-pulse {
		0%, 100% { transform: scale(0.7); opacity: 0.5; }
		50%       { transform: scale(1.2); opacity: 1; }
	}

	@keyframes blink {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0; }
	}
</style>
