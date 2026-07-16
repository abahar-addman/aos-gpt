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
	let modelInput = 'claude-opus-4-8';

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
				model: modelInput || 'claude-opus-4-8',
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
			builderConfig = { enabled: true, model: 'claude-opus-4-8', configured: false };
		}
		modelInput = builderConfig?.model || 'claude-opus-4-8';

		messages = loadHistory(storageKey);
		lastKey = storageKey;
		loaded = true;

		await tick();
		scrollToBottom();
	});
</script>

<div class="flex flex-col h-full w-full">
	<!-- Header -->
	<div class="flex items-center justify-between pb-1.5 pt-0.5">
		<div class="flex items-center gap-1.5 min-w-0">
			<SparklesSolid className="size-4 shrink-0" />
			<div class="font-medium text-base truncate">{$i18n.t('Build with Claude')}</div>
			<Tooltip
				content={$i18n.t('This feature is experimental and may be modified or discontinued without notice.')}
				placement="top"
			>
				<span class="text-gray-500 text-xs">({$i18n.t('Experimental')})</span>
			</Tooltip>
		</div>

		<div class="flex items-center gap-1">
			{#if messages.length > 0}
				<Tooltip content={$i18n.t('Clear')} placement="top">
					<button
						class="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-1.5 py-1 rounded-lg"
						on:click={clearChat}
						disabled={loading}
					>
						{$i18n.t('Clear')}
					</button>
				</Tooltip>
			{/if}
			<button
				class="p-0.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"
				on:click={onClose}
				aria-label={$i18n.t('Close')}
			>
				<XMark className="size-5" strokeWidth="2.5" />
			</button>
		</div>
	</div>

	{#if builderConfig && !builderConfig.enabled}
		<div class="flex-1 flex items-center justify-center text-sm text-gray-500 px-4 text-center">
			{$i18n.t('The Tool Builder is disabled.')}
		</div>
	{:else if builderConfig && !builderConfig.configured}
		<!-- Not configured -->
		<div class="flex-1 flex flex-col justify-center gap-3 px-2 text-sm">
			{#if isAdmin()}
				<div class="text-gray-600 dark:text-gray-300">
					{$i18n.t('Configure Claude to enable the Tool Builder.')}
				</div>
				<input
					class="w-full rounded-lg px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 outline-hidden"
					type="password"
					placeholder={$i18n.t('Anthropic API Key')}
					bind:value={apiKeyInput}
				/>
				<input
					class="w-full rounded-lg px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 outline-hidden"
					type="text"
					placeholder={$i18n.t('Model')}
					bind:value={modelInput}
				/>
				<button
					class="self-start px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full disabled:opacity-50"
					on:click={saveConfig}
					disabled={!apiKeyInput}
				>
					{$i18n.t('Save')}
				</button>
			{:else}
				<div class="text-gray-500 text-center px-4">
					{$i18n.t('The Tool Builder is not configured yet. Ask an admin to add an Anthropic API key.')}
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
				<div class="h-full flex flex-col items-center justify-center text-center text-sm text-gray-500 gap-1 px-4">
					<SparklesSolid className="size-6 mb-1 opacity-70" />
					<div>{$i18n.t('Describe the tool you want to build.')}</div>
					<div class="text-xs">
						{$i18n.t('e.g. "A tool that fetches a URL and returns the page title."')}
					</div>
				</div>
			{:else}
				<Messages bind:messages />
			{/if}
		</div>

		<!-- Proposal action bar -->
		{#if latestProposal && !loading}
			<div class="border-t border-gray-50 dark:border-gray-850 pt-2 pb-1.5 flex flex-col gap-1.5">
				<div class="flex items-center gap-1.5">
					<button
						class="px-3 py-1 text-xs font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
						on:click={applyHandler}
					>
						{$i18n.t('Apply to editor')}
					</button>
					<button
						class="px-3 py-1 text-xs rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
						on:click={() => (showDiff = true)}
					>
						{$i18n.t('View diff')}
					</button>
					<button
						class="px-3 py-1 text-xs rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-1"
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
						<div class="text-xs text-green-600 dark:text-green-400">
							{$i18n.t('Valid tool')}{validation.functions?.length
								? ` — ${validation.functions.join(', ')}`
								: ''}
						</div>
					{:else}
						<div class="text-xs text-red-600 dark:text-red-400 break-words">
							{validation.stage ? `[${validation.stage}] ` : ''}{validation.error}
						</div>
					{/if}
				{/if}
			</div>
		{/if}

		<!-- Composer -->
		<div class="pt-2 pb-1">
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="flex items-end gap-1.5 rounded-2xl bg-gray-50 dark:bg-gray-850 px-2 py-1.5"
				on:keydown={(e) => {
					if (e.key === 'Enter' && !e.shiftKey) {
						e.preventDefault();
						submitHandler();
					}
				}}
			>
				<Textarea
					bind:value={input}
					className="w-full bg-transparent outline-hidden text-sm resize-none px-1"
					placeholder={$i18n.t('Ask Claude to build or change this tool…')}
					maxSize={200}
				/>
				{#if loading}
					<Tooltip content={$i18n.t('Stop')} placement="top">
						<button
							class="shrink-0 p-1.5 rounded-full bg-black text-white dark:bg-white dark:text-black"
							on:click={stopHandler}
							aria-label={$i18n.t('Stop')}
						>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-3.5">
								<rect x="6" y="6" width="12" height="12" rx="2" />
							</svg>
						</button>
					</Tooltip>
				{:else}
					<button
						class="shrink-0 p-1.5 rounded-full bg-black text-white dark:bg-white dark:text-black transition disabled:opacity-40"
						on:click={submitHandler}
						disabled={!input.trim()}
						aria-label={$i18n.t('Send')}
					>
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-3.5">
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
