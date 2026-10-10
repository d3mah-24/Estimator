<template>
	<label
		class="flex items-center gap-1.5 text-sm"
		:class="dark ? 'text-white/70' : 'text-ink-gray-6'"
	>
		<span class="sr-only">{{ t('app.language') }}</span>
		<FeatherIcon name="globe" class="h-4 w-4" aria-hidden="true" />
		<select
			:value="locale"
			:aria-label="t('app.language')"
			class="h-7 rounded py-0 pr-7 text-sm"
			:class="
				dark
					? 'form-select border-white/20 bg-white/10 text-white focus:border-white/40 [&>option]:text-ink-gray-9'
					: 'form-select border-outline-gray-2'
			"
			@change="(e) => setLocale((e.target as HTMLSelectElement).value)"
		>
			<option v-for="l in LOCALES" :key="l.code" :value="l.code">{{ l.label }}</option>
		</select>
	</label>
</template>

<script setup lang="ts">
import { FeatherIcon } from 'frappe-ui'
import { useI18n } from 'vue-i18n'
import { LOCALES, setLocale } from '@/i18n'

defineProps<{ dark?: boolean }>()
const { t, locale } = useI18n()
</script>
