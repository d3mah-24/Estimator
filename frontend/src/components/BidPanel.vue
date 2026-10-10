<template>
	<div class="mx-auto max-w-7xl px-6 py-5">
		<!-- The bid the estimator chose (saved per tender, exported to Excel) -->
		<div
			class="mb-5 flex flex-wrap items-center gap-3 rounded-xl px-4 py-3"
			:class="
				shown.selected_bid
					? 'bg-brand-600 text-white'
					: 'border border-dashed border-outline-gray-3 bg-surface-white text-ink-gray-7'
			"
		>
			<FeatherIcon
				:name="shown.selected_bid ? 'award' : 'target'"
				class="h-5 w-5 shrink-0"
				:class="shown.selected_bid ? 'text-white' : 'text-brand-600'"
				aria-hidden="true"
			/>
			<div class="min-w-0 flex-1 text-sm">
				<template v-if="shown.selected_bid">
					<span class="font-semibold">{{
						t('bid.selectedLine', {
							price: formatCHF(shown.selected_bid.bid_price_chf, { digits: 0 }),
							scenario: t(`scenario.${shown.selected_bid.scenario}`),
							margin: formatPercent(shown.selected_bid.margin_pct / 100),
						})
					}}</span>
					<span
						v-if="shown.selected_bid.below_baseline"
						class="ml-2 rounded bg-white/20 px-1.5 py-0.5 font-medium"
						>{{ t('bid.own.belowBaseline') }}</span
					>
				</template>
				<template v-else>{{
					t('bid.noneSelected', { scenario: t(`scenario.${recommendedName}`) })
				}}</template>
			</div>
			<button
				v-if="shown.selected_bid"
				class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-white/90 hover:bg-white/10"
				:disabled="!!selecting"
				@click="select(null)"
			>
				<FeatherIcon name="x" class="h-4 w-4" aria-hidden="true" />
				{{ t('bid.clearSelection') }}
			</button>
		</div>
		<ErrorMessage v-if="selectError" class="mb-3" :message="selectError" />

		<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
			<!-- Scenarios and own offer -->
			<div class="xl:col-span-2">
				<div class="mb-2 flex flex-wrap items-baseline gap-2">
					<h2 class="text-base font-semibold text-ink-gray-9">{{ t('bid.title') }}</h2>
					<span class="text-xs text-ink-gray-5">{{ t('bid.modelNote') }}</span>
					<span
						v-if="isCustom"
						class="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700"
						>{{ t('bid.custom') }}</span
					>
				</div>
				<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
					<div
						v-for="s in shown.bid_range"
						:key="s.scenario"
						class="flex flex-col rounded-xl bg-surface-white p-4 shadow-card ring-1 transition-shadow"
						:class="
							s.selected
								? 'ring-2 ring-brand-500'
								: s.recommended
									? 'ring-green-300'
									: 'ring-outline-gray-1'
						"
					>
						<div class="flex items-center justify-between gap-2">
							<span class="text-sm font-semibold text-ink-gray-8">{{
								t(`scenario.${s.scenario}`)
							}}</span>
							<StatusPill v-if="s.selected" theme="blue" icon="check">{{
								t('bid.selected')
							}}</StatusPill>
							<StatusPill v-else-if="s.recommended" theme="green" icon="star">{{
								t('bid.recommended')
							}}</StatusPill>
						</div>
						<div
							class="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-ink-gray-9"
						>
							{{ formatCHF(s.bid_price_chf, { digits: 0 }) }}
						</div>
						<div class="mt-1 text-sm text-ink-gray-6">
							{{ t('bid.margin') }}
							<span class="font-medium tabular-nums text-ink-gray-8">{{
								formatPercent(s.margin_pct / 100)
							}}</span>
						</div>
						<div class="mt-3">
							<div class="flex justify-between text-xs text-ink-gray-5">
								<span>{{ t('bid.winProbability') }}</span>
								<span class="font-medium tabular-nums text-ink-gray-8">{{
									formatPercent(s.estimated_win_probability, { maxDigits: 0 })
								}}</span>
							</div>
							<div class="mt-1 h-2 overflow-hidden rounded-full bg-surface-gray-3">
								<div
									class="h-full rounded-full"
									:class="s.recommended ? 'bg-green-500' : 'bg-brand-500'"
									:style="{ width: `${s.estimated_win_probability * 100}%` }"
								/>
							</div>
						</div>
						<dl class="mt-3 grid grid-cols-2 gap-y-1 text-xs">
							<dt class="text-ink-gray-5">{{ t('bid.contributionIfWon') }}</dt>
							<dd class="text-right tabular-nums text-ink-gray-8">
								{{ formatCHF(s.contribution_if_won_chf, { digits: 0 }) }}
							</dd>
							<dt class="text-ink-gray-5">{{ t('bid.expectedContribution') }}</dt>
							<dd class="text-right font-semibold tabular-nums text-ink-gray-9">
								{{ formatCHF(s.expected_contribution_chf, { digits: 0 }) }}
							</dd>
						</dl>
						<button
							class="mt-4 inline-flex h-8 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors disabled:cursor-not-allowed"
							:class="
								s.selected
									? 'bg-brand-50 text-brand-700'
									: 'bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50'
							"
							:disabled="s.selected || dirty || !!selecting"
							@click="select({ scenario: s.scenario })"
						>
							<FeatherIcon
								:name="s.selected ? 'check' : 'mouse-pointer'"
								class="h-4 w-4"
								aria-hidden="true"
							/>
							{{ s.selected ? t('bid.selected') : t('bid.select') }}
						</button>
					</div>

					<!-- Own offer: a margin or a fixed price chosen by the estimator -->
					<div
						class="flex flex-col rounded-xl bg-surface-white p-4 shadow-card ring-1"
						:class="ownSelected ? 'ring-2 ring-brand-500' : 'ring-outline-gray-1'"
					>
						<div class="flex items-center justify-between gap-2">
							<span class="text-sm font-semibold text-ink-gray-8">{{
								t('scenario.custom')
							}}</span>
							<StatusPill v-if="ownSelected" theme="blue" icon="check">{{
								t('bid.selected')
							}}</StatusPill>
						</div>
						<template v-if="ownSelected">
							<div
								class="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-ink-gray-9"
							>
								{{ formatCHF(shown.selected_bid.bid_price_chf, { digits: 0 }) }}
							</div>
							<dl class="mt-2 grid grid-cols-2 gap-y-1 text-xs">
								<dt class="text-ink-gray-5">{{ t('bid.margin') }}</dt>
								<dd
									class="text-right tabular-nums"
									:class="
										shown.selected_bid.below_baseline
											? 'text-red-600'
											: 'text-ink-gray-8'
									"
								>
									{{ formatPercent(shown.selected_bid.margin_pct / 100) }}
								</dd>
								<dt class="text-ink-gray-5">{{ t('bid.winProbability') }}</dt>
								<dd class="text-right tabular-nums text-ink-gray-8">
									{{
										formatPercent(
											shown.selected_bid.estimated_win_probability,
											{ maxDigits: 0 },
										)
									}}
								</dd>
								<dt class="text-ink-gray-5">{{ t('bid.expectedContribution') }}</dt>
								<dd class="text-right font-semibold tabular-nums text-ink-gray-9">
									{{
										formatCHF(shown.selected_bid.expected_contribution_chf, {
											digits: 0,
										})
									}}
								</dd>
							</dl>
						</template>
						<p v-else class="mt-1 text-sm text-ink-gray-5">{{ t('bid.own.hint') }}</p>
						<div class="mt-auto pt-4">
							<div
								class="flex rounded-lg bg-surface-gray-2 p-0.5 text-xs"
								role="radiogroup"
								:aria-label="t('bid.own.mode')"
							>
								<button
									v-for="m in OWN_MODES"
									:key="m.mode"
									role="radio"
									:aria-checked="own.mode === m.mode"
									class="flex-1 rounded-md px-2 py-1 font-medium"
									:class="
										own.mode === m.mode
											? 'bg-surface-white text-ink-gray-9 shadow-sm'
											: 'text-ink-gray-6'
									"
									@click="own.mode = m.mode"
								>
									{{ t(m.label) }}
								</button>
							</div>
							<input
								v-model.number="own.value"
								type="number"
								:step="own.mode === 'margin_pct' ? 0.5 : 1000"
								:min="own.mode === 'margin_pct' ? 0 : 1"
								:max="own.mode === 'margin_pct' ? 30 : undefined"
								class="form-input mt-2 h-8 w-full rounded-lg border-outline-gray-2 text-sm"
								:aria-label="
									own.mode === 'margin_pct'
										? t('bid.own.margin')
										: t('bid.own.price')
								"
								:placeholder="own.mode === 'margin_pct' ? '5' : '450000'"
								@keydown.enter="selectOwn"
							/>
							<button
								class="mt-2 inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-brand-600 text-sm font-medium text-brand-700 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50"
								:disabled="!ownValid || dirty || !!selecting"
								@click="selectOwn"
							>
								<FeatherIcon name="edit-3" class="h-4 w-4" aria-hidden="true" />
								{{ ownSelected ? t('bid.own.update') : t('bid.select') }}
							</button>
						</div>
					</div>
				</div>

				<!-- Standard offer: the reference the win probability is measured against -->
				<div
					class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-dashed bg-surface-white px-4 py-3 text-sm"
				>
					<span class="font-medium text-ink-gray-7">{{ t('bid.standardOffer') }}</span>
					<span class="font-semibold tabular-nums text-ink-gray-9">{{
						formatCHF(shown.indicative_price.bid_price_chf, { digits: 0 })
					}}</span>
					<span class="text-xs text-ink-gray-5">{{
						t('bid.standardOfferFormula', {
							baseline: formatCHF(shown.build_up.cost_baseline, { digits: 0 }),
							margin: formatPercent(shown.indicative_price.margin_pct / 100),
							step: formatCHF(1000, { digits: 0 }),
						})
					}}</span>
					<span
						v-if="shown.totals.unresolved_count"
						class="inline-flex items-center gap-1 text-xs text-red-600"
					>
						<FeatherIcon name="alert-triangle" class="h-3.5 w-3.5" aria-hidden="true" />
						{{
							t(
								'bid.unpricedExcluded',
								{ count: shown.totals.unresolved_count },
								shown.totals.unresolved_count,
							)
						}}
					</span>
				</div>
			</div>

			<!-- Right column: how the price is built and what it assumes -->
			<div class="space-y-5">
				<section class="rounded-xl bg-surface-white p-4 shadow-card">
					<h2
						class="mb-3 flex items-center gap-2 text-base font-semibold text-ink-gray-9"
					>
						<FeatherIcon
							name="layers"
							class="h-4 w-4 text-ink-gray-5"
							aria-hidden="true"
						/>
						{{ t('bid.buildUp') }}
					</h2>
					<table class="w-full text-sm">
						<tbody>
							<tr
								v-for="line in buildUp"
								:key="line.key"
								:class="line.total ? 'border-t font-semibold' : ''"
							>
								<td
									class="py-1.5 pr-2"
									:class="line.total ? 'text-ink-gray-9' : 'text-ink-gray-7'"
								>
									{{ line.label }}
									<div
										v-if="line.note"
										class="text-xs font-normal text-ink-gray-5"
									>
										{{ line.note }}
									</div>
								</td>
								<td
									class="py-1.5 text-right align-top tabular-nums"
									:class="line.total ? 'text-ink-gray-9' : 'text-ink-gray-8'"
								>
									{{ formatCHF(shown.build_up[line.key], { digits: 0 }) }}
								</td>
							</tr>
						</tbody>
					</table>
				</section>

				<section class="rounded-xl bg-surface-white p-4 shadow-card">
					<h2
						class="mb-3 flex items-center gap-2 text-base font-semibold text-ink-gray-9"
					>
						<FeatherIcon
							name="sliders"
							class="h-4 w-4 text-ink-gray-5"
							aria-hidden="true"
						/>
						{{ t('bid.assumptions') }}
					</h2>
					<div class="grid grid-cols-3 gap-2">
						<label
							v-for="name in scenarioNames"
							:key="name"
							class="text-xs text-ink-gray-6"
						>
							{{ t('bid.input.margin', { scenario: t(`scenario.${name}`) }) }}
							<input
								v-model.number="draft.scenario_margins_pct[name]"
								type="number"
								step="0.5"
								min="0"
								max="30"
								class="form-input mt-0.5 h-8 w-full rounded-lg border-outline-gray-2 text-sm"
								@input="touched = true"
							/>
						</label>
					</div>

					<!-- Win-probability model: a rough estimate, so out of the way by default -->
					<details class="mt-3 rounded-lg bg-surface-gray-1 px-3 py-2">
						<summary class="cursor-pointer text-sm font-medium text-ink-gray-7">
							{{ t('bid.advanced') }}
						</summary>
						<p class="mt-1 text-xs text-ink-gray-5">{{ t('bid.advancedHint') }}</p>
						<div class="mt-2 grid grid-cols-2 gap-2">
							<label
								v-for="f in PP_FIELDS"
								:key="f.key"
								class="text-xs text-ink-gray-6"
								:title="t(f.hint)"
							>
								{{ t(f.label) }}
								<input
									v-model.number="pp[f.key]"
									type="number"
									:step="f.step"
									:min="f.min"
									:max="f.max"
									class="form-input mt-0.5 h-8 w-full rounded-lg border-outline-gray-2 text-sm"
									@input="touched = true"
								/>
							</label>
						</div>
					</details>

					<div class="mt-3 flex flex-wrap items-center gap-2">
						<button
							class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand-600 px-3 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
							:disabled="!dirty || saving"
							@click="save"
						>
							<FeatherIcon name="save" class="h-4 w-4" aria-hidden="true" />
							{{ t('bid.save') }}
						</button>
						<Button variant="ghost" :disabled="saving" @click="reset">{{
							t('bid.reset')
						}}</Button>
						<span
							class="text-xs"
							:class="dirty ? 'text-amber-700' : 'text-ink-gray-5'"
							>{{ dirty ? t('bid.previewState') : t('bid.savedState') }}</span
						>
					</div>
					<ErrorMessage class="mt-2" :message="error" />
				</section>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ErrorMessage, FeatherIcon } from 'frappe-ui'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusPill from '@/components/StatusPill.vue'
