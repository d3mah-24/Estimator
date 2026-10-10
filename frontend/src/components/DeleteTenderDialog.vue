<template>
	<!-- Confirm before deleting: names the tender and says what goes with it. -->
	<Dialog v-model="open" :options="{ title: t('delete.title') }">
		<template #body-content>
			<div class="flex gap-3">
				<span
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600"
					aria-hidden="true"
				>
					<FeatherIcon name="trash-2" class="h-5 w-5" />
				</span>
				<div class="text-sm text-ink-gray-7">
					<p>
						{{ t('delete.question') }}
						<span class="font-semibold text-ink-gray-9">{{
							tender?.project_name
						}}</span>
					</p>
					<p class="mt-1 text-ink-gray-5">{{ t('delete.consequence') }}</p>
				</div>
			</div>
			<ErrorMessage class="mt-3" :message="error" />
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button :disabled="deleting" @click="open = false">{{ t('delete.cancel') }}</Button>
				<button
					class="inline-flex h-7 items-center gap-1.5 rounded bg-red-600 px-3 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
					:disabled="deleting"
					@click="confirm"
				>
					<LoadingIndicator v-if="deleting" class="h-4 w-4" />
					<FeatherIcon v-else name="trash-2" class="h-4 w-4" aria-hidden="true" />
					{{ t('delete.confirm') }}
				</button>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { Dialog, ErrorMessage, FeatherIcon, LoadingIndicator } from 'frappe-ui'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorText } from '@/utils/api'

const { t } = useI18n()
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ tender: { name: string; project_name: string } | null }>()
const emit = defineEmits<{ (e: 'deleted', name: string): void }>()

const deleting = ref(false)
const error = ref('')
watch(open, (o) => o && (error.value = ''))

async function confirm() {
	if (!props.tender) return
	deleting.value = true
	error.value = ''
	try {
		await api('equans_bid.api.delete_tender', { tender: props.tender.name })
		open.value = false
		emit('deleted', props.tender.name)
	} catch (e: any) {
		error.value = errorText(e, t('delete.failed'))
	} finally {
		deleting.value = false
	}
}
</script>
