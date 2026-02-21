<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';

	// Props
	export let src: string | null = null; // URL or raw HTML (auto-detected)
	export let title = 'Embedded Content';
	export let initialHeight: number | null = null; // initial height in px, null = auto

	export let iframeClassName = 'w-full rounded-2xl';

	export let args = null;

	export let allowScripts = true;
	export let allowForms = false;

	export let allowSameOrigin = false; // set to true only when you trust the content
	export let allowPopups = false;
	export let allowDownloads = true;

	export let referrerPolicy: HTMLIFrameElement['referrerPolicy'] =
		'strict-origin-when-cross-origin';
	export let allowFullscreen = true;

	export let payload = null; // payload to send into the iframe on request

	let iframe: HTMLIFrameElement | null = null;
	let container: HTMLDivElement | null = null;
	let iframeSrc: string | null = null;
	let iframeDoc: string | null = null;
	let containerHeight = initialHeight ?? 650;
	let containerWidth: number | null = null; // null = 100%
	let isDragging = false;
	let dragStartX = 0;
	let dragStartY = 0;
	let dragStartHeight = 0;
	let dragStartWidth = 0;

	// Derived: build sandbox attribute from flags
	$: sandbox =
		[
			allowScripts && 'allow-scripts',
			allowForms && 'allow-forms',
			allowSameOrigin && 'allow-same-origin',
			allowPopups && 'allow-popups',
			allowDownloads && 'allow-downloads'
		]
			.filter(Boolean)
			.join(' ') || undefined;

	// Detect URL vs raw HTML and prep src/srcdoc
	$: isUrl = typeof src === 'string' && /^(https?:)?\/\//i.test(src);
	$: if (src) {
		setIframeSrc();
	}

	$: widthStyle = containerWidth ? `width:${containerWidth}px;` : 'width:100%;';

	const setIframeSrc = async () => {
		// Reset height when src changes to avoid stale sizing
		containerHeight = initialHeight ?? 650;
		// Clean up previous observer
		if (observerInstance) {
			observerInstance.disconnect();
			observerInstance = null;
		}
		await tick();
		if (isUrl) {
			iframeSrc = src as string;
			iframeDoc = null;
		} else {
			iframeDoc = await processHtmlForDeps(src as string);
			iframeSrc = null;
		}
	};

	// Alpine directives detection
	const alpineDirectives = [
		'x-data',
		'x-init',
		'x-show',
		'x-bind',
		'x-on',
		'x-text',
		'x-html',
		'x-model',
		'x-modelable',
		'x-ref',
		'x-for',
		'x-if',
		'x-effect',
		'x-transition',
		'x-cloak',
		'x-ignore',
		'x-teleport',
		'x-id'
	];

	async function processHtmlForDeps(html: string): Promise<string> {
		if (!allowSameOrigin) return html;

		const scriptTags: string[] = [];

		// --- Alpine.js detection & injection ---
		const hasAlpineDirectives = alpineDirectives.some((dir) => html.includes(dir));
		if (hasAlpineDirectives) {
			try {
				const { default: alpineCode } = await import('alpinejs/dist/cdn.min.js?raw');
				const alpineBlob = new Blob([alpineCode], { type: 'text/javascript' });
				const alpineUrl = URL.createObjectURL(alpineBlob);
				const alpineTag = `<script src="${alpineUrl}" defer><\/script>`;
				scriptTags.push(alpineTag);
			} catch (error) {
				console.error('Error processing Alpine for iframe:', error);
			}
		}

		// --- Chart.js detection & injection ---
		const chartJsDirectives = ['new Chart(', 'Chart.'];
		const hasChartJsDirectives = chartJsDirectives.some((dir) => html.includes(dir));
		if (hasChartJsDirectives) {
			try {
				// import chartUrl from 'chart.js/auto?url';
				const { default: Chart } = await import('chart.js/auto');
				(window as any).Chart = Chart;

				const chartTag = `<script>
window.Chart = parent.Chart; // Chart previously assigned on parent
<\/script>`;
				scriptTags.push(chartTag);
			} catch (error) {
				console.error('Error processing Chart.js for iframe:', error);
			}
		}

		// If nothing to inject, return original HTML
		if (scriptTags.length === 0) return html;

		const tags = scriptTags.join('\n');

		// Prefer injecting into <head>, then before </body>, otherwise prepend
		if (html.includes('</head>')) {
			return html.replace('</head>', `${tags}\n</head>`);
		}
		if (html.includes('</body>')) {
			return html.replace('</body>', `${tags}\n</body>`);
		}
		return `${tags}\n${html}`;
	}

	let observerInstance: MutationObserver | null = null;
	let resizeTimeout: ReturnType<typeof setTimeout> | null = null;

	// Try to measure same-origin content safely
	function resizeSameOrigin() {
		if (!iframe) return;
		try {
			const doc = iframe.contentDocument || iframe.contentWindow?.document;
			if (!doc) return;
			const h = Math.max(doc.documentElement?.scrollHeight ?? 0, doc.body?.scrollHeight ?? 0);
			if (h > 0) containerHeight = h + 20;
		} catch {
			// Cross-origin → rely on postMessage from inside the iframe
		}
	}

	// Observe DOM mutations inside the iframe to catch async content (e.g. Plotly CDN loads)
	function observeIframeContent() {
		if (!iframe) return;
		try {
			const doc = iframe.contentDocument || iframe.contentWindow?.document;
			if (!doc?.body) return;

			observerInstance = new MutationObserver(() => {
				// Debounce resize to avoid excessive recalculations
				if (resizeTimeout) clearTimeout(resizeTimeout);
				resizeTimeout = setTimeout(resizeSameOrigin, 100);
			});
			observerInstance.observe(doc.body, { childList: true, subtree: true, attributes: true });

			// Also retry resize a few times for scripts that render after load
			for (const delay of [200, 500, 1000, 2000]) {
				setTimeout(resizeSameOrigin, delay);
			}
		} catch {
			// Cross-origin — can't observe
		}
	}

	// Custom corner drag-to-resize (both axes)
	function onDragStart(e: MouseEvent) {
		e.preventDefault();
		isDragging = true;
		dragStartX = e.clientX;
		dragStartY = e.clientY;
		dragStartHeight = containerHeight;
		dragStartWidth = containerWidth ?? (container?.offsetWidth ?? 800);
		if (!containerWidth && container) {
			containerWidth = container.offsetWidth;
		}
		document.body.style.userSelect = 'none';
		document.body.style.cursor = 'nwse-resize';
		document.addEventListener('mousemove', onDragMove);
		document.addEventListener('mouseup', onDragEnd);
	}

	function onDragMove(e: MouseEvent) {
		if (!isDragging) return;
		containerHeight = Math.max(200, dragStartHeight + (e.clientY - dragStartY));
		containerWidth = Math.max(300, dragStartWidth + (e.clientX - dragStartX));
	}

	function onDragEnd() {
		isDragging = false;
		document.body.style.userSelect = '';
		document.body.style.cursor = '';
		document.removeEventListener('mousemove', onDragMove);
		document.removeEventListener('mouseup', onDragEnd);
	}

	function onMessage(e: MessageEvent) {
		if (!iframe || e.source !== iframe.contentWindow) return;

		const data = e.data || {};
		if (data?.type === 'iframe:height' && typeof data.height === 'number') {
			containerHeight = Math.max(200, data.height);
		}

		// Pong message for testing connectivity
		if (data?.type === 'pong') {
			console.log('Received pong from iframe:', data);

			// Optional: reply back
			iframe.contentWindow?.postMessage({ type: 'pong:ack' }, '*');
		}

		// Send payload data if requested
		if (data?.type === 'payload') {
			iframe.contentWindow?.postMessage(
				{ type: 'payload', requestId: data?.requestId ?? null, payload: payload },
				'*'
			);
		}
	}

	// When the iframe loads, try same-origin resize (cross-origin will noop)
	const onLoad = async () => {
		requestAnimationFrame(resizeSameOrigin);
		observeIframeContent();

		// if arguments are provided, inject them into the iframe window
		if (args && iframe?.contentWindow) {
			(iframe.contentWindow as any).args = args;
		}
	};

	// Ensure event listener bound only while component lives
	onMount(() => {
		window.addEventListener('message', onMessage);
	});

	onDestroy(() => {
		window.removeEventListener('message', onMessage);
		document.removeEventListener('mousemove', onDragMove);
		document.removeEventListener('mouseup', onDragEnd);
		if (observerInstance) observerInstance.disconnect();
		if (resizeTimeout) clearTimeout(resizeTimeout);
	});