import { api, errorText } from '@/utils/api'
import { formatCHF, formatPercent } from '@/utils/format'

const { t } = useI18n()

const props = defineProps<{ summary: any; tender: string }>()
const emit = defineEmits<{ (e: 'update', summary: any): void }>()

const OWN_MODES = [
	{ mode: 'margin_pct' as const, label: 'bid.own.margin' },
	{ mode: 'price_chf' as const, label: 'bid.own.price' },
]
// Win-probability inputs, edited as percentage points.
const PP_FIELDS = [
	{
		key: 'reference_win_probability',
		label: 'bid.input.base',
		hint: 'bid.input.baseHint',
		step: 1,
		min: 0,
		max: 100,
	},
	{
		key: 'price_sensitivity_probability_points_per_1pct_price',
		label: 'bid.input.sensitivity',
		hint: 'bid.input.sensitivityHint',
		step: 0.5,
		min: 0,
		max: 50,
	},
	{
		key: 'strategic_appetite_adjustment',
		label: 'bid.input.strategic',
		hint: 'bid.input.strategicHint',
		step: 1,
		min: -50,
		max: 50,
	},
	{
		key: 'competition_adjustment',
		label: 'bid.input.competition',
		hint: 'bid.input.competitionHint',
		step: 1,
		min: -50,
		max: 50,
	},
]

