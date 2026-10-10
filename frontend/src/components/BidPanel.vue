<template>
	<section class="border-b px-5 py-3">
		<div class="mb-2 flex flex-wrap items-center gap-2">
			<h2 class="text-base font-semibold text-ink-gray-9">{{ t('bid.title') }}</h2>
			<span class="text-xs text-ink-gray-5">{{ t('bid.modelNote') }}</span>
			<span
				v-if="isCustom"
				class="rounded bg-surface-amber-1 px-1.5 py-0.5 text-xs text-ink-amber-3"
				>{{ t('bid.custom') }}</span
			>
			<div class="ml-auto flex gap-2">
				<Button
					:variant="open === 'buildup' ? 'subtle' : 'ghost'"
					icon-left="layers"
					@click="toggle('buildup')"
					>{{ t('bid.buildUp') }}</Button
				>
				<Button
					:variant="open === 'assumptions' ? 'subtle' : 'ghost'"
					icon-left="sliders"
					@click="toggle('assumptions')"
					>{{ t('bid.assumptions') }}</Button
				>
			</div>
		</div>

		<div class="grid grid-cols-1 gap-3 md:grid-cols-4">
			<div
				v-for="s in shown.bid_range"
				:key="s.scenario"
				class="rounded-lg border px-3 py-2"
				:class="s.recommended ? 'border-outline-green-2 bg-surface-green-1' : ''"
			>
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium text-ink-gray-7">{{
						t(`scenario.${s.scenario}`)
					}}</span>
					<Badge v-if="s.recommended" theme="green" :label="t('bid.recommended')" />
				</div>
				<div class="text-xl font-semibold tabular-nums text-ink-gray-9">
					{{ formatCHF(s.bid_price_chf, { digits: 0 }) }}
				</div>
				<div class="mt-1 grid grid-cols-2 gap-x-2 text-xs text-ink-gray-6">
					<span>{{ t('bid.margin') }}</span>
					<span class="text-right tabular-nums text-ink-gray-8">{{
						formatPercent(s.margin_pct / 100)
					}}</span>
					<span>{{ t('bid.winProbability') }}</span>
					<span class="text-right tabular-nums text-ink-gray-8">{{
						formatPercent(s.estimated_win_probability, { maxDigits: 0 })
					}}</span>
					<span>{{ t('bid.contributionIfWon') }}</span>
					<span class="text-right tabular-nums text-ink-gray-8">{{
						formatCHF(s.contribution_if_won_chf, { digits: 0 })
					}}</span>
					<span>{{ t('bid.expectedContribution') }}</span>
					<span class="text-right font-medium tabular-nums text-ink-gray-9">{{
						formatCHF(s.expected_contribution_chf, { digits: 0 })
					}}</span>
				</div>
				<div
					class="mt-1.5 h-1.5 overflow-hidden rounded bg-surface-gray-3"
					:title="`${t('bid.winProbability')} ${formatPercent(
						s.estimated_win_probability,
						{ maxDigits: 0 }
					)}`"
				>
					<div
						class="h-full rounded bg-surface-gray-7"
						:style="{ width: `${s.estimated_win_probability * 100}%` }"
					/>
				</div>
			</div>
			<div class="rounded-lg border border-dashed px-3 py-2">
				<div class="text-sm font-medium text-ink-gray-7">{{ t('bid.standardOffer') }}</div>
				<div class="text-xl font-semibold tabular-nums text-ink-gray-9">
					{{ formatCHF(shown.indicative_price.bid_price_chf, { digits: 0 }) }}
				</div>
				<div class="mt-1 text-xs text-ink-gray-6">
					{{
						t('bid.standardOfferFormula', {
							baseline: formatCHF(shown.build_up.cost_baseline, { digits: 0 }),
							margin: formatPercent(shown.indicative_price.margin_pct / 100),
							step: formatCHF(1000, { digits: 0 }),
						})
					}}
				</div>
				<div v-if="shown.totals.unresolved_count" class="mt-1 text-xs text-ink-red-4">
					{{
						t(
							'bid.unpricedExcluded',
							{ count: shown.totals.unresolved_count },
							shown.totals.unresolved_count
						)
					}}
				</div>
			</div>
		</div>

		<!-- Cost build-up -->
		<div v-if="open === 'buildup'" class="mt-3 max-w-xl rounded-lg border">
			<table class="w-full text-sm">
				<tbody>
					<tr
						v-for="line in buildUp"
						:key="line.key"
						class="border-t first:border-t-0"
						:class="line.total ? 'bg-surface-gray-2 font-semibold' : ''"
					>
						<td class="px-3 py-1.5 text-ink-gray-8">{{ line.label }}</td>
						<td class="px-3 py-1.5 text-xs text-ink-gray-5">{{ line.note }}</td>
						<td class="px-3 py-1.5 text-right tabular-nums">
							{{ formatCHF(shown.build_up[line.key], { digits: 0 }) }}
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Assumptions -->
		<div v-if="open === 'assumptions'" class="mt-3 rounded-lg border p-3">
			<div class="grid grid-cols-2 gap-3 md:grid-cols-6">
				<label v-for="name in scenarioNames" :key="name" class="text-xs text-ink-gray-6">
					{{ t('bid.input.margin', { scenario: t(`scenario.${name}`) }) }}
					<input
						v-model.number="draft.scenario_margins_pct[name]"
						type="number"
						step="0.5"
						min="0"
						max="30"
						class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm"
						@input="touched = true"
					/>
				</label>
				<label class="text-xs text-ink-gray-6" :title="t('bid.input.strategicHint')">
					{{ t('bid.input.strategic') }}
					<input
						v-model.number="pp.strategic_appetite_adjustment"
						type="number"
						step="1"
						min="-50"
						max="50"
						class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm"
						@input="touched = true"
					/>
				</label>
				<label class="text-xs text-ink-gray-6" :title="t('bid.input.competitionHint')">
					{{ t('bid.input.competition') }}
					<input
						v-model.number="pp.competition_adjustment"
						type="number"
						step="1"
						min="-50"
						max="50"
						class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm"
						@input="touched = true"
					/>
				</label>
				<label class="text-xs text-ink-gray-6" :title="t('bid.input.sensitivityHint')">
					{{ t('bid.input.sensitivity') }}
					<input
						v-model.number="pp.price_sensitivity_probability_points_per_1pct_price"
						type="number"
						step="0.5"
						min="0"
						max="50"
						class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm"
						@input="touched = true"
					/>
				</label>
				<label class="text-xs text-ink-gray-6" :title="t('bid.input.baseHint')">
					{{ t('bid.input.base') }}
					<input
						v-model.number="pp.reference_win_probability"
						type="number"
						step="1"
						min="0"
						max="100"
						class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm"
						@input="touched = true"
					/>
				</label>
			</div>
			<div class="mt-3 flex items-center gap-2">
				<Button variant="solid" :loading="saving" :disabled="!dirty" @click="save">{{
					t('bid.save')
				}}</Button>
				<Button variant="ghost" :disabled="saving" @click="reset">{{
					t('bid.reset')
				}}</Button>
				<span class="text-xs text-ink-gray-5">{{
					dirty ? t('bid.previewState') : t('bid.savedState')
				}}</span>
				<ErrorMessage :message="error" />
			</div>
		</div>
	</section>
</template>

<script setup lang="ts">
import { Badge, ErrorMessage } from 'frappe-ui'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorText } from '@/utils/api'
import { formatCHF, formatPercent } from '@/utils/format'

const { t } = useI18n()

const props = defineProps<{ summary: any; tender: string }>()
const emit = defineEmits<{ (e: 'update', summary: any): void }>()

const open = ref<'' | 'buildup' | 'assumptions'>('')
const toggle = (what: 'buildup' | 'assumptions') => (open.value = open.value === what ? '' : what)

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
	{ immediate: true }
)

const scenarioNames = computed(() =>
	Object.keys(props.summary?.assumptions?.scenario_margins_pct || {})
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
			Object.entries(a.scenario_margins_pct).map(([k, v]) => [k, Number(v)])
		),
		...Object.fromEntries(PP_KEYS.map((k) => [k, Math.round(a[k] * 1000) / 1000])),
	})
	return !same(norm(draftAssumptions.value), norm(saved))
})
const isCustom = computed(
	() => props.summary && !same(props.summary.assumptions, props.summary.default_assumptions)
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
	{ deep: true }
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
