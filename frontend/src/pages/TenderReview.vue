<template>
	<div class="flex h-screen flex-col">
		<!-- Header -->
		<header class="flex items-center justify-between gap-4 border-b px-5 py-3">
			<div class="min-w-0">
				<router-link to="/" class="text-sm text-ink-gray-5 hover:text-ink-gray-8"
					>← {{ t('list.title') }}</router-link
				>
				<div class="flex items-center gap-3">
					<h1 class="truncate text-xl font-semibold text-ink-gray-9">
						{{ tender.doc?.project_name || '…' }}
					</h1>
					<Badge
						v-if="tender.doc"
						:theme="TENDER_STATUS[tender.doc.status]?.theme"
						:label="t(`tenderStatus.${tender.doc.status}`)"
					/>
				</div>
				<p v-if="processingText" class="truncate text-sm text-ink-gray-5">
					<span v-if="tender.doc?.trade">{{ tradeLabel(tender.doc.trade) }} · </span
					>{{ processingText }}
					<span v-if="tender.doc?.catalog_priced_at">
						·
						{{
							t('review.pricedAt', { date: formatDate(tender.doc.catalog_priced_at) })
						}}</span
					>
				</p>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<LanguageSwitcher />
				<Button
					icon-left="tag"
					:disabled="!summary.data"
					:loading="refresh.loading"
					@click="previewRefresh"
				>
					{{ t('review.refreshPrices') }}
				</Button>
				<Button icon-left="download" :disabled="!summary.data" @click="exportExcel">{{
					t('review.export')
				}}</Button>
				<Button icon-left="refresh-cw" :loading="reprocessing" @click="reprocess">{{
					t('review.reprocess')
				}}</Button>
			</div>
		</header>

		<!-- Totals -->
		<section
			v-if="summary.data"
			class="grid grid-cols-2 gap-3 border-b px-5 py-3 md:grid-cols-5"
		>
			<div v-for="k in kpis" :key="k.label" class="rounded-lg border px-3 py-2">
				<div class="text-sm text-ink-gray-5">{{ k.label }}</div>
				<div class="text-lg font-semibold tabular-nums" :class="k.tone">{{ k.value }}</div>
				<div v-if="k.hint" class="text-xs text-ink-gray-5">{{ k.hint }}</div>
			</div>
		</section>

		<BidPanel
			v-if="summary.data"
			:summary="summary.data"
			:tender="name"
			@update="(s) => summary.setData(s)"
		/>

		<!-- Subtotals by system -->
		<section v-if="summary.data" class="border-b px-5 py-2">
			<button
				class="text-sm font-medium text-ink-gray-7 hover:text-ink-gray-9"
				@click="showSystems = !showSystems"
			>
				{{ showSystems ? '▾' : '▸' }}
				{{ t('review.bySystem', { count: systemRows.length }) }}
			</button>
			<div
				v-if="showSystems"
				class="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-2 xl:grid-cols-3"
			>
				<button
					v-for="r in systemRows"
					:key="r.system"
					:disabled="!r.key"
					class="flex items-center justify-between gap-3 rounded px-2 py-1 text-left hover:bg-surface-gray-2"
					:class="r.key && systemFilter === r.key ? 'bg-surface-blue-1' : ''"
					@click="systemFilter = systemFilter === r.key ? '' : r.key"
				>
					<span class="truncate text-ink-gray-8">{{ r.system }}</span>
					<span class="shrink-0 tabular-nums text-ink-gray-6">
						{{ t('review.positionsShort', { count: r.positions }) }} ·
						{{ formatCHF(r.direct_cost, { digits: 0 }) }}
					</span>
				</button>
			</div>
		</section>

		<div class="flex min-h-0 flex-1">
			<!-- Positions -->
			<main class="flex min-w-0 flex-[7] flex-col border-r">
				<div class="flex flex-wrap items-center gap-2 border-b px-5 py-2">
					<input
						v-model="search"
						type="search"
						:placeholder="t('review.search')"
						class="form-input h-7 w-64 rounded border-outline-gray-2 text-sm"
					/>
					<select
						v-model="statusFilter"
						class="form-select h-7 rounded border-outline-gray-2 py-0 text-sm"
					>
						<option value="">
							{{ t('review.allStatuses', { count: items.data?.length || 0 }) }}
						</option>
						<option v-for="code in STATUS_CODES" :key="code" :value="code">
							{{ t(`status.${code}`) }} ({{
								summary.data?.by_status?.[code]?.positions || 0
							}})
						</option>
					</select>
					<select
						v-model="systemFilter"
						class="form-select h-7 max-w-xs rounded border-outline-gray-2 py-0 text-sm"
					>
						<option value="">{{ t('review.allSystems') }}</option>
						<option v-for="s in systems" :key="s" :value="s">{{ s }}</option>
					</select>
					<span class="ml-auto text-sm text-ink-gray-5">
						{{ t('review.positions', { count: filtered.length }, filtered.length) }} ·
						{{ formatCHF(filteredTotal, { digits: 0 }) }}
					</span>
				</div>

				<div class="min-h-0 flex-1 overflow-auto">
					<table class="w-full text-left text-sm">
						<thead class="sticky top-0 z-10 bg-surface-gray-2 text-ink-gray-6">
							<tr>
								<th class="px-3 py-2 font-medium">{{ t('review.col.lvId') }}</th>
								<th class="px-3 py-2 font-medium">
									{{ t('review.col.description') }}
								</th>
								<th class="px-3 py-2 text-right font-medium">
									{{ t('review.col.quantity') }}
								</th>
								<th class="px-3 py-2 font-medium">{{ t('review.col.unit') }}</th>
								<th class="px-3 py-2 font-medium">{{ t('review.col.product') }}</th>
								<th class="px-3 py-2 text-right font-medium">
									{{ t('review.col.directCost') }}
								</th>
								<th class="px-3 py-2 font-medium">{{ t('review.col.status') }}</th>
								<th class="px-3 py-2 font-medium">{{ t('review.col.source') }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-if="items.loading && !items.data?.length">
								<td colspan="8" class="px-3 py-6 text-center text-ink-gray-5">
									{{ t('review.loadingPositions') }}
								</td>
							</tr>
							<tr
								v-for="row in filtered"
								:key="row.name"
								class="cursor-pointer border-t align-top"
								:class="
									row.name === selected?.name
										? 'bg-surface-blue-1'
										: 'hover:bg-surface-gray-1'
								"
								@click="select(row)"
							>
								<td class="whitespace-nowrap px-3 py-2 font-mono text-xs">
									<div>{{ row.position_id }}</div>
									<div
										v-if="row.golden_lv_id"
										class="text-ink-green-3"
										:title="t('review.verifiedReference')"
									>
										{{ row.golden_lv_id }} ✓
									</div>
								</td>
								<td class="px-3 py-2">
									<div class="line-clamp-2 text-ink-gray-9">
										{{ row.description }}
									</div>
									<div class="truncate text-xs text-ink-gray-5">
										{{ row.system }}
									</div>
								</td>
								<td class="whitespace-nowrap px-3 py-2 text-right tabular-nums">
									{{ formatQuantity(row.quantity) }}
								</td>
								<td class="px-3 py-2">{{ unitLabel(row.unit) }}</td>
								<td class="whitespace-nowrap px-3 py-2 font-mono text-xs">
									{{ row.matched_product || MISSING }}
								</td>
								<td
									class="whitespace-nowrap px-3 py-2 text-right tabular-nums"
									@click.stop
								>
									<template v-if="row.status === 'supplier_quote_required'">
										<input
											type="number"
											min="0"
											step="0.01"
											:value="row.quote_override || ''"
											:placeholder="
												t('review.quotePlaceholder', {
													amount: formatNumber(row.material_cost, {
														maxDigits: 0,
													}),
												})
											"
											:title="t('review.quoteTitle')"
											class="form-input h-7 w-32 rounded border-outline-amber-2 text-right text-sm"
											@change="
												(e) =>
													saveQuote(
														row,
														(e.target as HTMLInputElement).value,
													)
											"
											@focus="select(row)"
										/>
										<div
											class="mt-0.5 text-xs"
											:class="
												row.quote_override
													? 'text-ink-green-3'
													: 'text-ink-amber-3'
											"
										>
											{{ formatCHF(row.direct_cost) }} ·
											{{
												row.quote_override
													? t('review.quoted')
													: t('review.provisional')
											}}
										</div>
									</template>
									<template v-else-if="STATUS[row.status]?.priced">{{
										formatCHF(row.direct_cost)
									}}</template>
									<span
										v-else
										class="text-ink-gray-4"
										:title="t('review.noPriceYet')"
										>{{ MISSING }}</span
									>
								</td>
								<td class="px-3 py-2">
									<Badge
										:theme="STATUS[row.status]?.theme"
										:label="statusLabel(row.status)"
									/>
								</td>
								<td class="whitespace-nowrap px-3 py-2 text-ink-blue-3">
									{{ t('review.page', { page: row.source_page }) }}
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</main>

			<!-- Traceability -->
			<aside class="flex min-w-[360px] flex-[3] flex-col">
				<div class="border-b px-4 py-2">
					<h2 class="text-base font-semibold text-ink-gray-9">
						{{ t('review.traceability') }}
					</h2>
				</div>

				<div v-if="selected" class="max-h-[45%] overflow-auto border-b px-4 py-3 text-sm">
					<div class="mb-2 flex items-start justify-between gap-2">
						<div>
							<div class="font-mono text-xs text-ink-gray-5">
								{{ selected.position_id
								}}<span v-if="selected.golden_lv_id">
									· {{ selected.golden_lv_id }}</span
								>
							</div>
							<div class="font-medium text-ink-gray-9">
								{{ selected.description }}
							</div>
						</div>
						<Badge
							:theme="STATUS[selected.status]?.theme"
							:label="statusLabel(selected.status)"
						/>
					</div>
					<p class="mb-3 rounded bg-surface-gray-2 px-2 py-1.5 text-ink-gray-7">
						{{
							reasonText(
								t,
								selected.reason_code,
								selected.reason_args,
								selected.status_reason,
								familyLabel,
							)
						}}
					</p>
					<p
						v-if="attrs.system_conflict"
						class="mb-3 rounded bg-surface-amber-1 px-2 py-1.5 text-ink-amber-3"
					>
						{{ t('review.documentConflict') }}: {{ conflictText }}
					</p>
					<p
						v-if="selected.error"
						class="mb-3 rounded bg-surface-red-1 px-2 py-1.5 text-ink-red-4"
					>
						{{ t('review.technicalError') }}: {{ selected.error }}
					</p>

					<dl class="grid grid-cols-2 gap-x-3 gap-y-1">
						<template v-if="selected.family">
							<dt class="text-ink-gray-5">{{ t('review.family') }}</dt>
							<dd>{{ familyLabel(selected.family) }}</dd>
						</template>
						<template v-if="selected.position_ref">
							<dt class="text-ink-gray-5">{{ t('review.positionRef') }}</dt>
							<dd class="font-mono text-xs">{{ selected.position_ref }}</dd>
						</template>
						<dt class="text-ink-gray-5">{{ t('review.col.quantity') }}</dt>
						<dd class="tabular-nums">
							{{ formatQuantity(selected.quantity) }} {{ unitLabel(selected.unit) }}
						</dd>
						<dt class="text-ink-gray-5">{{ t('review.confidence') }}</dt>
						<dd class="tabular-nums">
							{{ formatPercent(selected.extraction_confidence, { maxDigits: 0 }) }} /
							{{ formatPercent(selected.match_confidence, { maxDigits: 0 }) }}
						</dd>
						<template v-if="STATUS[selected.status]?.priced">
							<dt class="text-ink-gray-5">{{ t('review.material') }}</dt>
							<dd class="tabular-nums">
								{{ formatCHF(selected.material_cost) }}
								<span
									class="text-xs text-ink-gray-5"
									v-if="!selected.quote_override"
								>
									({{
										t('review.materialFormula', {
											quantity: formatQuantity(selected.quantity),
											price: formatCHF(selected.net_unit_cost),
											waste: formatPercent(wasteFraction),
										})
									}})
								</span>
								<span class="text-xs text-ink-green-3" v-else
									>({{ t('review.quoted') }})</span
								>
							</dd>
							<dt class="text-ink-gray-5">{{ t('review.labour') }}</dt>
							<dd class="tabular-nums">
								{{ formatCHF(selected.labour_cost) }}
								<span class="text-xs text-ink-gray-5">
									({{
										t('review.labourFormula', {
											hours: formatNumber(selected.labour_hours, {
												maxDigits: 2,
											}),
											rate: formatCHF(selected.labour_rate, { digits: 0 }),
										})
									}})
								</span>
							</dd>
							<dt class="font-medium text-ink-gray-7">
								{{ t('review.col.directCost') }}
							</dt>
							<dd class="font-semibold tabular-nums">
								{{ formatCHF(selected.direct_cost) }}
							</dd>
						</template>
					</dl>

					<!-- Project columns exactly as printed in the tender (source evidence, never translated). -->
					<div class="mt-3">
						<div class="mb-1 text-xs font-medium text-ink-gray-5">
							{{ t('review.customAttributes') }}
						</div>
						<table v-if="customRows.length" class="w-full text-xs">
							<tr
								v-for="[label, value] in customRows"
								:key="label"
								class="border-t first:border-t-0"
							>
								<td class="w-1/3 py-0.5 pr-2 text-ink-gray-5">{{ label }}</td>
								<td class="py-0.5 text-ink-gray-8">{{ value }}</td>
							</tr>
						</table>
						<p v-else class="text-xs text-ink-gray-4">
							{{ t('review.noCustomAttributes') }}
						</p>
					</div>

					<!-- What the LLM answered (model text is English and shown as returned). -->
					<div v-if="llmAnswer" class="mt-3 rounded bg-surface-gray-1 p-2 text-xs">
						<div class="mb-0.5 font-medium text-ink-gray-5">
							{{ t('review.llmAnswer', { by: t(`review.matchedBy.${matchedBy}`) }) }}
						</div>
						<div class="text-ink-gray-8">
							{{ llmAnswer.product_id || t('review.llmNoProduct') }}
							<span class="text-ink-gray-5"
								>({{ t(`review.fit.${llmAnswer.fit}`) }})</span
							>
						</div>
						<div v-if="llmAnswer.note" class="italic text-ink-gray-6" lang="en">
							{{ llmAnswer.note }}
						</div>
					</div>

					<div class="mt-3 grid grid-cols-2 gap-2">
						<label class="text-xs text-ink-gray-5">
							{{ t('review.col.product') }}
							<select
								class="form-select mt-0.5 h-7 w-full rounded border-outline-gray-2 py-0 text-sm"
								:value="selected.matched_product || ''"
								@change="
									(e) =>
										saveProduct(selected, (e.target as HTMLSelectElement).value)
								"
							>
								<option value="" disabled>{{ t('common.choose') }}</option>
								<option v-for="p in catalog.data" :key="p.name" :value="p.name">
									{{ p.name }} · {{ p.description }}
								</option>
							</select>
						</label>
						<label class="text-xs text-ink-gray-5">
							{{ t('review.col.status') }}
							<select
								class="form-select mt-0.5 h-7 w-full rounded border-outline-gray-2 py-0 text-sm"
								:value="selected.status"
								@change="
									(e) =>
										saveStatus(selected, (e.target as HTMLSelectElement).value)
								"
							>
								<option v-for="code in STATUS_CODES" :key="code" :value="code">
									{{ statusLabel(code) }}
								</option>
							</select>
						</label>
					</div>
					<p v-if="lastSave" class="mt-2 text-xs text-ink-gray-5">{{ lastSave }}</p>
					<ErrorMessage class="mt-2" :message="saveError" />
				</div>
				<div v-else class="border-b px-4 py-3 text-sm text-ink-gray-5">
					{{ t('review.selectHint') }}
				</div>

				<div class="min-h-0 flex-1">
					<PdfViewer
						v-if="pdfUrl"
						:url="pdfUrl"
						:file-name="fileName"
						:evidence="evidence"
						v-model:page="activePage"
					/>
				</div>
			</aside>
		</div>
		<Dialog v-model="refresh.open" :options="{ title: t('review.refreshTitle') }">
			<template #body-content>
				<p v-if="!refresh.diff?.changes?.length" class="text-sm text-ink-gray-7">
					{{ t('review.refreshNone') }}
				</p>
				<template v-else>
					<p class="mb-2 text-sm text-ink-gray-8">
						{{
							t('review.refreshSummary', {
								count: refresh.diff.changes.length,
								before: formatCHF(refresh.diff.total_before, { digits: 0 }),
								after: formatCHF(refresh.diff.total_after, { digits: 0 }),
							})
						}}
					</p>
					<table class="w-full text-sm">
						<tr
							v-for="c in refresh.diff.changes.slice(0, 12)"
							:key="c.item"
							class="border-t"
						>
							<td class="py-1 font-mono text-xs">{{ c.position_id }}</td>
							<td class="py-1 text-right tabular-nums">{{ formatCHF(c.before) }}</td>
							<td class="py-1 text-right tabular-nums">→ {{ formatCHF(c.after) }}</td>
						</tr>
					</table>
				</template>
				<ErrorMessage class="mt-2" :message="refresh.error" />
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button @click="refresh.open = false">{{ t('review.refreshCancel') }}</Button>
					<Button
						variant="solid"
						:loading="refresh.loading"
						:disabled="!refresh.diff?.changes?.length"
						@click="applyRefresh"
					>
						{{ t('review.refreshApply') }}
					</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import {
	Badge,
	Dialog,
	ErrorMessage,
	createDocumentResource,
	createListResource,
	createResource,
} from 'frappe-ui'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BidPanel from '@/components/BidPanel.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import PdfViewer from '@/components/PdfViewer.vue'
import { currentLocale } from '@/i18n'
import { api, errorText } from '@/utils/api'
import { STATUS, STATUS_CODES, TENDER_STATUS, UNIT_CODES } from '@/utils/codes'
import {
	MISSING,
	formatCHF,
	formatDate,
	formatNumber,
	formatPercent,
	formatQuantity,
} from '@/utils/format'
import { reasonText, warningText } from '@/utils/reasons'
import { familyLabel, tradeLabel } from '@/data/masterData'

const { t } = useI18n()
// Codes stay codes; unknown ones are shown as they are rather than hidden.
const statusLabel = (code: string) => (STATUS_CODES.includes(code) ? t(`status.${code}`) : code)
const unitLabel = (code: string) => (UNIT_CODES.includes(code) ? t(`unit.${code}`) : code || '')

const props = defineProps<{ name: string }>()

const tender = createDocumentResource({ doctype: 'Tender', name: props.name, auto: true })

const summary = createResource({
	url: 'equans_bid.api.get_tender_summary',
	params: { tender: props.name },
	auto: true,
})

const ITEM_FIELDS = [
	'name',
	'idx',
	'position_id',
	'golden_lv_id',
	'system',
	'source_page',
	'description',
	'description_original',
	'quantity_raw',
	'unit_raw',
	'quantity',
	'unit',
	'matched_product',
	'match_confidence',
	'extraction_confidence',
	'net_unit_cost',
	'quote_override',
	'material_cost',
	'labour_hours',
	'labour_rate',
	'labour_cost',
	'direct_cost',
	'status',
	'status_reason',
	'reason_code',
	'reason_args',
	'error',
	'attributes',
	'custom_attributes',
	'family',
	'position_ref',
	'price_version',
]

const items = createListResource({
	doctype: 'Tender Item',
	parent: 'Tender',
	fields: ITEM_FIELDS,
	filters: { parent: props.name, parenttype: 'Tender' },
	orderBy: 'idx asc',
	pageLength: 5000,
	auto: true,
})

const catalog = createListResource({
	doctype: 'Catalog Item',
	fields: ['name', 'description'],
	orderBy: 'name asc',
	pageLength: 500,
	auto: true,
})

// Filters
const search = ref('')
const statusFilter = ref('')
const systemFilter = ref('')
const systems = computed(() =>
	[...new Set((items.data || []).map((i: any) => i.system).filter(Boolean))].sort(),
)
const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	return (items.data || []).filter((i: any) => {
		if (statusFilter.value && i.status !== statusFilter.value) return false
		if (systemFilter.value && i.system !== systemFilter.value) return false
		if (!q) return true
		return [i.description, i.matched_product, i.position_id, i.golden_lv_id].some((v) =>
			v?.toLowerCase().includes(q),
		)
	})
})
const filteredTotal = computed(() =>
	filtered.value.reduce((s: number, i: any) => s + (i.direct_cost || 0), 0),
)

