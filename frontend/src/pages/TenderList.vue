<template>
	<div class="h-full overflow-auto">
		<div class="mx-auto max-w-6xl px-6 py-8">
			<!-- Page title and the one main action -->
			<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
				<div>
					<h1 class="text-2xl font-semibold tracking-tight text-ink-gray-9">
						{{ t('list.title') }}
					</h1>
					<p class="mt-1 text-base text-ink-gray-6">{{ t('list.intro') }}</p>
				</div>
				<button
					class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-card hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
					@click="openNew"
				>
					<FeatherIcon name="upload-cloud" class="h-4 w-4" aria-hidden="true" />
					{{ t('list.new') }}
				</button>
			</div>

			<!-- Overview -->
			<div v-if="tenders.data?.length" class="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
				<div
					v-for="s in stats"
					:key="s.key"
					class="rounded-xl bg-surface-white p-4 shadow-card"
				>
					<div class="flex items-center gap-3">
						<span
							class="flex h-9 w-9 items-center justify-center rounded-lg"
							:class="s.iconClass"
							aria-hidden="true"
						>
							<FeatherIcon :name="s.icon" class="h-4 w-4" />
						</span>
						<div>
							<div class="text-sm text-ink-gray-5">{{ s.label }}</div>
							<div class="text-xl font-semibold tabular-nums text-ink-gray-9">
								{{ s.value }}
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- Tenders -->
			<div class="overflow-hidden rounded-xl bg-surface-white shadow-card">
				<div
					v-if="tenders.loading && !tenders.data?.length"
					class="p-10 text-center text-ink-gray-5"
				>
					{{ t('common.loading') }}
				</div>

				<!-- Empty state -->
				<div
					v-else-if="!tenders.data?.length"
					class="flex flex-col items-center px-6 py-16 text-center"
				>
					<span
						class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600"
						aria-hidden="true"
					>
						<FeatherIcon name="file-text" class="h-7 w-7" />
					</span>
					<h2 class="text-lg font-semibold text-ink-gray-9">
						{{ t('list.emptyTitle') }}
					</h2>
					<p class="mt-1 max-w-md text-sm text-ink-gray-6">{{ t('list.empty') }}</p>
					<button
						class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
						@click="openNew"
					>
						<FeatherIcon name="upload-cloud" class="h-4 w-4" aria-hidden="true" />
						{{ t('list.new') }}
					</button>
				</div>

				<table v-else class="w-full text-left text-sm">
					<thead class="border-b text-xs uppercase tracking-wide text-ink-gray-5">
						<tr>
							<th class="px-5 py-3 font-medium">{{ t('list.col.project') }}</th>
							<th class="px-3 py-3 font-medium">{{ t('list.col.status') }}</th>
							<th class="w-56 px-3 py-3 font-medium">{{ t('list.col.progress') }}</th>
							<th class="px-3 py-3 text-right font-medium">
								{{ t('list.col.baseline') }}
							</th>
							<th class="px-3 py-3 text-right font-medium">
								{{ t('list.col.open') }}
							</th>
							<th class="w-10" />
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in tenders.data"
							:key="row.name"
							class="group cursor-pointer border-t first:border-t-0 hover:bg-surface-gray-1"
							tabindex="0"
							@click="open(row.name)"
							@keydown.enter="open(row.name)"
						>
							<td class="px-5 py-4">
								<div class="font-medium text-ink-gray-9">
									{{ row.project_name }}
								</div>
								<div
									class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-gray-5"
								>
									<span
										v-if="row.trade"
										class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-ink-gray-7"
										>{{ tradeLabel(row.trade) }}</span
									>
									<span>{{
										t('list.updated', { date: formatDate(row.modified) })
									}}</span>
								</div>
							</td>
							<td class="px-3 py-4">
								<StatusPill
									:theme="TENDER_STATUS[row.status]?.theme"
									:icon="TENDER_ICON[row.status]"
								>
									{{ t(`tenderStatus.${row.status}`) }}
								</StatusPill>
							</td>
							<td class="px-3 py-4">
								<ProgressBar
									v-if="row.status === 'Completed'"
									:parts="progressParts(row)"
								/>
								<span v-else class="text-xs text-ink-gray-4">{{ MISSING }}</span>
							</td>
							<td
								class="px-3 py-4 text-right font-medium tabular-nums text-ink-gray-9"
							>
								{{ formatCHF(row.cost_baseline, { digits: 0 }) }}
							</td>
							<td class="px-3 py-4 text-right tabular-nums">
								<span
									v-if="row.unresolved_count"
									class="rounded-full bg-surface-red-1 px-2 py-0.5 text-xs font-medium text-ink-red-4"
									>{{
										formatNumber(row.unresolved_count, { maxDigits: 0 })
									}}</span
								>
								<FeatherIcon
									v-else-if="row.status === 'Completed'"
									name="check"
									class="ml-auto h-4 w-4 text-ink-green-3"
									:aria-label="t('list.noOpen')"
								/>
							</td>
							<td class="pr-4 text-ink-gray-4 group-hover:text-ink-gray-7">
								<FeatherIcon
									name="chevron-right"
									class="h-4 w-4"
									aria-hidden="true"
								/>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>

		<!-- New tender: name, trade (usually automatic), PDF by drop or file picker -->
		<Dialog v-model="showNew" :options="{ title: t('list.new') }">
			<template #body-content>
				<div class="space-y-4">
					<FormControl
						v-model="projectName"
						:label="t('list.dialog.projectName')"
						:placeholder="t('list.dialog.placeholder')"
					/>
					<FileUploader
						ref="uploader"
						file-types=".pdf"
						:upload-args="{ private: true }"
						:validate-file="validatePdf"
						@success="(file) => (uploaded = file)"
					>
						<template #default="{ openFileSelector, uploading, progress, error }">
							<div
								role="button"
								tabindex="0"
								class="flex flex-col items-center rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors"
								:class="
									dragging
										? 'border-brand-500 bg-brand-50'
										: uploaded
											? 'border-outline-green-2 bg-surface-green-1'
											: 'border-outline-gray-2 hover:border-brand-400 hover:bg-surface-gray-1'
								"
								@click="openFileSelector"
								@keydown.enter="openFileSelector"
								@dragover.prevent="dragging = true"
								@dragleave.prevent="dragging = false"
								@drop.prevent="onDrop"
							>
								<FeatherIcon
									:name="uploaded ? 'check-circle' : 'upload-cloud'"
									class="mb-2 h-7 w-7"
									:class="uploaded ? 'text-ink-green-3' : 'text-brand-600'"
									aria-hidden="true"
								/>
								<template v-if="uploading">
									<div class="text-sm font-medium text-ink-gray-8">
										{{
											t('list.dialog.uploading', {
												progress: formatPercent(progress / 100, {
													maxDigits: 0,
												}),
											})
										}}
									</div>
									<div
										class="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-surface-gray-3"
									>
										<div
											class="h-full bg-brand-500"
											:style="{ width: `${progress}%` }"
										/>
									</div>
								</template>
								<template v-else-if="uploaded">
									<div class="text-sm font-medium text-ink-gray-9">
										{{ uploaded.file_name }}
									</div>
									<div class="mt-0.5 text-xs text-ink-gray-5">
										{{ t('list.dialog.replace') }}
									</div>
								</template>
								<template v-else>
									<div class="text-sm font-medium text-ink-gray-8">
										{{ t('list.dialog.drop') }}
									</div>
									<div class="mt-0.5 text-xs text-ink-gray-5">
										{{ t('list.dialog.dropHint') }}
									</div>
								</template>
							</div>
							<ErrorMessage class="mt-2" :message="error" />
						</template>
					</FileUploader>
					<details class="text-sm">
						<summary class="cursor-pointer text-ink-gray-6">
							{{ t('list.col.trade') }}:
							{{ trade ? tradeLabel(trade) : t('list.dialog.tradeAuto') }}
						</summary>
						<select
							v-model="trade"
							class="form-select mt-2 h-8 w-full rounded border-outline-gray-2 py-0 text-sm"
							:aria-label="t('list.col.trade')"
						>
							<option value="">{{ t('list.dialog.tradeAuto') }}</option>
							<option v-for="tr in trades.data || []" :key="tr.name" :value="tr.name">
								{{ tradeLabel(tr.name) }}
							</option>
						</select>
					</details>
					<ErrorMessage :message="createError" />
				</div>
			</template>
			<template #actions>
				<button
					class="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
					:disabled="!projectName || !uploaded || creating"
					@click="create"
				>
					<LoadingIndicator v-if="creating" class="h-4 w-4" />
					<FeatherIcon v-else name="zap" class="h-4 w-4" aria-hidden="true" />
					{{ t('list.dialog.submit') }}
				</button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import {
	Dialog,
	ErrorMessage,
	FeatherIcon,
	FileUploader,
	FormControl,
	LoadingIndicator,
	createListResource,
} from 'frappe-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ProgressBar from '@/components/ProgressBar.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api, errorText } from '@/utils/api'
import { TENDER_ICON, TENDER_STATUS } from '@/utils/codes'
import { MISSING, formatCHF, formatDate, formatNumber, formatPercent } from '@/utils/format'
import { tradeLabel, trades } from '@/data/masterData'

