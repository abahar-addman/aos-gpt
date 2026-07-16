<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<i18nStore>('i18n');

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let show = false;
	export let current = '';
	export let proposed = '';
	export let onApply = () => {};

	type DiffLine = { t: 'ctx' | 'add' | 'del'; text: string };

	// Minimal LCS-based line diff. Guarded against pathological sizes.
	const diffLines = (a: string, b: string): DiffLine[] => {
		const A = (a ?? '').split('\n');
		const B = (b ?? '').split('\n');
		const n = A.length;
		const m = B.length;

		if (n * m > 4_000_000) {
			// Too large to diff cheaply — show the proposed file as all-added.
			return B.map((text) => ({ t: 'add', text }));
		}

		const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
		for (let i = n - 1; i >= 0; i--) {
			for (let j = m - 1; j >= 0; j--) {
				dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
			}
		}

		const out: DiffLine[] = [];
		let i = 0;
		let j = 0;
		while (i < n && j < m) {
			if (A[i] === B[j]) {
				out.push({ t: 'ctx', text: A[i] });
				i++;
				j++;
			} else if (dp[i + 1][j] >= dp[i][j + 1]) {
				out.push({ t: 'del', text: A[i] });
				i++;
			} else {
				out.push({ t: 'add', text: B[j] });
				j++;
			}
		}
		while (i < n) out.push({ t: 'del', text: A[i++] });
		while (j < m) out.push({ t: 'add', text: B[j++] });
		return out;
	};

	$: lines = show ? diffLines(current, proposed) : [];
	$: added = lines.filter((l) => l.t === 'add').length;
	$: removed = lines.filter((l) => l.t === 'del').length;
</script>

<Modal bind:show size="xl">
	<div class="flex flex-col max-h-[85dvh]">
		<div class="flex items-center justify-between px-5 pt-4 pb-2">
			<div class="flex items-center gap-2">
				<div class="text-lg font-medium">{$i18n.t('Review changes')}</div>
				<div class="text-xs text-gray-500">
					<span class="text-green-600 dark:text-green-400">+{added}</span>
					<span class="text-red-600 dark:text-red-400">−{removed}</span>
				</div>
			</div>
			<button class="p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" on:click={() => (show = false)}>
				<XMark className="size-5" />
			</button>
		</div>

		<div class="px-5 pb-3 flex-1 overflow-auto">
			<pre class="text-xs leading-5 font-mono rounded-lg border border-gray-100 dark:border-gray-800 overflow-x-auto"><code
					>{#each lines as line}<div
							class="px-2 whitespace-pre {line.t === 'add'
								? 'bg-green-500/10 text-green-700 dark:text-green-300'
								: line.t === 'del'
									? 'bg-red-500/10 text-red-700 dark:text-red-300'
									: 'text-gray-600 dark:text-gray-400'}"
						>{line.t === 'add' ? '+ ' : line.t === 'del' ? '- ' : '  '}{line.text || ' '}</div>{/each}</code
				></pre>
		</div>

		<div class="px-5 py-3 flex justify-end gap-2 border-t border-gray-50 dark:border-gray-850">
			<button
				class="px-3.5 py-1.5 text-sm rounded-full hover:bg-gray-50 dark:hover:bg-gray-800"
				on:click={() => (show = false)}
			>
				{$i18n.t('Cancel')}
			</button>
			<button
				class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
				on:click={() => {
					onApply();
					show = false;
				}}
			>
				{$i18n.t('Apply')}
			</button>
		</div>
	</div>
</Modal>
