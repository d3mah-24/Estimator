<template>
	<!-- Full-screen while a tender PDF is processed; the page behind it is inert. -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
		role="alertdialog"
		aria-modal="true"
		aria-busy="true"
		:aria-label="t('processing.title')"
	>
		<div class="w-full max-w-md rounded-xl bg-surface-white p-6 text-center shadow-2xl">
			<LoadingIndicator class="mx-auto h-10 w-10 text-ink-gray-7" />
			<h2 class="mt-4 text-lg font-semibold text-ink-gray-9">{{ t('processing.title') }}</h2>
			<p v-if="fileName" class="mt-1 truncate text-sm text-ink-gray-6">{{ fileName }}</p>
			<p class="mt-3 text-sm text-ink-gray-7">{{ step }}</p>
			<p class="mt-1 text-xs tabular-nums text-ink-gray-5" aria-live="off">
				{{ t('processing.elapsed', { time: elapsed }) }}
			</p>
			<p class="mt-4 text-xs text-ink-gray-5">{{ t('processing.hint') }}</p>
			<router-link to="/" class="mt-3 inline-block text-xs text-ink-gray-6 underline">{{
				t('processing.leave')
			}}</router-link>
		</div>
	</div>
</template>

<script setup lang="ts">
import { LoadingIndicator } from 'frappe-ui'
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDuration } from '@/utils/format'

const { t } = useI18n()
const props = defineProps<{ fileName?: string; loadingResults?: boolean }>()

const started = Date.now()
const seconds = ref(0)
const timer = setInterval(() => (seconds.value = Math.floor((Date.now() - started) / 1000)), 1000)
onBeforeUnmount(() => clearInterval(timer))

const elapsed = computed(() => formatDuration(seconds.value))
// The job reports no progress; the text says what happens, in the order it happens.
const step = computed(() =>
	props.loadingResults ? t('processing.loading') : t('processing.working'),
)
</script>