// Totals
const kpis = computed(() => {
	const s = summary.data
	if (!s) return []
	const totals = s.totals
	const c = { digits: 0 }
	return [
		{ key: 'direct', value: formatCHF(totals.direct_cost, c) },
		{ key: 'confirmed', value: formatCHF(totals.confirmed_cost, c), tone: 'text-ink-green-3' },
		{
			key: 'provisional',
			value: formatCHF(totals.provisional_cost, c),
			tone: 'text-ink-amber-3',
		},
		{
			key: 'open',
			value: formatNumber(totals.unresolved_count, { maxDigits: 0 }),
			tone: 'text-ink-red-4',
		},
		{ key: 'baseline', value: formatCHF(s.build_up.cost_baseline, c) },
	].map((k) => ({ ...k, label: t(`kpi.${k.key}.label`), hint: t(`kpi.${k.key}.hint`) }))
})

// Subtotals by system, largest first (from the backend summary).
const showSystems = ref(false)
const systemRows = computed(() =>
	Object.entries(summary.data?.by_system || {})
		.map(([key, v]: [string, any]) => ({
			key: key === '-' ? '' : key,
			system: key === '-' ? t('review.noSystem') : key,
			...v,
		}))
		.sort((a, b) => b.direct_cost - a.direct_cost),
)

