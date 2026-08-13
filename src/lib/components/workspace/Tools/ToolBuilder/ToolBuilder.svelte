<script>
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, tick } from 'svelte';

	const i18n = /** @type {i18nStore} */ (getContext('i18n'));

	import { user } from '$lib/stores';
	import { createOpenAITextStream } from '$lib/apis/streaming';
	import {
		streamToolBuilderChat,
		validateToolBuilderCode,
		getToolBuilderConfig,
		updateToolBuilderConfig
	} from '$lib/apis/tools';

	import Messages from './Messages.svelte';
	import DiffModal from './DiffModal.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import SparklesSolid from '$lib/components/icons/SparklesSolid.svelte';

	// Current tool context (from ToolkitEditor).
	export let id = '';
	export let name = '';
	export let description = '';
	export let content = '';

	export let onApply = (/** @type {string} */ code) => {};
	export let onClose = () => {};

	let loaded = false;
	let loading = false;
	let stopFlag = false;
	let controller = null;

	let input = '';
	let messages = [];

	let messagesContainerElement;
	let scrolledToBottom = true;

	let builderConfig = null; // { enabled, model, configured }
	let apiKeyInput = '';
	// Mirrors config.TOOL_BUILDER_MODEL; only used until the backend config loads.
	const DEFAULT_MODEL = 'claude-opus-5';
	let modelInput = DEFAULT_MODEL;

	// v0.11.0 design tokens, matching AccessButton / AdminSettingField.
	const primaryButtonClass =
		'flex h-7 shrink-0 items-center gap-1.5 rounded-lg bg-gray-900 px-2.5 text-xs text-white transition hover:bg-black disabled:opacity-60 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white';
	const secondaryButtonClass =
		'flex shrink-0 items-center gap-1 rounded-lg bg-gray-50 px-2 py-1 text-xs font-normal text-gray-900 transition ring-1 ring-gray-200 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-850 dark:text-gray-100 dark:ring-gray-800 dark:hover:bg-gray-800';
	const inputClass =
		'w-full h-7 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 text-xs text-gray-700 outline-hidden transition-colors placeholder:text-gray-300 focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:placeholder:text-gray-700 dark:focus:border-blue-500';
	const helpTextClass = 'text-[0.6875rem] text-gray-400 dark:text-gray-600';

	let showDiff = false;
	let validating = false;
	let validation = null; // { ok, error, stage, functions }

	$: storageKey = `tool-builder-chat:${id || 'draft'}`;

	const isAdmin = () => $user?.role === 'admin';

	// ── Proposal extraction (last fenced code block from the last assistant turn) ──
	const extractLastCodeBlock = (md) => {
		if (!md) return '';
		const re = /```(?:python|py)?[ \t]*\r?\n([\s\S]*?)```/g;
		let m;
		let last = '';
		while ((m = re.exec(md)) !== null) last = m[1];
		return last.replace(/\s+$/, '');
	};

	$: latestProposal = (() => {
		for (let k = messages.length - 1; k >= 0; k--) {
			if (messages[k].role === 'assistant') return extractLastCodeBlock(messages[k].content);
		}
		return '';
	})();

	// ── Per-tool localStorage persistence ──
	const loadHistory = (key) => {
		try {
			const raw = localStorage.getItem(key);
			if (raw) return JSON.parse(raw).map((m) => ({ ...m, done: true }));
		} catch (e) {
			console.error(e);
		}
		return [];
	};

	const persist = () => {
		try {
			localStorage.setItem(
				storageKey,
				JSON.stringify(messages.map((m) => ({ role: m.role, content: m.content })))
			);
		} catch (e) {
			console.error(e);
		}
	};

	let lastKey = null;
	$: if (loaded && storageKey !== lastKey) {
		messages = loadHistory(storageKey);
		validation = null;
		lastKey = storageKey;
	}

	// ── Scrolling ──
	const scrollToBottom = () => {
		if (messagesContainerElement && scrolledToBottom) {
			messagesContainerElement.scrollTop = messagesContainerElement.scrollHeight;
		}
	};

	const onScroll = () => {
		if (messagesContainerElement) {
			scrolledToBottom =
				messagesContainerElement.scrollHeight - messagesContainerElement.scrollTop <=
				messagesContainerElement.clientHeight + 10;
		}
	};

	// ── Chat ──
	const chatHandler = async () => {
		if (!builderConfig?.enabled) {
			toast.error($i18n.t('The Tool Builder is disabled.'));
			return;
		}
		if (!builderConfig?.configured) {
			toast.error($i18n.t('The Tool Builder is not configured yet.'));
			return;
		}

		const responseMessage = { role: 'assistant', content: '', done: false };
		messages = [...messages, responseMessage];
		scrolledToBottom = true;
		await tick();
		scrollToBottom();

		stopFlag = false;
		loading = true;
		validation = null;

		const chatMessages = messages
			.filter((m) => !(m.role === 'assistant' && m.content === ''))
			.map((m) => ({ role: m.role, content: m.content }));

		try {
			const [res, ctrl] = await streamToolBuilderChat(localStorage.token, {
				messages: chatMessages,
				tool: { id, name, description, content }
			});
			controller = ctrl;

			if (res && res.ok && res.body) {
				const stream = await createOpenAITextStream(res.body, false);
				for await (const update of stream) {
					if (stopFlag) {
						controller?.abort('user stop');
						break;
					}
					if (update.error) {
						toast.error(`${update.error?.detail ?? update.error}`);
						break;
					}
					if (update.done) break;

					responseMessage.content += update.value;
					messages = messages;
					await tick();
					scrollToBottom();
				}
			} else {
				const err = res ? await res.json().catch(() => null) : null;
				toast.error(err?.detail ?? $i18n.t('Failed to connect to the Tool Builder.'));
			}
		} catch (e) {
			toast.error(`${e}`);
		}

		responseMessage.done = true;
		messages = messages;
		loading = false;
		stopFlag = false;
		controller = null;
		persist();
		await tick();
		scrollToBottom();
	};

	const submitHandler = () => {
		const text = input.trim();
		if (!text || loading) return;
		messages = [...messages, { role: 'user', content: text, done: true }];
		input = '';
		persist();
		chatHandler();
	};

	const stopHandler = () => {
		stopFlag = true;
		controller?.abort('user stop');
	};

	const clearChat = () => {
		messages = [];
		validation = null;
		persist();
	};

	// ── Apply / diff / validate ──
	const applyHandler = () => {
		if (!latestProposal) return;
		onApply(latestProposal);
		toast.success($i18n.t('Applied to editor'));
	};

	const validateHandler = async () => {
		const code = latestProposal || content;
		if (!code) {
			toast.error($i18n.t('There is no code to validate.'));
			return;
		}
		validating = true;
		validation = null;
		try {
			validation = await validateToolBuilderCode(localStorage.token, code);
		} catch (e) {
			validation = { ok: false, stage: 'error', error: `${e}` };
		}
		validating = false;
	};

	// ── Admin config ──
	const saveConfig = async () => {
		try {
			builderConfig = await updateToolBuilderConfig(localStorage.token, {
				anthropic_api_key: apiKeyInput,
				model: modelInput || DEFAULT_MODEL,
				enabled: true
			});
			apiKeyInput = '';
			toast.success($i18n.t('Tool Builder configured.'));
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	onMount(async () => {
		try {
			builderConfig = await getToolBuilderConfig(localStorage.token);
		} catch (e) {
			console.error(e);
			builderConfig = { enabled: true, model: DEFAULT_MODEL, configured: false };
		}
		modelInput = builderConfig?.model || DEFAULT_MODEL;

		messages = loadHistory(storageKey);
		lastKey = storageKey;
		loaded = true;

		await tick();
		scrollToBottom();
	});
</script>

<div class="flex flex-col h-full w-full">
	<!-- Header -->
	<div class="flex shrink-0 items-center justify-between gap-2 pb-2">
		<div class="flex min-w-0 items-center gap-1.5">
			<SparklesSolid className="size-3.5 shrink-0" />
			<div class="truncate text-xs font-medium text-gray-900 dark:text-white">
				{$i18n.t('Build with Claude')}
			</div>
			<Tooltip
				content={$i18n.t(
					'This feature is experimental and may be modified or discontinued without notice.'
				)}
				placement="top"
			>
				<span class={helpTextClass}>({$i18n.t('Experimental')})</span>
			</Tooltip>
		</div>

		<div class="flex shrink-0 items-center gap-1">
			{#if messages.length > 0}
				<button
					class="text-xs text-gray-500 transition-colors hover:text-gray-900 disabled:opacity-50 dark:text-gray-500 dark:hover:text-white"
					type="button"
					on:click={clearChat}
					disabled={loading}
				>
					{$i18n.t('Clear')}
				</button>
			{/if}
			<button
				class="rounded-lg p-0.5 text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-500 dark:hover:text-white"
				type="button"
				on:click={onClose}
				aria-label={$i18n.t('Close')}
			>
				<XMark className="size-4" strokeWidth="2.5" />
			</button>
		</div>
	</div>

	{#if builderConfig && !builderConfig.enabled}
		<div class="flex flex-1 items-center justify-center px-4 text-center text-xs text-gray-500">
			{$i18n.t('The Tool Builder is disabled.')}
		</div>
	{:else if builderConfig && !builderConfig.configured}
		<!-- Not configured -->
		<div class="flex flex-1 flex-col justify-center gap-2.5">
			{#if isAdmin()}
				<div class="text-xs text-gray-600 dark:text-gray-400">
					{$i18n.t('Configure Claude to enable the Tool Builder.')}
				</div>

				<div class="flex flex-col gap-1">
					<div class={helpTextClass}>{$i18n.t('Anthropic API Key')}</div>
					<input
						class={inputClass}
						type="password"
						placeholder={$i18n.t('Anthropic API Key')}
						bind:value={apiKeyInput}
					/>
				</div>

				<div class="flex flex-col gap-1">
					<div class={helpTextClass}>{$i18n.t('Model')}</div>
					<input
						class={inputClass}
						type="text"
						placeholder={DEFAULT_MODEL}
						bind:value={modelInput}
					/>
				</div>

				<button
					class="{primaryButtonClass} self-start"
					type="button"
					on:click={saveConfig}
					disabled={!apiKeyInput}
				>
					{$i18n.t('Save')}
				</button>
			{:else}
				<div class="px-4 text-center text-xs text-gray-500">
					{$i18n.t(
						'The Tool Builder is not configured yet. Ask an admin to add an Anthropic API key.'
					)}
				</div>
			{/if}
		</div>
	{:else}
		<!-- Transcript -->
		<div
			class="flex-1 overflow-auto scrollbar-hidden pr-0.5"
			bind:this={messagesContainerElement}
			on:scroll={onScroll}
		>
			{#if messages.length === 0}
				<div
					class="flex h-full flex-col items-center justify-center gap-1 px-4 text-center text-gray-400 dark:text-gray-600"
				>
					<SparklesSolid className="size-5 mb-1 opacity-60" />
					<div class="text-xs">{$i18n.t('Describe the tool you want to build.')}</div>
					<div class={helpTextClass}>
						{$i18n.t('e.g. "A tool that fetches a URL and returns the page title."')}
					</div>
				</div>
			{:else}
				<Messages bind:messages />
			{/if}
		</div>

		<!-- Proposal action bar -->
		{#if latestProposal && !loading}
			<div
				class="flex shrink-0 flex-col gap-1.5 border-t border-gray-100/50 pt-2 pb-1.5 dark:border-white/[0.04]"
			>
				<div class="flex flex-wrap items-center gap-1.5">
					<button class={primaryButtonClass} type="button" on:click={applyHandler}>
						{$i18n.t('Apply to editor')}
					</button>
					<button
						class={secondaryButtonClass}
						type="button"
						on:click={() => (showDiff = true)}
					>
						{$i18n.t('View diff')}
					</button>
					<button
						class={secondaryButtonClass}
						type="button"
						on:click={validateHandler}
						disabled={validating}
					>
						{#if validating}
							<Spinner className="size-3" />
						{/if}
						{$i18n.t('Validate')}
					</button>
				</div>

				{#if validation}
					{#if validation.ok}
						<div class="text-[0.6875rem] text-green-600 dark:text-green-400">
							{$i18n.t('Valid tool')}{validation.functions?.length
								? ` — ${validation.functions.join(', ')}`
								: ''}
						</div>
					{:else}
						<div class="text-[0.6875rem] break-words text-red-600 dark:text-red-400">
							{validation.stage ? `[${validation.stage}] ` : ''}{validation.error}
						</div>
					{/if}
				{/if}
			</div>
		{/if}

		<!-- Composer -->
		<div class="shrink-0 pt-2 pb-1">
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="flex items-end gap-1.5 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1.5 transition-colors focus-within:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:focus-within:border-blue-500"
				on:keydown={(e) => {
					if (e.key === 'Enter' && !e.shiftKey) {
						e.preventDefault();
						submitHandler();
					}
				}}
			>
				<Textarea
					bind:value={input}
					className="w-full resize-none bg-transparent px-1 text-xs text-gray-700 outline-hidden placeholder:text-gray-300 dark:text-gray-300 dark:placeholder:text-gray-700"
					placeholder={$i18n.t('Ask Claude to build or change this tool…')}
					maxSize={200}
				/>
				{#if loading}
					<Tooltip content={$i18n.t('Stop')} placement="top">
						<button
							class="shrink-0 rounded-lg bg-gray-900 p-1.5 text-white transition hover:bg-black dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
							type="button"
							on:click={stopHandler}
							aria-label={$i18n.t('Stop')}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								class="size-3"
							>
								<rect x="6" y="6" width="12" height="12" rx="2" />
							</svg>
						</button>
					</Tooltip>
				{:else}
					<button
						class="shrink-0 rounded-lg bg-gray-900 p-1.5 text-white transition hover:bg-black disabled:opacity-40 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
						type="button"
						on:click={submitHandler}
						disabled={!input.trim()}
						aria-label={$i18n.t('Send')}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 24 24"
							fill="currentColor"
							class="size-3"
						>
							<path
								fill-rule="evenodd"
								d="M12 2.25a.75.75 0 0 1 .53.22l5.25 5.25a.75.75 0 0 1-1.06 1.06l-3.97-3.97V21a.75.75 0 0 1-1.5 0V4.81L7.28 8.78a.75.75 0 0 1-1.06-1.06l5.25-5.25A.75.75 0 0 1 12 2.25Z"
								clip-rule="evenodd"
							/>
						</svg>
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>

<DiffModal bind:show={showDiff} current={content} proposed={latestProposal} onApply={applyHandler} />
