<template>
	<!-- A status as icon + text on a soft colour; colour is never the only signal. -->
	<span
		class="inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium"
		:class="THEMES[theme || 'gray']"
	>
		<FeatherIcon v-if="icon" :name="icon" class="h-3 w-3 shrink-0" aria-hidden="true" />
		<slot />
	</span>
</template>

<script setup lang="ts">
import { FeatherIcon } from 'frappe-ui'

defineProps<{ theme?: string; icon?: string }>()

const THEMES: Record<string, string> = {
	green: 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-200',
	orange: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
	blue: 'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200',
	red: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
	gray: 'bg-gray-100 text-gray-600 ring-1 ring-inset ring-gray-200',
}
</script>
