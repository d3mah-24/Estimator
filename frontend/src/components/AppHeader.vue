<template>
	<!-- App frame: brand, navigation, language. Same on every page. -->
	<header class="flex h-12 shrink-0 items-center gap-6 bg-navy-900 px-5 text-white">
		<router-link to="/" class="flex items-center gap-2" :aria-label="t('app.home')">
			<span
				class="flex h-7 w-7 items-center justify-center rounded-md bg-brand-500 text-sm font-bold"
				aria-hidden="true"
				>EB</span
			>
			<span class="text-base font-semibold tracking-tight">Equans Bid</span>
		</router-link>
		<nav class="flex items-center gap-1 text-sm">
			<router-link
				to="/"
				class="rounded-md px-3 py-1.5 text-white/70 hover:bg-white/10 hover:text-white"
				:class="route.name === 'TenderList' ? 'bg-white/10 text-white' : ''"
				>{{ t('list.title') }}</router-link
			>
		</nav>
		<div class="ml-auto flex items-center gap-3">
			<span class="hidden text-xs text-white/50 md:inline">{{ t('app.tagline') }}</span>
			<LanguageSwitcher dark />
		</div>
	</header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'

const { t } = useI18n()
const route = useRoute()
</script>
