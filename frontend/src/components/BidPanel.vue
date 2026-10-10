<template>
  <section class="border-b px-5 py-3">
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <h2 class="text-base font-semibold text-ink-gray-9">Empfohlene Angebotsspanne</h2>
      <span class="text-xs text-ink-gray-5">Gewinnchance: Modellschätzung, nicht auf historische Angebote kalibriert</span>
      <span v-if="isCustom" class="rounded bg-surface-amber-1 px-1.5 py-0.5 text-xs text-ink-amber-3">Eigene Annahmen</span>
      <div class="ml-auto flex gap-2">
        <Button :variant="open === 'buildup' ? 'subtle' : 'ghost'" icon-left="layers" @click="toggle('buildup')">Kostenaufbau</Button>
        <Button :variant="open === 'assumptions' ? 'subtle' : 'ghost'" icon-left="sliders" @click="toggle('assumptions')">Annahmen</Button>
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
          <span class="text-sm font-medium text-ink-gray-7">{{ SCENARIO[s.scenario] || s.scenario }}</span>
          <Badge v-if="s.recommended" theme="green" label="Empfohlen" />
        </div>
        <div class="text-xl font-semibold tabular-nums text-ink-gray-9">{{ chf(s.bid_price_chf, 0) }}</div>
        <div class="mt-1 grid grid-cols-2 gap-x-2 text-xs text-ink-gray-6">
          <span>Marge</span><span class="text-right tabular-nums text-ink-gray-8">{{ num(s.margin_pct, 1) }} %</span>
          <span>Gewinnchance</span><span class="text-right tabular-nums text-ink-gray-8">{{ pct(s.estimated_win_probability) }}</span>
          <span>DB bei Zuschlag</span><span class="text-right tabular-nums text-ink-gray-8">{{ chf(s.contribution_if_won_chf, 0) }}</span>
          <span>Erwarteter DB</span><span class="text-right font-medium tabular-nums text-ink-gray-9">{{ chf(s.expected_contribution_chf, 0) }}</span>
        </div>
        <div class="mt-1.5 h-1.5 overflow-hidden rounded bg-surface-gray-3" :title="`Gewinnchance ${pct(s.estimated_win_probability)}`">
          <div class="h-full rounded bg-surface-gray-7" :style="{ width: `${s.estimated_win_probability * 100}%` }" />
        </div>
      </div>
      <div class="rounded-lg border border-dashed px-3 py-2">
        <div class="text-sm font-medium text-ink-gray-7">Richtpreis</div>
        <div class="text-xl font-semibold tabular-nums text-ink-gray-9">{{ chf(shown.indicative_price.bid_price_chf, 0) }}</div>
        <div class="mt-1 text-xs text-ink-gray-6">
          Kostenbasis {{ chf(shown.build_up.cost_baseline, 0) }} ÷ (1 − {{ num(shown.indicative_price.margin_pct, 1) }} % Zielmarge),
          aufgerundet auf CHF 1’000
        </div>
        <div v-if="shown.totals.unresolved_count" class="mt-1 text-xs text-ink-red-4">
          {{ shown.totals.unresolved_count }} Positionen ohne Preis sind nicht enthalten
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
            <td class="px-3 py-1.5 text-right tabular-nums">{{ chf(shown.build_up[line.key], 0) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Assumptions -->
    <div v-if="open === 'assumptions'" class="mt-3 rounded-lg border p-3">
      <div class="grid grid-cols-2 gap-3 md:grid-cols-6">
        <label v-for="name in scenarioNames" :key="name" class="text-xs text-ink-gray-6">
          Marge {{ SCENARIO[name] }} (%)
          <input v-model.number="draft.scenario_margins_pct[name]" type="number" step="0.5" min="0" max="30" class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm" @input="touched = true" />
        </label>
        <label class="text-xs text-ink-gray-6" title="Positiv = wir wollen den Auftrag unbedingt (z. B. Referenzprojekt, freie Kapazität)">
          Strategisches Interesse (Pp.)
          <input v-model.number="pp.strategic_appetite_adjustment" type="number" step="1" min="-50" max="50" class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm" @input="touched = true" />
        </label>
        <label class="text-xs text-ink-gray-6" title="Negativ = viele oder aggressive Mitbewerber">
          Wettbewerb (Pp.)
          <input v-model.number="pp.competition_adjustment" type="number" step="1" min="-50" max="50" class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm" @input="touched = true" />
        </label>
        <label class="text-xs text-ink-gray-6" title="Wie stark sinkt die Gewinnchance pro 1 % höherem Preis gegenüber dem Richtpreis">
          Preissensitivität (Pp. je 1 %)
          <input v-model.number="pp.price_sensitivity_probability_points_per_1pct_price" type="number" step="0.5" min="0" max="50" class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm" @input="touched = true" />
        </label>
        <label class="text-xs text-ink-gray-6" title="Gewinnchance beim Richtpreis">
          Basis-Gewinnchance (%)
          <input v-model.number="pp.reference_win_probability" type="number" step="1" min="0" max="100" class="form-input mt-0.5 h-7 w-full rounded border-outline-gray-2 text-sm" @input="touched = true" />
        </label>
      </div>
      <div class="mt-3 flex items-center gap-2">
        <Button variant="solid" :loading="saving" :disabled="!dirty" @click="save">Annahmen speichern</Button>
        <Button variant="ghost" :disabled="saving" @click="reset">Auf Projektparameter zurücksetzen</Button>
        <span class="text-xs text-ink-gray-5">
          {{ dirty ? 'Vorschau – noch nicht gespeichert' : 'Gespeichert' }}
        </span>
        <ErrorMessage :message="error" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Badge, ErrorMessage, call } from 'frappe-ui'
import { computed, reactive, ref, watch } from 'vue'
import { SCENARIO, chf, num, pct } from '@/utils/format'

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
watch(() => props.summary?.assumptions, (a) => a && !touched.value && loadDraft(a), { immediate: true })

const scenarioNames = computed(() => Object.keys(props.summary?.assumptions?.scenario_margins_pct || {}))
const draftAssumptions = computed(() => ({
  scenario_margins_pct: { ...draft.scenario_margins_pct },
  ...Object.fromEntries(PP_KEYS.map((k) => [k, (Number(pp[k]) || 0) / 100])),
}))
const same = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b)
const dirty = computed(() => {
  const saved = props.summary?.assumptions
  if (!saved || !touched.value) return false
  const norm = (a: any) => ({
    scenario_margins_pct: Object.fromEntries(Object.entries(a.scenario_margins_pct).map(([k, v]) => [k, Number(v)])),
    ...Object.fromEntries(PP_KEYS.map((k) => [k, Math.round(a[k] * 1000) / 1000])),
  })
  return !same(norm(draftAssumptions.value), norm(saved))
})
const isCustom = computed(() => props.summary && !same(props.summary.assumptions, props.summary.default_assumptions))