// Probabilities are edited as percentage points (0.05 -> 5).
const PP_KEYS = [
	'strategic_appetite_adjustment',
	'competition_adjustment',
	'price_sensitivity_probability_points_per_1pct_price',
	'reference_win_probability',
] as const

const draft = reactive<any>({ scenario_margins_pct: {} })
const pp = reactive<Record<string, number>>({})
const preview = ref<any>(null)
// Set when the estimator edits a field; until then the inputs follow the saved assumptions.
const touched = ref(false)
const saving = ref(false)
const error = ref('')

function loadDraft(a: any) {
	draft.scenario_margins_pct = { ...a.scenario_margins_pct }
	for (const k of PP_KEYS) pp[k] = Math.round(a[k] * 1000) / 10
}
watch(
	() => props.summary?.assumptions,
	(a) => a && !touched.value && loadDraft(a),
	{ immediate: true },
)

const scenarioNames = computed(() =>
	Object.keys(props.summary?.assumptions?.scenario_margins_pct || {}),
)
const draftAssumptions = computed(() => ({
	scenario_margins_pct: { ...draft.scenario_margins_pct },
	...Object.fromEntries(PP_KEYS.map((k) => [k, (Number(pp[k]) || 0) / 100])),
}))
const same = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b)
const dirty = computed(() => {
	const saved = props.summary?.assumptions
	if (!saved || !touched.value) return false
	const norm = (a: any) => ({
		scenario_margins_pct: Object.fromEntries(
			Object.entries(a.scenario_margins_pct).map(([k, v]) => [k, Number(v)]),
		),
		...Object.fromEntries(PP_KEYS.map((k) => [k, Math.round(a[k] * 1000) / 1000])),
	})
	return !same(norm(draftAssumptions.value), norm(saved))
})
const isCustom = computed(
	() => props.summary && !same(props.summary.assumptions, props.summary.default_assumptions),
)

