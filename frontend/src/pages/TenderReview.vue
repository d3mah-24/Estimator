<template>
  <div class="flex h-screen flex-col">
    <!-- Header -->
    <header class="flex items-center justify-between gap-4 border-b px-5 py-3">
      <div class="min-w-0">
        <router-link to="/" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">← Ausschreibungen</router-link>
        <div class="flex items-center gap-3">
          <h1 class="truncate text-xl font-semibold text-ink-gray-9">{{ tender.doc?.project_name || '…' }}</h1>
          <Badge
            v-if="tender.doc"
            :theme="TENDER_STATUS[tender.doc.status]?.theme"
            :label="TENDER_STATUS[tender.doc.status]?.label"
          />
        </div>
        <p v-if="tender.doc?.processing_log" class="truncate text-sm text-ink-gray-5">{{ tender.doc.processing_log }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <Button icon-left="refresh-cw" :loading="reprocessing" @click="reprocess">Erneut verarbeiten</Button>
      </div>
    </header>

    <!-- Totals -->
    <section v-if="summary.data" class="grid grid-cols-2 gap-3 border-b px-5 py-3 md:grid-cols-5">
      <div v-for="k in kpis" :key="k.label" class="rounded-lg border px-3 py-2">
        <div class="text-sm text-ink-gray-5">{{ k.label }}</div>
        <div class="text-lg font-semibold tabular-nums" :class="k.tone">{{ k.value }}</div>
        <div v-if="k.hint" class="text-xs text-ink-gray-5">{{ k.hint }}</div>
      </div>
    </section>

    <!-- Subtotals by system -->
    <section v-if="summary.data" class="border-b px-5 py-2">
      <button class="text-sm font-medium text-ink-gray-7 hover:text-ink-gray-9" @click="showSystems = !showSystems">
        {{ showSystems ? '▾' : '▸' }} Nach Anlage ({{ systemRows.length }})
      </button>
      <div v-if="showSystems" class="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-2 xl:grid-cols-3">
        <button
          v-for="r in systemRows"
          :key="r.system"
          :disabled="!r.key"
          class="flex items-center justify-between gap-3 rounded px-2 py-1 text-left hover:bg-surface-gray-2"
          :class="r.key && systemFilter === r.key ? 'bg-surface-blue-1' : ''"
          @click="systemFilter = systemFilter === r.key ? '' : r.key"
        >
          <span class="truncate text-ink-gray-8">{{ r.system }}</span>
          <span class="shrink-0 tabular-nums text-ink-gray-6">{{ r.positions }} Pos. · {{ chf(r.direct_cost, 0) }}</span>
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
            placeholder="Suchen (Beschreibung, Produkt, LV-ID)"
            class="form-input h-7 w-64 rounded border-outline-gray-2 text-sm"
          />
          <select v-model="statusFilter" class="form-select h-7 rounded border-outline-gray-2 py-0 text-sm">
            <option value="">Alle Status ({{ items.data?.length || 0 }})</option>
            <option v-for="(meta, key) in STATUS" :key="key" :value="key">
              {{ meta.label }} ({{ summary.data?.by_status?.[key]?.positions || 0 }})
            </option>
          </select>
          <select v-model="systemFilter" class="form-select h-7 max-w-xs rounded border-outline-gray-2 py-0 text-sm">
            <option value="">Alle Anlagen</option>
            <option v-for="s in systems" :key="s" :value="s">{{ s }}</option>
          </select>
          <span class="ml-auto text-sm text-ink-gray-5">{{ filtered.length }} Positionen · {{ chf(filteredTotal, 0) }}</span>
        </div>

        <div class="min-h-0 flex-1 overflow-auto">
          <table class="w-full text-left text-sm">
            <thead class="sticky top-0 z-10 bg-surface-gray-2 text-ink-gray-6">
              <tr>
                <th class="px-3 py-2 font-medium">LV-ID</th>
                <th class="px-3 py-2 font-medium">Beschreibung</th>
                <th class="px-3 py-2 text-right font-medium">Menge</th>
                <th class="px-3 py-2 font-medium">Einh.</th>
                <th class="px-3 py-2 font-medium">Produkt</th>
                <th class="px-3 py-2 text-right font-medium">Direkte Kosten</th>
                <th class="px-3 py-2 font-medium">Status</th>
                <th class="px-3 py-2 font-medium">Quelle</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="items.loading && !items.data?.length">
                <td colspan="8" class="px-3 py-6 text-center text-ink-gray-5">Positionen werden geladen …</td>
              </tr>
              <tr
                v-for="row in filtered"
                :key="row.name"
                class="cursor-pointer border-t align-top"
                :class="row.name === selected?.name ? 'bg-surface-blue-1' : 'hover:bg-surface-gray-1'"
                @click="select(row)"
              >
                <td class="whitespace-nowrap px-3 py-2 font-mono text-xs">
                  <div>{{ row.position_id }}</div>
                  <div v-if="row.golden_lv_id" class="text-ink-green-3" title="Verifizierte Referenzposition">
                    {{ row.golden_lv_id }} ✓
                  </div>
                </td>
                <td class="px-3 py-2">
                  <div class="line-clamp-2 text-ink-gray-9">{{ row.description }}</div>
                  <div class="truncate text-xs text-ink-gray-5">{{ row.system }}</div>
                </td>
                <td class="whitespace-nowrap px-3 py-2 text-right tabular-nums">{{ num(row.quantity, 3) }}</td>
                <td class="px-3 py-2">{{ UNIT[row.unit] || row.unit }}</td>
                <td class="whitespace-nowrap px-3 py-2 font-mono text-xs">{{ row.matched_product || '—' }}</td>
                <td class="whitespace-nowrap px-3 py-2 text-right tabular-nums" @click.stop>
                  <template v-if="row.status === 'supplier_quote_required'">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      :value="row.quote_override || ''"
                      :placeholder="`Katalog ${num(row.material_cost, 0)}`"
                      title="Offertpreis Lieferant (Material total, CHF)"
                      class="form-input h-7 w-32 rounded border-outline-amber-2 text-right text-sm"
                      @change="(e) => saveQuote(row, (e.target as HTMLInputElement).value)"
                      @focus="select(row)"
                    />
                    <div class="mt-0.5 text-xs" :class="row.quote_override ? 'text-ink-green-3' : 'text-ink-amber-3'">
                      {{ chf(row.direct_cost) }} {{ row.quote_override ? '· Offerte' : '· provisorisch' }}
                    </div>
                  </template>
                  <template v-else-if="STATUS[row.status]?.priced">{{ chf(row.direct_cost) }}</template>
                  <span v-else class="text-ink-gray-4" title="Kein Preis bis zur Prüfung">—</span>
                </td>
                <td class="px-3 py-2">
                  <Badge :theme="STATUS[row.status]?.theme" :label="STATUS[row.status]?.label || row.status" />
                </td>
                <td class="whitespace-nowrap px-3 py-2 text-ink-blue-3">S. {{ row.source_page }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>

      <!-- Traceability -->
      <aside class="flex min-w-[360px] flex-[3] flex-col">
        <div class="border-b px-4 py-2">
          <h2 class="text-base font-semibold text-ink-gray-9">Dokumenten-Rückverfolgbarkeit</h2>
        </div>

        <div v-if="selected" class="max-h-[45%] overflow-auto border-b px-4 py-3 text-sm">
          <div class="mb-2 flex items-start justify-between gap-2">
            <div>
              <div class="font-mono text-xs text-ink-gray-5">
                {{ selected.position_id }}<span v-if="selected.golden_lv_id"> · {{ selected.golden_lv_id }}</span>
              </div>
              <div class="font-medium text-ink-gray-9">{{ selected.description }}</div>
            </div>
            <Badge :theme="STATUS[selected.status]?.theme" :label="STATUS[selected.status]?.label" />
          </div>
          <p class="mb-3 rounded bg-surface-gray-2 px-2 py-1.5 text-ink-gray-7">{{ selected.status_reason }}</p>
          <p v-if="attrs.system_conflict" class="mb-3 rounded bg-surface-amber-1 px-2 py-1.5 text-ink-amber-3">
            Widerspruch im Dokument: {{ attrs.system_conflict }}
          </p>
          <p v-if="selected.error" class="mb-3 rounded bg-surface-red-1 px-2 py-1.5 text-ink-red-4">{{ selected.error }}</p>

          <dl class="grid grid-cols-2 gap-x-3 gap-y-1">
            <dt class="text-ink-gray-5">Menge</dt>
            <dd class="tabular-nums">{{ num(selected.quantity, 3) }} {{ UNIT[selected.unit] || selected.unit }}</dd>
            <dt class="text-ink-gray-5">Erkennung / Zuordnung</dt>
            <dd class="tabular-nums">{{ pct(selected.extraction_confidence) }} / {{ pct(selected.match_confidence) }}</dd>
            <template v-if="STATUS[selected.status]?.priced">
              <dt class="text-ink-gray-5">Material</dt>
              <dd class="tabular-nums">
                {{ chf(selected.material_cost) }}
                <span class="text-xs text-ink-gray-5" v-if="!selected.quote_override">
                  ({{ num(selected.quantity, 3) }} × {{ chf(selected.net_unit_cost) }} + {{ wastePct }} % Verschnitt)
                </span>
                <span class="text-xs text-ink-green-3" v-else>(Offerte)</span>
              </dd>
              <dt class="text-ink-gray-5">Arbeit</dt>
              <dd class="tabular-nums">
                {{ chf(selected.labour_cost) }}
                <span class="text-xs text-ink-gray-5">({{ num(selected.labour_hours, 2) }} h × {{ chf(selected.labour_rate, 0) }})</span>
              </dd>
              <dt class="font-medium text-ink-gray-7">Direkte Kosten</dt>
              <dd class="font-semibold tabular-nums">{{ chf(selected.direct_cost) }}</dd>
            </template>
          </dl>

          <div class="mt-3 grid grid-cols-2 gap-2">
            <label class="text-xs text-ink-gray-5">
              Produkt
              <select
                class="form-select mt-0.5 h-7 w-full rounded border-outline-gray-2 py-0 text-sm"
                :value="selected.matched_product || ''"
                @change="(e) => saveProduct(selected, (e.target as HTMLSelectElement).value)"
              >
                <option value="" disabled>— wählen —</option>
                <option v-for="p in catalog.data" :key="p.name" :value="p.name">{{ p.name }} · {{ p.description }}</option>
              </select>
            </label>
            <label class="text-xs text-ink-gray-5">
              Status
              <select
                class="form-select mt-0.5 h-7 w-full rounded border-outline-gray-2 py-0 text-sm"
                :value="selected.status"
                @change="(e) => saveStatus(selected, (e.target as HTMLSelectElement).value)"
              >
                <option v-for="(meta, key) in STATUS" :key="key" :value="key">{{ meta.label }}</option>
              </select>
            </label>
          </div>
          <p v-if="lastSave" class="mt-2 text-xs text-ink-gray-5">{{ lastSave }}</p>
          <ErrorMessage class="mt-2" :message="saveError" />
        </div>
        <div v-else class="border-b px-4 py-3 text-sm text-ink-gray-5">
          Position wählen, um Herkunft und Berechnung zu sehen.
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
  </div>
</template>

<script setup lang="ts">
import { Badge, ErrorMessage, call, createDocumentResource, createListResource, createResource } from 'frappe-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import PdfViewer from '@/components/PdfViewer.vue'
import { STATUS, TENDER_STATUS, UNIT, chf, num, pct } from '@/utils/format'

const props = defineProps<{ name: string }>()

const tender = createDocumentResource({ doctype: 'Tender', name: props.name, auto: true })

const summary = createResource({
  url: 'equans_bid.api.get_tender_summary',
  params: { tender: props.name },
  auto: true,
})

const ITEM_FIELDS = [
  'name', 'idx', 'position_id', 'golden_lv_id', 'system', 'source_page', 'description', 'description_original',
  'quantity_raw', 'unit_raw', 'quantity', 'unit', 'matched_product', 'match_confidence', 'extraction_confidence',
  'net_unit_cost', 'quote_override', 'material_cost', 'labour_hours', 'labour_rate', 'labour_cost', 'direct_cost',
  'status', 'status_reason', 'error', 'attributes',
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
const systems = computed(() => [...new Set((items.data || []).map((i: any) => i.system).filter(Boolean))].sort())
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return (items.data || []).filter((i: any) => {
    if (statusFilter.value && i.status !== statusFilter.value) return false
    if (systemFilter.value && i.system !== systemFilter.value) return false
    if (!q) return true
    return [i.description, i.matched_product, i.position_id, i.golden_lv_id].some((v) => v?.toLowerCase().includes(q))
  })
})
const filteredTotal = computed(() => filtered.value.reduce((s: number, i: any) => s + (i.direct_cost || 0), 0))

// Totals
const kpis = computed(() => {
  const s = summary.data
  if (!s) return []
  const t = s.totals
  return [
    { label: 'Direkte Kosten', value: chf(t.direct_cost, 0), hint: 'Material + Arbeit, bepreiste Positionen' },
    { label: 'Davon bestätigt', value: chf(t.confirmed_cost, 0), tone: 'text-ink-green-3', hint: 'Katalog oder Offerte' },
    { label: 'Davon provisorisch', value: chf(t.provisional_cost, 0), tone: 'text-ink-amber-3', hint: 'Offerte ausstehend / Annahme' },
    { label: 'Offene Positionen', value: String(t.unresolved_count), tone: 'text-ink-red-4', hint: 'Ohne Preis, Prüfung nötig' },
    { label: 'Kostenbasis', value: chf(s.build_up.cost_baseline, 0), hint: 'inkl. Projektkosten, Zuschläge, Overhead' },
  ]
})

// Subtotals by system, largest first (from the backend summary).
const showSystems = ref(false)
const systemRows = computed(() =>
  Object.entries(summary.data?.by_system || {})
    .map(([key, v]: [string, any]) => ({ key: key === '-' ? '' : key, system: key === '-' ? 'Ohne Anlage' : key, ...v }))
    .sort((a, b) => b.direct_cost - a.direct_cost),
)

// Selection and traceability
const selected = ref<any>(null)
const activePage = ref(1)
function select(row: any) {
  selected.value = row
  activePage.value = row.source_page
}

const pdfUrl = computed(() => (tender.doc ? `/api/method/equans_bid.api.get_tender_pdf?tender=${encodeURIComponent(props.name)}` : ''))
const fileName = computed(() => (tender.doc?.tender_file || 'BKP_244_LV_Lueftung_260804.pdf').split('/').pop())

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
const wastePct = computed(() => {
  const s = selected.value
  const base = (s?.quantity || 0) * (s?.net_unit_cost || 0)
  return base ? Math.round((s.material_cost / base - 1) * 1000) / 10 : 0
})

// Lines to highlight: the quantity line for LV positions, the table rows for component lists.
const evidence = computed(() => {
  const s = selected.value
  if (!s || activePage.value !== s.source_page) return []
  const lines = (s.description_original || '').split('\n').filter(Boolean)
  if (lines[0] === 'Bauteilliste Lüftung') return lines.slice(1)
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
    const res = await call('equans_bid.api.update_item', { tender: props.name, item: row.name, ...args })
    for (const f of ITEM_FIELDS) if (f in res.item) row[f] = res.item[f]
    summary.setData(res.summary)
    lastSave.value = `Gespeichert und neu berechnet in ${Math.round(performance.now() - started)} ms`
  } catch (e: any) {
    saveError.value = e?.messages?.join(', ') || e?.message || 'Speichern fehlgeschlagen'
  }
}
const saveQuote = (row: any, value: string) => update(row, { quote_override: value === '' ? 0 : Number(value) })
const saveProduct = (row: any, product: string) => product && update(row, { matched_product: product })
const saveStatus = (row: any, status: string) => update(row, { status })

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
watch(() => tender.doc?.status, (s) => s === 'Processing' && poll(), { immediate: true })

async function reprocess() {
  reprocessing.value = true
  await call('equans_bid.api.start_processing', { tender: props.name })
  await tender.reload()
  poll()
}
onBeforeUnmount(() => timer && clearInterval(timer))
</script>
