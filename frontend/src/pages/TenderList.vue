<template>
	<div class="mx-auto max-w-5xl px-6 py-10">
		<div class="mb-8 flex items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-9">{{ t('list.title') }}</h1>
				<p class="mt-1 text-base text-ink-gray-6">{{ t('list.intro') }}</p>
			</div>
			<div class="flex items-center gap-3">
				<LanguageSwitcher />
				<Button variant="solid" icon-left="upload" @click="showNew = true">{{
					t('list.new')
				}}</Button>
			</div>
		</div>

		<div class="overflow-hidden rounded-lg border">
			<table class="w-full text-left text-base">
				<thead class="bg-surface-gray-2 text-sm text-ink-gray-6">
					<tr>
						<th class="px-4 py-2 font-medium">{{ t('list.col.project') }}</th>
						<th class="px-4 py-2 font-medium">{{ t('list.col.trade') }}</th>
						<th class="px-4 py-2 font-medium">{{ t('list.col.status') }}</th>
						<th class="px-4 py-2 text-right font-medium">
							{{ t('list.col.directCost') }}
						</th>
						<th class="px-4 py-2 text-right font-medium">
							{{ t('list.col.baseline') }}
						</th>
						<th class="px-4 py-2 text-right font-medium">{{ t('list.col.open') }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-if="tenders.loading && !tenders.data?.length">
						<td colspan="6" class="px-4 py-6 text-center text-ink-gray-5">
							{{ t('common.loading') }}
						</td>
					</tr>
					<tr v-else-if="!tenders.data?.length">
						<td colspan="6" class="px-4 py-6 text-center text-ink-gray-5">
							{{ t('list.empty') }}
						</td>
					</tr>
					<tr
						v-for="row in tenders.data"
						:key="row.name"
						class="cursor-pointer border-t hover:bg-surface-gray-1"
						@click="open(row.name)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-9">
							{{ row.project_name }}
						</td>
						<td class="px-4 py-3 text-ink-gray-7">{{ tradeLabel(row.trade) }}</td>
						<td class="px-4 py-3">
							<Badge
								:theme="TENDER_STATUS[row.status]?.theme"
								:label="t(`tenderStatus.${row.status}`)"
							/>
						</td>
						<td class="px-4 py-3 text-right tabular-nums">
							{{ formatCHF(row.direct_cost, { digits: 0 }) }}
						</td>
						<td class="px-4 py-3 text-right tabular-nums">
							{{ formatCHF(row.cost_baseline, { digits: 0 }) }}
						</td>
						<td class="px-4 py-3 text-right tabular-nums">
							{{ formatNumber(row.unresolved_count, { maxDigits: 0 }) }}
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<Dialog v-model="showNew" :options="{ title: t('list.new') }">
			<template #body-content>
				<div class="space-y-4">
					<FormControl
						v-model="projectName"
						:label="t('list.dialog.projectName')"
						:placeholder="t('list.dialog.placeholder')"
					/>
					<label class="block text-xs text-ink-gray-5">
						{{ t('list.col.trade') }}
						<select
							v-model="trade"
							class="form-select mt-1 h-8 w-full rounded border-outline-gray-2 py-0 text-sm"
						>
							<option value="">{{ t('list.dialog.tradeAuto') }}</option>
							<option v-for="tr in trades.data || []" :key="tr.name" :value="tr.name">
								{{ tradeLabel(tr.name) }}
							</option>
						</select>
					</label>
					<FileUploader
						file-types=".pdf"
						:upload-args="{ private: true }"
						:validate-file="validatePdf"
						@success="(file) => (uploaded = file)"
					>
						<template #default="{ openFileSelector, uploading, progress, error }">
							<div class="flex items-center gap-3">
								<Button
									:loading="uploading"
									icon-left="file-text"
									@click="openFileSelector"
								>
									{{
										uploading
											? t('list.dialog.uploading', {
													progress: formatPercent(progress / 100, {
														maxDigits: 0,
													}),
												})
											: t('list.dialog.choose')
									}}
								</Button>
								<span v-if="uploaded" class="truncate text-sm text-ink-gray-7">{{
									uploaded.file_name
								}}</span>
							</div>
							<ErrorMessage class="mt-2" :message="error" />
						</template>
					</FileUploader>
					<ErrorMessage :message="createError" />
				</div>
			</template>
			<template #actions>
				<Button
					variant="solid"
					class="w-full"
					:loading="creating"
					:disabled="!projectName || !uploaded"
					@click="create"
				>
					{{ t('list.dialog.submit') }}
				</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import {
	Badge,
	Dialog,
	ErrorMessage,
	FileUploader,
	FormControl,
	createListResource,
} from 'frappe-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { api, errorText } from '@/utils/api'
import { TENDER_STATUS } from '@/utils/codes'
import { formatCHF, formatNumber, formatPercent } from '@/utils/format'
import { tradeLabel, trades } from '@/data/masterData'

const { t } = useI18n()
const router = useRouter()
const showNew = ref(false)
const projectName = ref('')
const uploaded = ref<any>(null)
const creating = ref(false)
const createError = ref('')
const trade = ref('')

const tenders = createListResource({
	doctype: 'Tender',
	fields: [
		'name',
		'project_name',
		'trade',
		'status',
		'direct_cost',
		'cost_baseline',
		'unresolved_count',
		'modified',
	],
	orderBy: 'modified desc',
	pageLength: 50,
	auto: true,
})

function validatePdf(file: File) {
	if (!file.name.toLowerCase().endsWith('.pdf')) return t('list.dialog.notPdf')
	if (file.size > 50 * 1024 * 1024)
		return t('list.dialog.tooLarge', { size: formatNumber(50, { maxDigits: 0 }) })
}

function open(name: string) {
	router.push({ name: 'TenderReview', params: { name } })
}

async function create() {
	creating.value = true
	createError.value = ''
	try {
		const doc = await tenders.insert.submit({
			project_name: projectName.value,
			trade: trade.value,
			tender_file: uploaded.value.file_url,
		})
		await api('equans_bid.api.start_processing', { tender: doc.name })
		showNew.value = false
		open(doc.name)
	} catch (e: any) {
		createError.value = errorText(e, t('list.dialog.createFailed'))
	} finally {
		creating.value = false
	}
}
</script>
