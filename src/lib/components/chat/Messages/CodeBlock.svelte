<script lang="ts">
	import hljs from 'highlight.js';
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, tick, onDestroy } from 'svelte';
	import { config, pyodideWorker as pyodideWorkerStore } from '$lib/stores';

	import { createPyodideWorker } from '$lib/pyodide/createPyodideWorker';
	import { executeCode } from '$lib/apis/utils';
	import {
		copyToClipboard,
		initMermaid,
		renderMermaidDiagram,
		renderVegaVisualization,
		isMermaidData,
		renderPlotlyVisualization,
		unescapeHtml
	} from '$lib/utils';

	import 'highlight.js/styles/github-dark.min.css';
	import equal from 'fast-deep-equal';

	import CodeEditor from '$lib/components/common/CodeEditor.svelte';
	import SvgPanZoom from '$lib/components/common/SVGPanZoom.svelte';

	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import ChevronUpDown from '$lib/components/icons/ChevronUpDown.svelte';
	import CommandLine from '$lib/components/icons/CommandLine.svelte';
	import Cube from '$lib/components/icons/Cube.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext<i18nStore>('i18n');

	export let id = '';
	export let edit = true;

	export let onSave = (e) => {};
	export let onUpdate = (e, codeBlockId = '') => {};
	export let onPreview = (e) => {};

	export let save = false;
	export let run = true;
	export let preview = false;
	export let collapsed = false;

	export let token;
	export let lang = '';
	export let code = '';
	export let attributes = {};

	export let className = '';
	export let editorClassName = '';
	export let stickyButtonsClassName = 'top-0';

	let localPyodideWorker = null;

	let _code = '';
	$: if (code) {
		updateCode();
	}

	const updateCode = () => {
		_code = code;
	};

	let _token = null;

	let renderHTML = null;
	let renderError = null;

	let highlightedCode = null;
	let executing = false;

	let stdout = null;
	let stderr = null;
	let result = null;
	let files = null;

	let copied = false;
	let saved = false;

	const collapseCodeBlock = () => {
		collapsed = !collapsed;
	};

	const saveCode = () => {
		saved = true;

		code = _code;
		onSave(code);

		setTimeout(() => {
			saved = false;
		}, 1000);
	};

	const copyCode = async () => {
		copied = true;
		await copyToClipboard(_code);

		setTimeout(() => {
			copied = false;
		}, 1000);
	};

	const previewCode = () => {
		onPreview(code);
	};

	const checkPythonCode = (str) => {
		// Check if the string contains typical Python syntax characters
		const pythonSyntax = [
			'def ',
			'else:',
			'elif ',
			'try:',
			'except:',
			'finally:',
			'yield ',
			'lambda ',
			'assert ',
			'nonlocal ',
			'del ',
			'True',
			'False',
			'None',
			' and ',
			' or ',
			' not ',
			' in ',
			' is ',
			' with '
		];

		for (let syntax of pythonSyntax) {
			if (str.includes(syntax)) {
				return true;
			}
		}

		// If none of the above conditions met, it's probably not Python code
		return false;
	};

	const executePython = async (code) => {
		result = null;
		stdout = null;
		stderr = null;

		executing = true;

		if ($config?.code?.engine === 'jupyter') {
			const output = await executeCode(localStorage.token, code).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (output) {
				if (output['stdout']) {
					stdout = output['stdout'];
					const stdoutLines = stdout.split('\n');

					for (const [idx, line] of stdoutLines.entries()) {
						if (line.startsWith('data:image/png;base64')) {
							if (files) {
								files.push({
									type: 'image/png',
									data: line
								});
							} else {
								files = [
									{
										type: 'image/png',
										data: line
									}
								];
							}

							if (stdout.includes(`${line}\n`)) {
								stdout = stdout.replace(`${line}\n`, ``);
							} else if (stdout.includes(`${line}`)) {
								stdout = stdout.replace(`${line}`, ``);
							}
						}
					}
				}

				if (output['result']) {
					result = output['result'];
					const resultLines = result.split('\n');

					for (const [idx, line] of resultLines.entries()) {
						if (line.startsWith('data:image/png;base64')) {
							if (files) {
								files.push({
									type: 'image/png',
									data: line
								});
							} else {
								files = [
									{
										type: 'image/png',
										data: line
									}
								];
							}

							if (result.includes(`${line}\n`)) {
								result = result.replace(`${line}\n`, ``);
							} else if (result.includes(`${line}`)) {
								result = result.replace(`${line}`, ``);
							}
						}
					}
				}

				output['stderr'] && (stderr = output['stderr']);
			}

			executing = false;
		} else {
			executePythonAsWorker(code);
		}
	};

	const executePythonAsWorker = async (code) => {
		let packages = [
			/\bimport\s+requests\b|\bfrom\s+requests\b/.test(code) ? 'requests' : null,
			/\bimport\s+bs4\b|\bfrom\s+bs4\b/.test(code) ? 'beautifulsoup4' : null,
			/\bimport\s+numpy\b|\bfrom\s+numpy\b/.test(code) ? 'numpy' : null,
			/\bimport\s+pandas\b|\bfrom\s+pandas\b/.test(code) ? 'pandas' : null,
			/\bimport\s+matplotlib\b|\bfrom\s+matplotlib\b/.test(code) ? 'matplotlib' : null,
			/\bimport\s+seaborn\b|\bfrom\s+seaborn\b/.test(code) ? 'seaborn' : null,
			/\bimport\s+sklearn\b|\bfrom\s+sklearn\b/.test(code) ? 'scikit-learn' : null,
			/\bimport\s+scipy\b|\bfrom\s+scipy\b/.test(code) ? 'scipy' : null,
			/\bimport\s+re\b|\bfrom\s+re\b/.test(code) ? 'regex' : null,
			/\bimport\s+seaborn\b|\bfrom\s+seaborn\b/.test(code) ? 'seaborn' : null,
			/\bimport\s+sympy\b|\bfrom\s+sympy\b/.test(code) ? 'sympy' : null,
			/\bimport\s+tiktoken\b|\bfrom\s+tiktoken\b/.test(code) ? 'tiktoken' : null,
			/\bimport\s+pytz\b|\bfrom\s+pytz\b/.test(code) ? 'pytz' : null,
			/\bimport\s+plotly\b|\bfrom\s+plotly\b/.test(code) ? 'plotly' : null
		].filter(Boolean);

		console.log(packages);

		// Reuse the shared Pyodide worker when code interpreter is active,
		// so files written here are immediately visible in PyodideFileNav.
		// Otherwise fall back to a throwaway worker.
		const sharedWorker = $pyodideWorkerStore;
		const isShared = !!sharedWorker;
		const worker = sharedWorker ?? createPyodideWorker();

		if (!isShared) {
			localPyodideWorker = worker;
		}

		worker.postMessage({
			id: id,
			code: code,
			packages: packages
		});

		const timeoutId = setTimeout(() => {
			if (executing) {
				executing = false;
				stderr = 'Execution Time Limit Exceeded';
				if (!isShared) {
					worker.terminate();
					localPyodideWorker = null;
				}
			}
		}, 60000);

		const handler = (event) => {
			// Ignore messages from other requests on the shared worker
			if (event.data?.id !== id) return;

			console.log('pyodideWorker.onmessage', event);
			const { id: _id, ...data } = event.data;

			console.log(_id, data);

			if (data['stdout']) {
				stdout = data['stdout'];
				const stdoutLines = stdout.split('\n');

				for (const [idx, line] of stdoutLines.entries()) {
					if (line.startsWith('data:image/png;base64')) {
						if (files) {
							files.push({
								type: 'image/png',
								data: line
							});
						} else {
							files = [
								{
									type: 'image/png',
									data: line
								}
							];
						}

						if (stdout.includes(`${line}\n`)) {
							stdout = stdout.replace(`${line}\n`, ``);
						} else if (stdout.includes(`${line}`)) {
							stdout = stdout.replace(`${line}`, ``);
						}
					} else if (line.startsWith('data:text/html;base64,')) {
						if (files) {
							files.push({
								type: 'text/html',
								data: line
							});
						} else {
							files = [
								{
									type: 'text/html',
									data: line
								}
							];
						}

						if (stdout.includes(`${line}\n`)) {
							stdout = stdout.replace(`${line}\n`, ``);
						} else if (stdout.includes(`${line}`)) {
							stdout = stdout.replace(`${line}`, ``);
						}
					}
				}
			}

			if (data['result']) {
				result = data['result'];
				const resultLines = result.split('\n');

				for (const [idx, line] of resultLines.entries()) {
					if (line.startsWith('data:image/png;base64')) {
						if (files) {
							files.push({
								type: 'image/png',
								data: line
							});
						} else {
							files = [
								{
									type: 'image/png',
									data: line
								}
							];
						}

						if (result.startsWith(`${line}\n`)) {
							result = result.replace(`${line}\n`, ``);
						} else if (result.startsWith(`${line}`)) {
							result = result.replace(`${line}`, ``);
						}
					} else if (line.startsWith('data:text/html;base64,')) {
						if (files) {
							files.push({
								type: 'text/html',
								data: line
							});
						} else {
							files = [
								{
									type: 'text/html',
									data: line
								}
							];
						}

						if (result.startsWith(`${line}\n`)) {
							result = result.replace(`${line}\n`, ``);
						} else if (result.startsWith(`${line}`)) {
							result = result.replace(`${line}`, ``);
						}
					}
				}
			}

			data['stderr'] && (stderr = data['stderr']);

			clearTimeout(timeoutId);
			worker.removeEventListener('message', handler);
			executing = false;

			// Signal PyodideFileNav to auto-refresh after execution
			window.dispatchEvent(new Event('pyodide:files'));
		};

		worker.addEventListener('message', handler);

		worker.onerror = (event) => {
			console.log('pyodideWorker.onerror', event);
			clearTimeout(timeoutId);
			worker.removeEventListener('message', handler);
			executing = false;
		};
	};

	let mermaid = null;
	let mermaidTheme = null;
	const renderMermaid = async (code, dark) => {
		// initMermaid() reads the current .dark class, so re-running it is how a diagram picks up
		// a theme flip. The dynamic import is cached, so this is just an initialize() call.
		const wanted = dark ? 'dark' : 'light';
		if (!mermaid || mermaidTheme !== wanted) {
			mermaid = await initMermaid();
			mermaidTheme = wanted;
		}
		return await renderMermaidDiagram(mermaid, code);
	};

	let plotlyHTML = null;

	// marked puts the whole info string in `lang`, so ```plotly {caption="Q3"} arrives as
	// 'plotly {caption="Q3"}', and the case is whatever the model happened to type.
	const baseLang = () => (lang ?? '').trim().split(/\s+/)[0].toLowerCase();

	const isMermaidBlock = () => {
		if (baseLang() === 'mermaid') return true;
		if (baseLang() === '' && isMermaidData(code)) return true;
		return false;
	};

	const isVegaBlock = () => ['vega', 'vega-lite'].includes(baseLang());

	// Deprecated renderer, kept so charts already in chat history keep displaying. Only an
	// explicit ```plotly fence qualifies: the old content-sniffing also claimed ```json and bare
	// blocks, so any JSON payload with a `data` array was turned into a chart iframe.
	const isPlotlyBlock = () => baseLang() === 'plotly';

	const isChartBlock = () => isMermaidBlock() || isVegaBlock() || isPlotlyBlock();

	// Charts only render once the fence has closed — a half-streamed spec is not parseable.
	// Both fence characters count: ~~~ is valid markdown and previously never satisfied this.
	const isComplete = () => {
		const raw = (token?.raw ?? '').trimEnd();
		return raw.endsWith('```') || raw.endsWith('~~~');
	};

	const readDarkMode = () =>
		typeof document !== 'undefined' && document.documentElement.classList.contains('dark');

	let isDark = readDarkMode();
	let themeObserver = null;

	// A chat can hold dozens of charts; rendering the offscreen ones costs a Vega dataflow
	// evaluation and a full SVG serialisation each. Hold off until the block is near the viewport.
	let chartContainer = null;
	let chartVisible = typeof IntersectionObserver === 'undefined';
	let visibilityObserver = null;
	let visibilityFallbackTimer = null;

	const renderChart = async (dark = isDark) => {
		if (!isChartBlock()) {
			// The {#each} rendering these blocks is keyed by index, so this component instance gets
			// reused for a different token. Drop the previous token's chart or it shadows whatever
			// lands in the slot next.
			renderHTML = null;
			plotlyHTML = null;
			renderError = null;
			return;
		}

		if (!isComplete() || !chartVisible) {
			return;
		}

		renderError = null;

		// Same reuse hazard across renderer types: plotlyHTML wins the template's branch order, so
		// a stale iframe would hide a vega/mermaid block rendered into the same instance.
		if (isPlotlyBlock()) {
			renderHTML = null;
		} else {
			plotlyHTML = null;
		}

		if (isMermaidBlock()) {
			try {
				renderHTML = await renderMermaid(code, dark);
			} catch (error) {
				console.error('Failed to render mermaid diagram:', error);
				const errorMsg = error instanceof Error ? error.message : String(error);
				renderError = $i18n.t('Failed to render diagram') + `: ${errorMsg}`;
				renderHTML = null;
			}
		} else if (isVegaBlock()) {
			try {
				renderHTML = await renderVegaVisualization(code, lang, dark);
			} catch (error) {
				console.error('Failed to render Vega visualization:', error);
				const errorMsg = error instanceof Error ? error.message : String(error);
				renderError = $i18n.t('Failed to render visualization') + `: ${errorMsg}`;
				renderHTML = null;
			}
		} else if (isPlotlyBlock()) {
			try {
				plotlyHTML = renderPlotlyVisualization(code);
			} catch (error) {
				console.error('Failed to render Plotly chart:', error);
				const errorMsg = error instanceof Error ? error.message : String(error);
				renderError = $i18n.t('Failed to render visualization') + `: ${errorMsg}`;
				plotlyHTML = null;
			}
		}
	};

	$: if (token) {
		if (token.text !== _token?.text || token.raw !== _token?.raw) {
			_token = token;
		} else if (!equal(token, _token)) {
			_token = token;
		}
	}

	// Stays token-driven exactly as before: a theme flip or a chart scrolling into view must not
	// re-notify the parent.
	$: if (_token) {
		onUpdate(token, id);
	}

	// Listed dependencies are explicit so it is obvious what re-renders a chart: new content, an
	// app theme flip, or the block scrolling into range.
	const renderChartOn = (..._deps) => {
		if (_token) {
			renderChart(isDark);
		}
	};

	$: renderChartOn(_token, isDark, chartVisible);

	$: if (attributes) {
		onAttributesUpdate();
	}

	const onAttributesUpdate = () => {
		if (attributes?.output) {
			try {
				const output = JSON.parse(unescapeHtml(attributes.output));
				stdout = output.stdout;
				stderr = output.stderr;
				result = output.result;
			} catch (error) {
				console.error('Error:', error);
			}
		}
	};

	onMount(async () => {
		if (token) {
			onUpdate(token, id);
		}

		if (!isChartBlock()) {
			return;
		}

		// Watch the class rather than the theme store: 'system' resolves against the OS at runtime,
		// and the store is set before the class is applied, so the element is the authoritative
		// source either way.
		isDark = readDarkMode();
		themeObserver = new MutationObserver(() => {
			const next = readDarkMode();
			if (next !== isDark) {
				isDark = next;
			}
		});
		themeObserver.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ['class']
		});

		if (typeof IntersectionObserver !== 'undefined' && chartContainer) {
			let observerReported = false;

			visibilityObserver = new IntersectionObserver(
				(entries) => {
					// Any delivery — intersecting or not — proves the observer works here.
					observerReported = true;
					if (entries.some((entry) => entry.isIntersecting)) {
						chartVisible = true;
						// One-shot: charts stay rendered once seen, so unhook immediately.
						visibilityObserver?.disconnect();
						visibilityObserver = null;
					}
				},
				{ rootMargin: '600px 0px' }
			);
			visibilityObserver.observe(chartContainer);

			// A hidden, occluded or throttled tab never paints, so IntersectionObserver never
			// delivers at all and the chart would sit on the placeholder indefinitely. A visible
			// tab reports within a frame — including a truthful "not intersecting" for offscreen
			// blocks, which must stay deferred — so only total silence triggers the eager fallback.
			visibilityFallbackTimer = setTimeout(() => {
				if (!observerReported) {
					chartVisible = true;
				}
			}, 2000);
		} else {
			chartVisible = true;
		}
	});

	onDestroy(() => {
		if (localPyodideWorker) {
			localPyodideWorker.terminate();
			localPyodideWorker = null;
		}

		themeObserver?.disconnect();
		themeObserver = null;
		visibilityObserver?.disconnect();
		visibilityObserver = null;
		clearTimeout(visibilityFallbackTimer);
		visibilityFallbackTimer = null;
	});