// Live preview while editing (debounced); the cards show the preview until saved or reset.
let timer: ReturnType<typeof setTimeout> | null = null
// Also watch `touched`: v-model updates the draft before the @input handler sets it.
watch([draftAssumptions, touched], () => {
  if (!dirty.value) return (preview.value = null)
  if (timer) clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      preview.value = await call('equans_bid.api.get_tender_summary', {
        tender: props.tender,
        assumptions: JSON.stringify(draftAssumptions.value),
      })
    } catch (e: any) {
      error.value = e?.message || 'Vorschau fehlgeschlagen'
    }
  }, 250)
}, { deep: true })
const shown = computed(() => (dirty.value && preview.value) || props.summary)

async function persist(assumptions: any) {
  saving.value = true
  error.value = ''
  try {
    const s = await call('equans_bid.api.set_bid_assumptions', {
      tender: props.tender,
      assumptions: assumptions ? JSON.stringify(assumptions) : '',
    })
    preview.value = null
    touched.value = false
    loadDraft(s.assumptions)
    emit('update', s)
  } catch (e: any) {
    error.value = e?.messages?.join(', ') || e?.message || 'Speichern fehlgeschlagen'
  } finally {
    saving.value = false
  }
}
const save = () => persist(draftAssumptions.value)
const reset = () => persist(null)

const buildUp = computed(() => {
  const p = props.summary?.parameters || {}
  return [
    { key: 'catalog_material', label: 'Material Katalog', note: `inkl. ${p.material_waste_pct} % Verschnitt` },
    { key: 'supplier_material', label: 'Lieferpakete', note: 'Katalogpreis oder Offerte' },
    { key: 'labour', label: 'Montage', note: 'Stunden × Ansatz, mit Projektfaktoren' },
    { key: 'small_material', label: 'Kleinmaterial', note: `${p.small_material_pct} % auf Katalogmaterial` },
    { key: 'supplier_contingency', label: 'Reserve Lieferpakete', note: `${p.supplier_package_contingency_pct} %` },
    { key: 'project_costs', label: 'Projektkosten', note: 'Engineering, Inbetriebnahme, Hygiene, Doku' },
    { key: 'direct_cost', label: 'Direkte Kosten', note: '', total: true },
    { key: 'transport_equipment', label: 'Transport & Geräte', note: `${p.transport_equipment_pct} %` },
    { key: 'overhead', label: 'Gemeinkosten', note: `${p.overhead_pct} %` },
    { key: 'cost_baseline', label: 'Kostenbasis', note: '', total: true },
  ]
})
</script>
