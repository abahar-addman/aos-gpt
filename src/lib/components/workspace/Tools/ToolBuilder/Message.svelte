<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<i18nStore>('i18n');

	import Skeleton from '$lib/components/chat/Messages/Skeleton.svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	export let message;
	export let idx;
</script>

<div class="flex flex-col gap-1">
	<!-- $i18n.t('user') -->
	<!-- $i18n.t('assistant') -->
	<div class="py-0.5 text-xs font-semibold uppercase text-gray-500">
		{$i18n.t(message.role)}
	</div>

	<div class="flex-1">
		{#if !(message?.done ?? true) && (message?.content ?? '') === ''}
			<Skeleton size="sm" />
		{:else}
			<div class="markdown-prose-sm text-sm">
				<Markdown
					id={`tool-builder-message-${idx}`}
					content={message.content}
					done={message?.done ?? true}
					editCodeBlock={false}
				/>
			</div>
		{/if}
	</div>
</div>