</script>

<div bind:this={chartContainer}>
	<div
		class="relative {className} flex flex-col rounded-2xl border border-gray-100/30 dark:border-gray-850/30 my-0.5"
		dir="ltr"
	>
		{#if plotlyHTML}
			<div class="rounded-2xl overflow-hidden">
				<iframe
					srcdoc={plotlyHTML}
					class="w-full rounded-2xl border-0"
					style="height: 500px;"
					sandbox="allow-scripts"
					title={$i18n.t('Chart')}
				></iframe>
			</div>
		{:else if isPlotlyBlock()}
			{#if renderError}
				<div class="p-3">
					<div
						class="flex gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-2xl mb-2"
					>
						{renderError}
					</div>
					<details>
						<summary class="text-xs text-gray-500 cursor-pointer select-none">
							{$i18n.t('Show chart source')}
						</summary>
						<pre class="mt-2 text-xs overflow-x-auto">{code}</pre>
					</details>
				</div>
			{:else if isComplete()}
				<div class="p-3">
					<div class="animate-pulse flex flex-col gap-2" aria-hidden="true">
						<div class="h-3 w-24 rounded bg-gray-100 dark:bg-gray-850"></div>
						<div class="h-40 rounded-xl bg-gray-50 dark:bg-gray-850/60"></div>
					</div>
				</div>
			{:else}
				<div class="p-3"><pre>{code}</pre></div>
			{/if}
		{:else if isMermaidBlock() || isVegaBlock()}
			{#if renderHTML}
				<SvgPanZoom
					className=" rounded-2xl max-h-fit overflow-hidden"
					svg={renderHTML}
					content={_token.text}
				/>
			{:else if isComplete() && !renderError}
				<div class="p-3">
					<div class="animate-pulse flex flex-col gap-2" aria-hidden="true">
						<div class="h-3 w-24 rounded bg-gray-100 dark:bg-gray-850"></div>
						<div class="h-40 rounded-xl bg-gray-50 dark:bg-gray-850/60"></div>
					</div>
				</div>
			{:else if renderError}
				<div class="p-3">
					<div
						class="flex gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-2xl mb-2"
					>
						{renderError}
					</div>
					<details>
						<summary class="text-xs text-gray-500 cursor-pointer select-none">
							{$i18n.t('Show chart source')}
						</summary>
						<pre class="mt-2 text-xs overflow-x-auto">{code}</pre>
					</details>
				</div>
			{:else}
				<div class="p-3"><pre>{code}</pre></div>
			{/if}
		{:else}
			<div
				class="sticky {stickyButtonsClassName} left-0 right-0 py-1.5 px-3.5 gap-2 flex items-center justify-end w-full z-10 text-xs text-black dark:text-white bg-white dark:bg-black rounded-t-2xl"
			>
				<div class="flex-1 truncate">
					<Tooltip content={lang} placement="top-start">
						<span class=" truncate text-ellipsis">
							{lang}
						</span>
					</Tooltip>
				</div>

				<div class="flex items-center gap-0.5 shrink-0">
					<button
						class="flex gap-1 items-center bg-none border-none transition rounded-md px-1.5 py-0.5 bg-white dark:bg-black"
						on:click={collapseCodeBlock}
					>
						<div class=" -translate-y-[0.5px]">
							<ChevronUpDown className="size-3" />
						</div>

						<div>
							{collapsed ? $i18n.t('Expand') : $i18n.t('Collapse')}
						</div>
					</button>

					{#if ($config?.features?.enable_code_execution ?? true) && (lang.toLowerCase() === 'python' || lang.toLowerCase() === 'py' || (lang === '' && checkPythonCode(code)))}
						{#if executing}
							<div
								class="run-code-button bg-none border-none p-0.5 cursor-not-allowed bg-white dark:bg-black"
							>
								{$i18n.t('Running')}
							</div>
						{:else if run}
							<button
								class="flex gap-1 items-center run-code-button bg-none border-none transition rounded-md px-1.5 py-0.5 bg-white dark:bg-black"
								on:click={async () => {
									code = _code;
									await tick();
									executePython(code);
								}}
							>
								<div>
									{$i18n.t('Run')}
								</div>
							</button>
						{/if}
					{/if}

					{#if save}
						<button
							class="save-code-button bg-none border-none transition rounded-md px-1.5 py-0.5 bg-white dark:bg-black"
							on:click={saveCode}
						>
							{saved ? $i18n.t('Saved') : $i18n.t('Save')}
						</button>
					{/if}

					<button
						class="copy-code-button bg-none border-none transition rounded-md px-1.5 py-0.5 bg-white dark:bg-black"
						on:click={copyCode}>{copied ? $i18n.t('Copied') : $i18n.t('Copy')}</button
					>

					{#if preview && ['html', 'svg'].includes(lang)}
						<button
							class="flex gap-1 items-center run-code-button bg-none border-none transition rounded-md px-1.5 py-0.5 bg-white dark:bg-black"
							on:click={previewCode}
						>
							<div>
								{$i18n.t('Preview')}
							</div>
						</button>
					{/if}
				</div>
			</div>

			<div
				class="language-{lang} rounded-t-2xl -mt-8 {editorClassName
					? editorClassName
					: executing || stdout || stderr || result
						? ''
						: 'rounded-b-2xl'} overflow-hidden"
			>
				<div class=" pt-6.5 bg-white dark:bg-black"></div>

				{#if !collapsed}
					{#if edit}
						<CodeEditor
							value={code}
							{id}
							{lang}
							onSave={() => {
								saveCode();
							}}
							onChange={(value) => {
								_code = value;
							}}
						/>
					{:else}
						<pre
							class=" hljs p-4 px-5 overflow-x-auto"
							style="border-top-left-radius: 0px; border-top-right-radius: 0px; {(executing ||
								stdout ||
								stderr ||
								result) &&
								'border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;'}"><code
								class="language-{lang} rounded-t-none whitespace-pre text-sm"
								>{#if lang && hljs.getLanguage(lang)}{@html hljs.highlight(code, {
										language: lang,
										ignoreIllegals: true
									}).value}{:else}{code}{/if}</code
							></pre>
					{/if}
				{:else}
					<div
						class="bg-white dark:bg-black dark:text-white rounded-b-2xl! pt-1 pb-2 px-4 flex flex-col gap-2 text-xs"
					>
						<span class="text-gray-500 italic">
							{$i18n.t('{{COUNT}} hidden lines', {
								COUNT: code.split('\n').length
							})}
						</span>
					</div>
				{/if}
			</div>

			{#if !collapsed}
				<div
					id="plt-canvas-{id}"
					class="bg-gray-50 dark:bg-black dark:text-white max-w-full overflow-x-auto scrollbar-hidden"
				/>

				{#if executing || stdout || stderr || result || files}
					<div
						class="bg-gray-50 dark:bg-black dark:text-white rounded-b-2xl! pt-2 pb-3 px-3.5 flex flex-col gap-2"
					>
						{#if executing}
							<div class=" ">
								<div class=" text-gray-500 text-xs mb-1">{$i18n.t('STDOUT/STDERR')}</div>
								<div class="text-sm">{$i18n.t('Running...')}</div>
							</div>
						{:else}
							{#if stdout || stderr}
								<div class=" ">
									<div class=" text-gray-500 text-xs mb-1">{$i18n.t('STDOUT/STDERR')}</div>
									<div
										class="text-sm font-mono whitespace-pre-wrap {stdout?.split('\n')?.length > 100
											? `max-h-96`
											: ''}  overflow-y-auto"
									>
										{stdout || stderr}
									</div>
								</div>
							{/if}
							{#if result || files}
								<div class=" ">
									<div class=" text-gray-500 text-xs mb-1">{$i18n.t('RESULT')}</div>
									{#if result}
										<div class="text-sm">{`${JSON.stringify(result)}`}</div>
									{/if}
									{#if files}
										<div class="flex flex-col gap-2">
											{#each files as file}
												{#if file.type.startsWith('image')}
													<img src={file.data} alt="Output" class=" w-full max-w-[36rem]" />
												{:else if file.type === 'text/html'}
													<iframe
														srcdoc={atob(file.data.replace('data:text/html;base64,', ''))}
														class="w-full max-w-[36rem] rounded-lg border"
														style="height: 500px;"
														sandbox="allow-scripts allow-same-origin"
														title="Plotly Chart"
													></iframe>
												{/if}
											{/each}
										</div>
									{/if}
								</div>
							{/if}
						{/if}
					</div>
				{/if}
			{/if}
		{/if}
	</div>
</div>