</script>

<div class="relative inline-block" style="min-height:200px; min-width:300px; {widthStyle}" bind:this={container}>
	{#if iframeDoc}
		<iframe
			bind:this={iframe}
			srcdoc={iframeDoc}
			{title}
			class={iframeClassName}
			style={`height:${containerHeight}px; width:100%; overflow:hidden; border:none;`}
			scrolling="no"
			frameborder="0"
			{sandbox}
			{allowFullscreen}
			on:load={onLoad}
		/>
	{:else if iframeSrc}
		<iframe
			bind:this={iframe}
			src={iframeSrc}
			{title}
			class={iframeClassName}
			style={`height:${containerHeight}px; width:100%; overflow:hidden; border:none;`}
			scrolling="no"
			frameborder="0"
			{sandbox}
			referrerpolicy={referrerPolicy}
			{allowFullscreen}
			on:load={onLoad}
		/>
	{/if}

	<!-- Corner resize grip (both axes) -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="absolute bottom-0 right-0 w-5 h-5 cursor-nwse-resize group flex items-center justify-center"
		style="z-index:5;"
		on:mousedown={onDragStart}
	>
		<svg class="w-3 h-3 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" viewBox="0 0 10 10" fill="currentColor">
			<circle cx="8" cy="2" r="1.2" />
			<circle cx="4" cy="6" r="1.2" />
			<circle cx="8" cy="6" r="1.2" />
			<circle cx="8" cy="10" r="1.2" />
		</svg>
	</div>

	{#if isDragging}
		<!-- Overlay to prevent iframe from stealing mouse events during drag -->
		<div class="fixed inset-0 z-50"></div>
	{/if}
</div>
