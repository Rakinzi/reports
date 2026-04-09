# Reports — Frontend

SvelteKit + Tauri desktop frontend for the Reports app.

## Dev

```sh
bun install
bun run dev          # web dev server
bun run tauri:dev    # desktop dev (hot-reload)
```

## Build

See the root [`README.md`](../README.md) for full installer build instructions for macOS and Windows.

```sh
# macOS
bun run tauri:build:mac

# Windows
bun run tauri:build:win
```

## Check / Lint

```sh
bun run check    # svelte-check (TypeScript + Svelte)
bun run lint     # prettier + eslint
bun run format   # auto-format
```
