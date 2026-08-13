import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';

// Dev backend target for `bun run dev` (see the dev:backend script in package.json).
// 1776 is this project's port everywhere else — docker/Dockerfile EXPOSE + healthcheck,
// docker-compose.yaml, docker-compose.dev.yaml — so dev now matches the image instead of
// sitting on 8080, which is heavily contested locally (other app servers, SSH
// port-forwards). A forward bound to 127.0.0.1:8080 silently shadows a backend bound to
// 0.0.0.0:8080 and every proxied call lands on the wrong server.
// Addressed as 127.0.0.1 rather than localhost so the target can't resolve to ::1 first.
// Keep this in sync with the dev:backend script in package.json.
const BACKEND = 'http://127.0.0.1:1776';

export default defineConfig({
	server: {
		proxy: {
			'/api': {
				target: BACKEND
			},
			'/ollama': {
				target: BACKEND
			},
			'/openai': {
				target: BACKEND
			},
			'/ws': {
				target: BACKEND,
				ws: true
			},
			'/static': {
				target: BACKEND
			},
			'/cache': {
				target: BACKEND
			},
			'/oauth': {
				target: BACKEND
			}
		}
	},
	plugins: [
		sveltekit(),
		viteStaticCopy({
			targets: [
				{
					src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

					dest: 'wasm'
				}
			]
		})
	],
	define: {
		APP_VERSION: JSON.stringify(process.env.npm_package_version),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
	},
	resolve: {
		dedupe: [
			'prosemirror-state',
			'prosemirror-view',
			'prosemirror-model',
			'prosemirror-transform',
			'prosemirror-keymap',
			'prosemirror-inputrules',
			'prosemirror-gapcursor',
			'prosemirror-dropcursor',
			'prosemirror-history',
			'prosemirror-commands',
			'prosemirror-schema-list',
			'prosemirror-tables',
			'prosemirror-collab'
		]
	},
	build: {
		sourcemap: true
	},
	worker: {
		format: 'es'
	},
	esbuild: {
		pure: process.env.ENV === 'dev' ? [] : ['console.log', 'console.debug', 'console.error']
	}
});