// Live preview while editing (debounced); the cards show the preview until saved or reset.
let timer: ReturnType<typeof setTimeout> | null = null
// Also watch `touched`: v-model updates the draft before the @input handler sets it.
watch(
	[draftAssumptions, touched],
	() => {
		if (!dirty.value) return (preview.value = null)
		if (timer) clearTimeout(timer)
		timer = setTimeout(async () => {
			try {
				preview.value = await api('equans_bid.api.get_tender_summary', {
					tender: props.tender,
					assumptions: JSON.stringify(draftAssumptions.value),
				})
			} catch (e: any) {
				error.value = errorText(e, t('bid.previewFailed'))
			}
		}, 250)
	},
	{ deep: true },
)
const shown = computed(() => (dirty.value && preview.value) || props.summary)

async function persist(assumptions: any) {
	saving.value = true
	error.value = ''
	try {
		const s = await api('equans_bid.api.set_bid_assumptions', {
			tender: props.tender,
			assumptions: assumptions ? JSON.stringify(assumptions) : '',
		})
		preview.value = null
		touched.value = false
		loadDraft(s.assumptions)
		emit('update', s)
	} catch (e: any) {
		error.value = errorText(e, t('common.saveFailed'))
	} finally {
		saving.value = false
	}
}
const save = () => persist(draftAssumptions.value)
const reset = () => persist(null)

