// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
	}

	// Type of the i18next store provided via setContext('i18n', ...) in the root
	// layout. Declared globally so `getContext<i18nStore>('i18n')` needs no imports.
	type i18nStore = import('svelte/store').Writable<import('i18next').i18n>;
}

export {};