// Selection and traceability
const selected = ref<any>(null)
const activePage = ref(1)
function select(row: any) {
	selected.value = row
	activePage.value = row.source_page
}

const pdfUrl = computed(() =>
	tender.doc
		? `/api/method/equans_bid.api.get_tender_pdf?tender=${encodeURIComponent(props.name)}`
		: '',
)
const fileName = computed(() =>
	(tender.doc?.tender_file || 'BKP_244_LV_Lueftung_260804.pdf').split('/').pop(),
)

// Parsed attributes (kind, sizes, document warnings) stored as JSON on the row.
const attrs = computed(() => {
	const a = selected.value?.attributes
	if (!a) return {}
	try {
		return typeof a === 'string' ? JSON.parse(a) : a
	} catch {
		return {}
	}
})

// Material waste as applied by the backend (material / (qty x net) - 1), shown in the breakdown.
const wasteFraction = computed(() => {
	const s = selected.value
	const base = (s?.quantity || 0) * (s?.net_unit_cost || 0)
	return base ? Math.round((s.material_cost / base - 1) * 1000) / 1000 : 0
})

const conflictText = computed(() => {
	const c = attrs.value.system_conflict
	return c && typeof c === 'object' ? warningText(t, 'header_conflict', c) : c || ''
})

// Processing summary from structured info (translated); the raw log only as a fallback.
const processingText = computed(() => {
	const doc = tender.doc
	if (!doc) return ''
	let info: any = doc.processing_info
	try {
		info = typeof info === 'string' ? JSON.parse(info) : info
	} catch {
		info = null
	}
	if (!info || doc.status === 'Failed') return doc.processing_log || ''
	const llm = info.llm ? t('review.llmUsed', { provider: '—', ...info.llm }) : t('review.llmNone')
	return `${t(
		'review.processed',
		{ count: info.positions, file: info.file },
		info.positions,
	)} ${llm}`
})

