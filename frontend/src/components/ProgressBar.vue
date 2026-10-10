<template>
	<!-- Stacked shares (0..1) of one total; the grey rest is not covered by any part. -->
	<div>
		<div
			class="flex h-2 overflow-hidden rounded-full bg-surface-gray-3"
			role="img"
			:aria-label="
				parts
					.map((p) => `${p.label} ${formatPercent(p.share, { maxDigits: 0 })}`)
					.join(', ')
			"
		>
			<div
				v-for="p in parts"
				:key="p.key"
				:class="p.class"
				:style="{ width: `${Math.max(0, Math.min(1, p.share)) * 100}%` }"
			/>
		</div>
		<div v-if="!compact" class="mt-1 flex gap-3 text-xs text-ink-gray-5">
			<span v-for="p in parts" :key="p.key" class="inline-flex items-center gap-1">
				<span class="h-2 w-2 rounded-full" :class="p.class" aria-hidden="true" />
				{{ formatPercent(p.share, { maxDigits: 0 }) }}
			</span>
		</div>
	</div>
</template>

<script setup lang="ts">
import { formatPercent } from '@/utils/format'

defineProps<{
	parts: { key: string; share: number; class: string; label: string }[]
	compact?: boolean
}>()
</script>
