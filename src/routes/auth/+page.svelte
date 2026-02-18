<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { getBackendConfig } from '$lib/apis';
	import { getSessionUser, userSignIn, userSignUp, updateUserTimezone } from '$lib/apis/auths';

	import { WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, config, user, socket } from '$lib/stores';

	import { generateInitialsImage, getUserTimezone } from '$lib/utils';

	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let mode: 'signin' | 'signup' = 'signin';

	let name = '';
	let email = '';
	let password = '';
	let confirmPassword = '';

	const setSessionUser = async (sessionUser, redirectPath: string | null = null) => {
		if (sessionUser) {
			console.log(sessionUser);
			toast.success($i18n.t(`You're now logged in.`));
			if (sessionUser.token) {
				localStorage.token = sessionUser.token;
			}
			$socket.emit('user-join', { auth: { token: sessionUser.token } });
			await user.set(sessionUser);
			await config.set(await getBackendConfig());

			const timezone = getUserTimezone();
			if (sessionUser.token && timezone) {
				updateUserTimezone(sessionUser.token, timezone);
			}

			if (!redirectPath) {
				redirectPath = $page.url.searchParams.get('redirect') || '/';
			}

			goto(redirectPath);
			localStorage.removeItem('redirectPath');
		}
	};

	const signInHandler = async () => {
		const sessionUser = await userSignIn(email, password).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		await setSessionUser(sessionUser);
	};

	const signUpHandler = async () => {
		if ($config?.features?.enable_signup_password_confirmation) {
			if (password !== confirmPassword) {
				toast.error($i18n.t('Passwords do not match.'));
				return;
			}
		}

		const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		await setSessionUser(sessionUser);
	};

	const submitHandler = async () => {
		if (mode === 'signin') {
			await signInHandler();
		} else {
			await signUpHandler();
		}
	};

	onMount(async () => {
		const redirectPath = $page.url.searchParams.get('redirect');
		if ($user !== undefined) {
			goto(redirectPath || '/');
		} else {
			if (redirectPath) {
				localStorage.setItem('redirectPath', redirectPath);
			}
		}

		const error = $page.url.searchParams.get('error');
		if (error) {
			toast.error(error);
		}

		const form = $page.url.searchParams.get('form');
		if (form === 'signup') {
			mode = 'signup';
		}

		loaded = true;
	});

	const features = [
		{
			title: 'Contract Review',
			description: 'AI-assisted analysis and review of contracts',
			icon: 'contract'
		},
		{
			title: 'Data Analysis',
			description: 'Transform raw data into actionable insights',
			icon: 'data'
		},
		{
			title: 'Reporting & Metrics',
			description: 'Generate and review performance metrics',
			icon: 'report'
		},
		{
			title: 'PCD Creation',
			description: 'Streamline process control document creation',
			icon: 'pcd'
		},
		{
			title: 'Manufacturing Feedback',
			description: 'Get AI feedback on manufacturing documents',
			icon: 'manufacturing'
		}
	];
</script>

<svelte:head>
	<title>{`${$WEBUI_NAME}`}</title>
</svelte:head>