// Lines to highlight: the quantity line for LV positions, the table rows for component lists.
const evidence = computed(() => {
	const s = selected.value
	if (!s || activePage.value !== s.source_page) return []
	// Table rows store the lines they were read from (attributes.evidence_lines).
	if (attrs.value.source_kind === 'table' && attrs.value.evidence_lines?.length)
		return attrs.value.evidence_lines
	const lines = (s.description_original || '').split('\n').filter(Boolean)
	const label = lines.length ? lines[lines.length - 1] : ''
	const qtyLine = s.quantity_raw ? `${s.unit_raw} ${s.quantity_raw}` : s.unit_raw
	return [`${label} ${qtyLine}`.trim()]
})

// Edits: one call reprices the row and returns the new totals; the row is patched in place.
const saveError = ref('')
const lastSave = ref('')
async function update(row: any, args: Record<string, any>) {
	saveError.value = ''
	const started = performance.now()
	try {
		const res = await api('equans_bid.api.update_item', {
			tender: props.name,
			item: row.name,
			...args,
		})
		for (const f of ITEM_FIELDS) if (f in res.item) row[f] = res.item[f]
		summary.setData(res.summary)
		lastSave.value = t('review.saved', {
			ms: formatNumber(Math.round(performance.now() - started), { maxDigits: 0 }),
		})
	} catch (e: any) {
		saveError.value = errorText(e, t('common.saveFailed'))
	}
}
const saveQuote = (row: any, value: string) =>
	update(row, { quote_override: value === '' ? 0 : Number(value) })