// Bid selection: a scenario, or the own offer (margin % or fixed CHF price). Disabled while
// assumptions are being edited, so what is chosen is always what is saved.
const selecting = ref<string | null>(null)
const selectError = ref('')
const own = reactive<{ mode: 'margin_pct' | 'price_chf'; value: number | '' }>({
	mode: 'margin_pct',
	value: '',
})
const ownSelected = computed(() => shown.value?.selected_bid?.scenario === 'custom')
watch(
	() => props.summary?.selected_bid,
	(b) => {
		if (b?.scenario !== 'custom') return
		const [mode, value] = Object.entries(b.input)[0] as [any, number]
		own.mode = mode
		own.value = value
	},
	{ immediate: true },
)
const ownValid = computed(() => {
	const v = Number(own.value)
	if (own.value === '' || !Number.isFinite(v)) return false
	return own.mode === 'margin_pct' ? v >= 0 && v <= 30 : v > 0
})
const recommendedName = computed(
	() => (shown.value?.bid_range || []).find((s: any) => s.recommended)?.scenario || 'Target',
)

async function select(choice: any) {
	selecting.value = choice?.scenario || 'clear'
	selectError.value = ''
	try {
		const s = await api('equans_bid.api.set_bid_selection', { tender: props.tender, ...choice })
		emit('update', s)
	} catch (e: any) {
		selectError.value = errorText(e, t('common.saveFailed'))
	} finally {
		selecting.value = null
	}
}
const selectOwn = () =>
	ownValid.value && select({ scenario: 'custom', [own.mode]: Number(own.value) })

// Cost build-up lines; notes carry the percentages from the project parameters.
const buildUp = computed(() => {
	const p = props.summary?.parameters || {}
	const pctOf = (v: number) => formatPercent((v || 0) / 100)
	return [
		{ key: 'catalog_material', note: { waste: pctOf(p.material_waste_pct) } },
		{ key: 'supplier_material' },
		{ key: 'labour' },
		{ key: 'small_material', note: { pct: pctOf(p.small_material_pct) } },
		{ key: 'supplier_contingency', note: { pct: pctOf(p.supplier_package_contingency_pct) } },
		{ key: 'project_costs' },
		{ key: 'direct_cost', total: true },
		{ key: 'transport_equipment', note: { pct: pctOf(p.transport_equipment_pct) } },
		{ key: 'overhead', note: { pct: pctOf(p.overhead_pct) } },
		{ key: 'cost_baseline', total: true },
	].map((l: any) => ({
		...l,
		label: t(`buildUp.${l.key}.label`),
		note: l.total ? '' : t(`buildUp.${l.key}.note`, l.note || {}),
	}))
})
</script>
