<script lang="ts">
	import { getContext, onMount } from 'svelte';

	import { toast } from 'svelte-sonner';
	import { deleteSharedChatById, getChatById, shareChatById } from '$lib/apis/chats';
	import { getChannels, sendMessage } from '$lib/apis/channels';
	import { copyToClipboard } from '$lib/utils';

	import Modal from '../common/Modal.svelte';
	import Link from '../icons/Link.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let chatId;

	let chat = null;
	let shareUrl = null;

	let channels = [];
	let selectedChannelId = '';
	let sharingToChannel = false;

	const i18n = getContext<i18nStore>('i18n');

	onMount(async () => {
		channels = (await getChannels(localStorage.token).catch(() => [])) ?? [];
	});

	// Ensure the chat has a share link, then post it into the selected channel as a
	// read-only, forkable card. Reuses the existing share + clone infrastructure.
	const shareToChannel = async () => {
		if (!selectedChannelId || !chat) return;
		sharingToChannel = true;

		const sharedChat = await shareChatById(localStorage.token, chatId).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (!sharedChat) {
			sharingToChannel = false;
			return;
		}

		const shareId = sharedChat.id;
		const title = chat?.title ?? sharedChat?.title ?? $i18n.t('Shared chat');

		const res = await sendMessage(localStorage.token, selectedChannelId, {
			content: $i18n.t('Shared a chat in this channel.'),
			data: {
				shared_chat: {
					share_id: shareId,
					title
				}
			}
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		sharingToChannel = false;

		if (res) {
			chat = await getChatById(localStorage.token, chatId);
			toast.success($i18n.t('Shared chat to channel'));
			show = false;
		}
	};

	const shareLocalChat = async () => {
		const _chat = chat;

		const sharedChat = await shareChatById(localStorage.token, chatId);
		shareUrl = `${window.location.origin}/s/${sharedChat.id}`;
		console.log(shareUrl);
		chat = await getChatById(localStorage.token, chatId);

		return shareUrl;
	};

	export let show = false;

	const isDifferentChat = (_chat) => {
		if (!chat) {
			return true;
		}
		if (!_chat) {
			return false;
		}
		return chat.id !== _chat.id || chat.share_id !== _chat.share_id;
	};

	$: if (show) {
		(async () => {
			if (chatId) {
				const _chat = await getChatById(localStorage.token, chatId);
				if (isDifferentChat(_chat)) {
					chat = _chat;
				}
			} else {
				chat = null;
				console.log(chat);
			}
		})();
	}
</script>

<Modal bind:show size="md">
	<div>
		<div class=" flex justify-between dark:text-gray-300 px-5 pt-4 pb-0.5">
			<div class=" text-lg font-medium self-center">{$i18n.t('Share Chat')}</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		{#if chat}
			<div class="px-5 pt-4 pb-5 w-full flex flex-col justify-center">
				<div class=" text-sm dark:text-gray-300 mb-1">
					{#if chat.share_id}
						<a href="/s/{chat.share_id}" target="_blank"
							>{$i18n.t('You have shared this chat')}
							<span class=" underline">{$i18n.t('before')}</span>.</a
						>
						{$i18n.t('Click here to')}
						<button
							class="underline"
							on:click={async () => {
								const res = await deleteSharedChatById(localStorage.token, chatId);

								if (res) {
									chat = await getChatById(localStorage.token, chatId);
								}
							}}
							>{$i18n.t('delete this link')}
						</button>
						{$i18n.t('and create a new shared link.')}
					{:else}
						{$i18n.t(
							"Messages you send after creating your link won't be shared. Users with the URL will be able to view the shared chat."
						)}
					{/if}
				</div>

				{#if channels.length > 0}
					<div class="flex flex-col gap-1 mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
						<div class=" text-sm dark:text-gray-300">
							{$i18n.t(
								'Share this chat to a channel. Members can view it (read-only) and fork their own copy.'
							)}
						</div>
						<div class="flex gap-2 mt-1">
							<select
								class="w-full text-sm rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-850 dark:text-gray-100 outline-hidden"
								bind:value={selectedChannelId}
							>
								<option value="" disabled selected>{$i18n.t('Select a channel')}</option>
								{#each channels as channel}
									<option value={channel.id}>{channel.name || $i18n.t('Direct message')}</option>
								{/each}
							</select>
							<button
								class="shrink-0 self-center flex items-center gap-1 px-3.5 py-2 text-sm font-medium bg-gray-100 hover:bg-gray-200 text-gray-800 dark:bg-gray-850 dark:text-white dark:hover:bg-gray-800 transition rounded-full disabled:opacity-50"
								type="button"
								disabled={!selectedChannelId || sharingToChannel}
								on:click={shareToChannel}
							>
								{sharingToChannel ? $i18n.t('Sharing...') : $i18n.t('Share to channel')}
							</button>
						</div>
					</div>
				{/if}

				<div class="flex justify-end">
					<div class="flex flex-col items-end space-x-1 mt-3">
						<div class="flex gap-1">
							<button
								class="self-center flex items-center gap-1 px-3.5 py-2 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
								type="button"
								id="copy-and-share-chat-button"
								on:click={async () => {
									const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

									if (isSafari) {
										// Oh, Safari, you're so special, let's give you some extra love and attention
										console.log('isSafari');

										const getUrlPromise = async () => {
											const url = await shareLocalChat();
											return new Blob([url], { type: 'text/plain' });
										};

										navigator.clipboard
											.write([
												new ClipboardItem({
													'text/plain': getUrlPromise()
												})
											])
											.then(() => {
												console.log('Async: Copying to clipboard was successful!');
												return true;
											})
											.catch((error) => {
												console.error('Async: Could not copy text: ', error);
												return false;
											});
									} else {
										copyToClipboard(await shareLocalChat());
									}

									toast.success($i18n.t('Copied shared chat URL to clipboard!'));
									show = false;
								}}
							>
								<Link />

								{#if chat.share_id}
									{$i18n.t('Update and Copy Link')}
								{:else}
									{$i18n.t('Copy Link')}
								{/if}
							</button>
						</div>
					</div>
				</div>
			</div>
		{/if}
	</div>
</Modal>
