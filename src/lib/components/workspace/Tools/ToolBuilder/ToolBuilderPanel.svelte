<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Pane, PaneResizer } from 'paneforge';

	import Drawer from '$lib/components/common/Drawer.svelte';

	export let show = false;
	export let pane = null;

	// Sized against the workspace scroll container (see workspace/+layout.svelte).
	export let containerId = 'workspace-container';

	let mediaQuery;
	let largeScreen = false;

	let minSize = 0;

	const handleMediaQuery = async (e) => {
		if (e.matches) {
			largeScreen = true;
		} else {
			largeScreen = false;
			pane = null;
		}
	};

	onMount(() => {
		mediaQuery = window.matchMedia('(min-width: 1000px)');
		mediaQuery.addEventListener('change', handleMediaQuery);
		handleMediaQuery(mediaQuery);

		const container = document.getElementById(containerId);
		if (!container) return;

		minSize = Math.floor((400 / container.clientWidth) * 100);

		const resizeObserver = new ResizeObserver((entries) => {
			for (let entry of entries) {
				const width = entry.contentRect.width;
				const percentage = (400 / width) * 100;
				minSize = Math.floor(percentage);

				if (show) {
					if (pane && pane.isExpanded() && pane.getSize() < minSize) {
						pane.resize(minSize);
					}
				}
			}
		});

		resizeObserver.observe(container);
	});

	onDestroy(() => {
		mediaQuery?.removeEventListener('change', handleMediaQuery);
	});
</script>

{#if !largeScreen}
	{#if show}
		<Drawer
			{show}
			onClose={() => {
				show = false;
			}}
		>
			<div class=" px-3.5 py-2.5 h-screen max-h-dvh flex flex-col">
				<slot />
			</div>
		</Drawer>
	{/if}
{:else if show}
	<PaneResizer
		class="group relative z-20 flex items-center justify-center border-l border-gray-100/50 transition hover:border-gray-200 dark:border-white/[0.04] dark:hover:border-gray-800"
		id="tool-builder-resizer"
	>
		<div class=" absolute -left-1.5 -right-1.5 -top-0 -bottom-0 z-20 cursor-col-resize bg-transparent"></div>
	</PaneResizer>

	<Pane
		bind:pane
		defaultSize={Math.max(25, minSize)}
		{minSize}
		onCollapse={() => {
			show = false;
		}}
		collapsible={true}
		class=" z-10 "
	>
		{#if show}
			<div class="flex max-h-full min-h-full">
				<div
					class="pointer-events-auto z-40 flex w-full flex-col overflow-y-auto scrollbar-hidden bg-white px-2 pt-2 dark:bg-gray-900"
				>
					<slot />
				</div>
			</div>
		{/if}
	</Pane>
{/if}
