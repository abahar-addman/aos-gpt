<script lang="ts">
	import Message from './Message.svelte';

	export let messages = [];
</script>

<div class="space-y-3 pb-4">
	{#each messages as message, idx (idx)}
		<Message {message} {idx} />
	{/each}
</div>