{#if loaded}
	<div class="flex min-h-screen">
		<!-- LEFT: Branding panel (hidden on mobile, shown lg+) -->
		<div
			class="hidden lg:flex lg:w-1/2 bg-gray-900 text-white flex-col justify-between p-10 relative overflow-hidden"
		>
			<!-- Subtle gradient overlay -->
			<div
				class="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 opacity-80"
			></div>

			<div class="relative z-10 flex flex-col h-full">
				<!-- Logo -->
				<div class="flex items-center gap-3 mb-12">
					<img
						src="{WEBUI_BASE_URL}/static/logo.png"
						class="w-10 h-10 rounded"
						alt="Addman"
						on:error={(e) => {
							e.target.style.display = 'none';
							e.target.nextElementSibling.style.display = 'block';
						}}
					/>
					<span
						class="text-xl font-bold tracking-wide hidden"
						style="display: none;">ADDMAN</span
					>
				</div>

				<!-- Hero -->
				<div class="mb-8">
					<h1 class="text-4xl font-bold tracking-tight mb-2">AOS-GPT</h1>
					<p class="text-lg text-gray-300 font-medium">Secure AI Tools for Manufacturing</p>
					<p class="mt-4 text-sm text-gray-400 leading-relaxed max-w-md">
						A safe and secure environment to interact with AI development tools at Addman.
					</p>
				</div>

				<!-- Feature cards -->
				<div class="flex flex-col gap-3 mt-auto mb-8">
					{#each features as feature}
						<div class="flex items-start gap-3 bg-white/5 rounded-lg px-4 py-3">
							<div class="mt-0.5 shrink-0">
								{#if feature.icon === 'contract'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-5 h-5 text-blue-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
										/>
									</svg>
								{:else if feature.icon === 'data'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-5 h-5 text-green-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z"
										/>
									</svg>
								{:else if feature.icon === 'report'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-5 h-5 text-yellow-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M10.5 6a7.5 7.5 0 1 0 7.5 7.5h-7.5V6Z"
										/>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M13.5 10.5H21A7.5 7.5 0 0 0 13.5 3v7.5Z"
										/>
									</svg>
								{:else if feature.icon === 'pcd'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-5 h-5 text-purple-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15a2.25 2.25 0 0 1 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z"
										/>
									</svg>
								{:else if feature.icon === 'manufacturing'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										class="w-5 h-5 text-orange-400"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085"
										/>
									</svg>
								{/if}
							</div>
							<div>
								<p class="text-sm font-medium text-white">{feature.title}</p>
								<p class="text-xs text-gray-400">{feature.description}</p>
							</div>
						</div>
					{/each}
				</div>
			</div>
		</div>

		<!-- RIGHT: Auth form -->
		<div
			class="w-full lg:w-1/2 bg-white dark:bg-gray-950 flex flex-col items-center justify-center px-6 sm:px-12 py-10 min-h-screen"
		>
			<!-- Mobile-only branding (shown < lg) -->
			<div class="lg:hidden mb-8 text-center">
				<div class="flex items-center justify-center gap-3 mb-3">
					<img
						src="{WEBUI_BASE_URL}/static/logo.png"
						class="w-8 h-8 rounded"
						alt="Addman"
						on:error={(e) => {
							e.target.style.display = 'none';
						}}
					/>
					<span class="text-2xl font-bold text-gray-900 dark:text-white">AOS-GPT</span>
				</div>
				<p class="text-sm text-gray-500 dark:text-gray-400">
					Secure AI Tools for Manufacturing
				</p>
			</div>

			<div class="w-full max-w-sm">
				<!-- Heading -->
				<div class="mb-6">
					<h2 class="text-2xl font-semibold text-gray-900 dark:text-white">
						{#if mode === 'signin'}
							Welcome back
						{:else}
							Create your account
						{/if}
					</h2>
					<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
						{#if mode === 'signin'}
							Sign in to continue to AOS-GPT
						{:else}
							Get started with AOS-GPT
						{/if}
					</p>
				</div>

				<!-- Form -->
				<form
					on:submit|preventDefault={submitHandler}
				>
					<div class="flex flex-col gap-4">
						{#if mode === 'signup'}
							<div>
								<label for="name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
									>{$i18n.t('Name')}</label
								>
								<input
									bind:value={name}
									type="text"
									id="name"
									class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
									autocomplete="name"
									placeholder={$i18n.t('Enter Your Full Name')}
									required
								/>
							</div>
						{/if}

						<div>
							<label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
								>{$i18n.t('Email')}</label
							>
							<input
								bind:value={email}
								type="email"
								id="email"
								class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								autocomplete="email"
								name="email"
								placeholder={$i18n.t('Enter Your Email')}
								required
							/>
						</div>

						<div>
							<label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
								>{$i18n.t('Password')}</label
							>
							<SensitiveInput
								bind:value={password}
								type="password"
								id="password"
								class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder={$i18n.t('Enter Your Password')}
								autocomplete={mode === 'signup' ? 'new-password' : 'current-password'}
								name="password"
								screenReader={false}
								required
							/>
						</div>

						{#if mode === 'signup' && $config?.features?.enable_signup_password_confirmation}
							<div>
								<label
									for="confirm-password"
									class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
									>{$i18n.t('Confirm Password')}</label
								>
								<SensitiveInput
									bind:value={confirmPassword}
									type="password"
									id="confirm-password"
									class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
									placeholder={$i18n.t('Confirm Your Password')}
									autocomplete="new-password"
									name="confirm-password"
									required
								/>
							</div>
						{/if}
					</div>

					<button
						class="mt-6 w-full rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm py-2.5 transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
						type="submit"
					>
						{mode === 'signin' ? $i18n.t('Sign in') : $i18n.t('Create Account')}
					</button>
				</form>

				{#if $config?.features.enable_signup}
					<div class="mt-6 text-sm text-center text-gray-500 dark:text-gray-400">
						{#if mode === 'signin'}
							{$i18n.t("Don't have an account?")}
							<button
								class="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
								type="button"
								on:click={() => { mode = 'signup'; }}
							>
								{$i18n.t('Sign up')}
							</button>
						{:else}
							{$i18n.t('Already have an account?')}
							<button
								class="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
								type="button"
								on:click={() => { mode = 'signin'; }}
							>
								{$i18n.t('Sign in')}
							</button>
						{/if}
					</div>
				{/if}

				<!-- Footer -->
				<div class="mt-10 text-center text-xs text-gray-400 dark:text-gray-600">
					Powered by AOS-GPT &middot; Addman
				</div>
			</div>
		</div>
	</div>
{:else}
	<!-- Loading state -->
	<div class="flex items-center justify-center min-h-screen bg-white dark:bg-gray-950">
		<div class="flex items-center gap-3 text-gray-600 dark:text-gray-300">
			<Spinner className="size-5" />
			<span class="text-sm">Loading...</span>
		</div>
	</div>
{/if}
