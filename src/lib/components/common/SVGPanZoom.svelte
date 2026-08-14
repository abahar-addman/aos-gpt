<script lang="ts">
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { toast } from 'svelte-sonner';

	import DOMPurify from 'dompurify';

	import { getContext } from 'svelte';
	const i18n = getContext<i18nStore>('i18n');

	import { copyToClipboard } from '$lib/utils';

	import PanzoomContainer from './PanzoomContainer.svelte';
	import Tooltip from './Tooltip.svelte';
	import Clipboard from '../icons/Clipboard.svelte';
	import Reset from '../icons/Reset.svelte';
	import Download from '../icons/Download.svelte';
	import Photo from '../icons/Photo.svelte';

	export let className = '';
	export let svg = '';
	export let content = '';

	let panzoomRef: PanzoomContainer;
	const resetPanZoomViewport = () => {
		panzoomRef?.reset();
	};

	const downloadAsSVG = () => {
		const svgBlob = new Blob([svg], { type: 'image/svg+xml' });
		saveAs(svgBlob, `diagram.svg`);
	};

	/**
	 * Prefer the viewBox over the width/height attributes: rendered charts carry a responsive
	 * `max-width:100%;height:auto` style, which leaves an <img>'s natural size unreliable.
	 */
	const intrinsicSize = (markup: string) => {
		const viewBox = markup
			.match(/viewBox="([\d.\s-]+)"/i)?.[1]
			?.trim()
			.split(/\s+/);
		if (viewBox?.length === 4) {
			const width = Number(viewBox[2]);
			const height = Number(viewBox[3]);
			if (width > 0 && height > 0) return { width, height };
		}

		const width = Number(markup.match(/\bwidth="([\d.]+)"/)?.[1]);
		const height = Number(markup.match(/\bheight="([\d.]+)"/)?.[1]);
		if (width > 0 && height > 0) return { width, height };

		return null;
	};

	const downloadAsPNG = async () => {
		const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));

		try {
			const image = new Image();
			await new Promise((resolve, reject) => {
				image.onload = resolve;
				image.onerror = () => reject(new Error('the diagram could not be rasterized'));
				image.src = url;
			});

			const size = intrinsicSize(svg) ?? {
				width: image.naturalWidth || 800,
				height: image.naturalHeight || 600
			};

			// 2x so the export stays sharp when dropped into a doc or a slide.
			const scale = 2;
			const canvas = document.createElement('canvas');
			canvas.width = size.width * scale;
			canvas.height = size.height * scale;

			const ctx = canvas.getContext('2d');
			if (!ctx) throw new Error('no 2d context available');

			// Charts render on a transparent background so the chat surface shows through; PNG
			// viewers differ on how they present that, so bake in the current surface instead.
			ctx.fillStyle = document.documentElement.classList.contains('dark') ? '#171717' : '#ffffff';
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

			const png = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
			if (!png) throw new Error('the PNG could not be encoded');

			saveAs(png, 'diagram.png');
		} catch (error) {
			console.error('Failed to export PNG:', error);
			toast.error($i18n.t('Failed to export as PNG'));
		} finally {
			URL.revokeObjectURL(url);
		}
	};
</script>

<div class="relative group {className}">
	<PanzoomContainer
		bind:this={panzoomRef}
		className="flex h-full max-h-full justify-center items-center"
	>
		{@html DOMPurify.sanitize(svg, {
			USE_PROFILES: { svg: true, svgFilters: true }, // allow <svg>, <defs>, <filter>, etc.
			WHOLE_DOCUMENT: false,
			ADD_TAGS: ['style', 'foreignObject'], // include foreignObject if using HTML labels
			ADD_ATTR: [
				'class',
				'style',
				'id',
				'data-*',
				'viewBox',
				'preserveAspectRatio',
				// markers / arrows
				'markerWidth',
				'markerHeight',
				'markerUnits',
				'refX',
				'refY',
				'orient',
				// hrefs (for gradients, markers, etc.)
				'href',
				'xlink:href',
				// text positioning
				'dominant-baseline',
				'text-anchor',
				// pattern / clip / mask units
				'clipPathUnits',
				'filterUnits',
				'patternUnits',
				'patternContentUnits',
				'maskUnits',
				// a11y niceties
				'role',
				'aria-label',
				'aria-labelledby',
				'aria-hidden',
				'tabindex'
			],
			SANITIZE_DOM: true
		})}
	</PanzoomContainer>

	{#if content}
		<!-- Vega puts legends top-right by default, which is exactly where these sit. Reveal them
		     on hover/focus so they never permanently cover part of the chart. -->
		<div
			class=" absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150"
		>
			<div class="flex gap-1">
				<Tooltip content={$i18n.t('Download as SVG')}>
					<button
						class="p-1.5 rounded-lg border border-gray-100 dark:border-none dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
						on:click={() => {
							downloadAsSVG();
						}}
					>
						<Download className=" size-4" />
					</button>
				</Tooltip>

				<Tooltip content={$i18n.t('Download as PNG')}>
					<button
						class="p-1.5 rounded-lg border border-gray-100 dark:border-none dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
						on:click={() => {
							downloadAsPNG();
						}}
					>
						<Photo className=" size-4" />
					</button>
				</Tooltip>

				<Tooltip content={$i18n.t('Reset view')}>
					<button
						class="p-1.5 rounded-lg border border-gray-100 dark:border-none dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
						on:click={() => {
							resetPanZoomViewport();
						}}
					>
						<Reset className=" size-4" />
					</button>
				</Tooltip>

				<Tooltip content={$i18n.t('Copy to clipboard')}>
					<button
						class="p-1.5 rounded-lg border border-gray-100 dark:border-none dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
						on:click={() => {
							copyToClipboard(content);
							toast.success($i18n.t('Copied to clipboard'));
						}}
					>
						<Clipboard className=" size-4" strokeWidth="1.5" />
					</button>
				</Tooltip>
			</div>
		</div>
	{/if}
</div>
