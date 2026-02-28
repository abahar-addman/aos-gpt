<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	export let size = 'md';

	const sayings = [
		'Warming up the neurons...',
		'Thinking really hard...',
		'Consulting the knowledge base...',
		'Brewing a response...',
		'Crunching the numbers...',
		'Connecting the dots...',
		'Gathering my thoughts...',
		'Almost there...',
		'Working on it...',
		'Processing your request...',
		'Putting it all together...',
		'Reading between the lines...',
		'On it...',
		'Spinning up...',
		'Assembling the answer...'
	];

	let currentIndex = Math.floor(Math.random() * sayings.length);
	let currentSaying = sayings[currentIndex];
	let interval: ReturnType<typeof setInterval>;

	onMount(() => {
		interval = setInterval(() => {
			currentIndex = (currentIndex + 1) % sayings.length;
			currentSaying = sayings[currentIndex];
		}, 3000);
	});

	onDestroy(() => {
		if (interval) clearInterval(interval);
	});
</script>

<div
	class="flex items-center gap-2 {size === 'md'
		? 'py-0.5'
		: size === 'xs'
			? 'py-0'
			: 'py-0.5'}"
>
	<div
		class="shimmer {size === 'md'
			? 'text-base'
			: size === 'xs'
				? 'text-xs'
				: 'text-sm'} line-clamp-1"
	>
		{currentSaying}
	</div>
</div>
