import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';

export default defineConfig({
	server: {
		proxy: {
			'/api': {
				target: 'http://localhost:8080',
			},
			'/ollama': {
				target: 'http://localhost:8080',
			},
			'/openai': {
				target: 'http://localhost:8080',
			},
			'/ws': {
				target: 'http://localhost:8080',
				ws: true,
			},
			'/static': {
				target: 'http://localhost:8080',
			},
			'/cache': {
				target: 'http://localhost:8080',
			},
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
