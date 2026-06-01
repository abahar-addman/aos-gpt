// Base-aware navigation wrapper.
//
// Open WebUI hardcodes root-absolute internal paths (e.g. `goto('/auth')`,
// `goto('/workspace/models')`). When the app is hosted under a URL prefix
// (svelte.config.js `paths.base`, e.g. /edison-ai), SvelteKit treats those
// root-absolute paths as NOT belonging to the app and does a full-page
// navigation to the origin root — which the reverse proxy doesn't route → 404.
//
// This module re-exports the entire `$app/navigation` API and overrides `goto`
// to prepend the base path to root-absolute internal URLs. Import `goto` from
// here instead of `$app/navigation`. No-op when base is '' (root hosting) or
// when the URL already includes the base / is external.

import { goto as _goto } from '$app/navigation';
import { base } from '$app/paths';

export * from '$app/navigation';

export function goto(url: string | URL, opts?: Parameters<typeof _goto>[1]): Promise<void> {
	if (
		base &&
		typeof url === 'string' &&
		url.startsWith('/') &&
		url !== base &&
		!url.startsWith(`${base}/`)
	) {
		url = `${base}${url}`;
	}
	return _goto(url, opts);
}