const { t } = useI18n()
const router = useRouter()
const showNew = ref(false)
const projectName = ref('')
const uploaded = ref<any>(null)
const creating = ref(false)
const createError = ref('')
const trade = ref('')
const dragging = ref(false)
const uploader = ref<any>(null)

const tenders = createListResource({
	doctype: 'Tender',
	fields: [
		'name',
		'project_name',
		'trade',
		'status',
		'direct_cost',
		'confirmed_cost',
		'provisional_cost',
		'cost_baseline',
		'unresolved_count',
		'modified',
	],
	orderBy: 'modified desc',
	pageLength: 50,
	auto: true,
})

const stats = computed(() => {
	const rows = tenders.data || []
	const open = rows.reduce((s: number, r: any) => s + (r.unresolved_count || 0), 0)
	const baseline = rows.reduce((s: number, r: any) => s + (r.cost_baseline || 0), 0)
	return [
		{
			key: 'tenders',
			icon: 'folder',
			iconClass: 'bg-brand-50 text-brand-700',
			label: t('list.stats.tenders'),
			value: formatNumber(rows.length, { maxDigits: 0 }),
		},
		{
			key: 'open',
			icon: 'alert-triangle',
			iconClass: 'bg-surface-red-1 text-ink-red-4',
			label: t('list.stats.open'),
			value: formatNumber(open, { maxDigits: 0 }),
		},
		{
			key: 'baseline',
			icon: 'bar-chart-2',
			iconClass: 'bg-surface-blue-1 text-ink-blue-3',
			label: t('list.stats.baseline'),
			value: formatCHF(baseline, { digits: 0 }),
		},
	]
})

// Share of the direct cost that is confirmed / provisional (by value); open = not priced.
function progressParts(row: any) {
	const total = row.direct_cost || 0
	const share = (v: number) => (total ? (v || 0) / total : 0)
	return [
		{
			key: 'confirmed',
			share: share(row.confirmed_cost),
			class: 'bg-green-500',
			label: t('kpi.confirmed.label'),
		},
		{
			key: 'provisional',
			share: share(row.provisional_cost),
			class: 'bg-amber-400',
			label: t('kpi.provisional.label'),
		},
	]
}

function openNew() {
	projectName.value = ''
	uploaded.value = null
	createError.value = ''
	trade.value = ''
	showNew.value = true
}

function validatePdf(file: File) {
	if (!file.name.toLowerCase().endsWith('.pdf')) return t('list.dialog.notPdf')
	if (file.size > 50 * 1024 * 1024)
		return t('list.dialog.tooLarge', { size: formatNumber(50, { maxDigits: 0 }) })
}

// A dropped file goes through the same validation and upload as a picked one.
function onDrop(e: DragEvent) {
	dragging.value = false
	const files = e.dataTransfer?.files
	if (files?.length) uploader.value?.onFileAdd({ target: { files } })
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