const saveProduct = (row: any, product: string) =>
	product && update(row, { matched_product: product })
const saveStatus = (row: any, status: string) => update(row, { status })

function exportExcel() {
	const q = new URLSearchParams({ tender: props.name, lang: currentLocale() })
	window.location.href = `/api/method/equans_bid.api.export_tender?${q}`
}

const llmAnswer = computed(() => attrs.value.llm || null)
const matchedBy = computed(() => attrs.value.matched_by || 'rules')

const customRows = computed(() => {
	const raw = selected.value?.custom_attributes
	try {
		return Object.entries(typeof raw === 'string' ? JSON.parse(raw) : raw || {})
	} catch {
		return []
	}
})

// Price refresh: show what today's catalogue would change, apply only on confirmation.
const refresh = reactive({ loading: false, open: false, diff: null as any, error: '' })
async function previewRefresh() {
	refresh.loading = true
	refresh.error = ''
	try {
		refresh.diff = await api('equans_bid.api.preview_price_refresh', { tender: props.name })
		refresh.open = true
	} catch (e: any) {
		refresh.error = errorText(e, t('common.saveFailed'))
	} finally {
		refresh.loading = false
	}
}
async function applyRefresh() {
	refresh.loading = true
	try {
		const res = await api('equans_bid.api.apply_price_refresh', { tender: props.name })
		summary.setData(res.summary)
		refresh.open = false
		await Promise.all([items.reload(), tender.reload()])
	} catch (e: any) {
		refresh.error = errorText(e, t('common.saveFailed'))
	} finally {
		refresh.loading = false
	}
}

// Background processing: poll until the job finishes, then load the positions.
const reprocessing = ref(false)
let timer: ReturnType<typeof setInterval> | null = null
function poll() {
	if (timer) return
	timer = setInterval(async () => {
		await tender.reload()
		if (tender.doc?.status !== 'Processing') {
			clearInterval(timer!)
			timer = null
			reprocessing.value = false
			selected.value = null
			items.reload()
			summary.reload()
		}
	}, 2000)
}
watch(
	() => tender.doc?.status,
	(s) => s === 'Processing' && poll(),
	{ immediate: true },
)

async function reprocess() {
	reprocessing.value = true
	await api('equans_bid.api.start_processing', { tender: props.name })
	await tender.reload()
	poll()
}
onBeforeUnmount(() => timer && clearInterval(timer))
</script>
