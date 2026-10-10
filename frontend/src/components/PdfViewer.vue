<template>
  <div class="flex h-full flex-col">
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2 text-sm">
      <div class="truncate text-ink-gray-7" :title="fileName">{{ fileName }}</div>
      <div class="flex shrink-0 items-center gap-1">
        <Button variant="ghost" icon="chevron-left" :disabled="page <= 1" @click="go(page - 1)" />
        <span class="tabular-nums text-ink-gray-8">{{ t('pdf.page', { page, count: pageCount || '…' }) }}</span>
        <Button variant="ghost" icon="chevron-right" :disabled="page >= pageCount" @click="go(page + 1)" />
      </div>
    </div>
    <div ref="scroller" class="relative flex-1 overflow-auto bg-surface-gray-2 p-3">
      <div v-if="error" class="p-4 text-sm text-ink-red-4">{{ error }}</div>
      <div v-else class="relative mx-auto w-fit shadow">
        <canvas ref="canvas" class="block bg-white" />
        <div
          v-for="(box, i) in boxes"
          :key="i"
          class="pointer-events-none absolute rounded-sm bg-yellow-300/40 ring-2 ring-amber-500"
          :style="{ left: box.x + 'px', top: box.y + 'px', width: box.w + 'px', height: box.h + 'px' }"
        />
      </div>
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-white/50">
        <LoadingIndicator class="h-6 w-6 text-ink-gray-5" />
      </div>
    </div>
    <div v-if="highlightNote" class="border-t px-3 py-1.5 text-xs text-ink-gray-6">{{ highlightNote }}</div>
  </div>
</template>

<script setup lang="ts">
import { LoadingIndicator } from 'frappe-ui'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url'
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

const props = defineProps<{
  url: string
  fileName: string
  page: number
  // Text fragments the position was read from; matching lines on the page are highlighted.
  evidence: string[]
}>()
const emit = defineEmits<{ (e: 'update:page', page: number): void }>()
const { t } = useI18n()

const canvas = ref<HTMLCanvasElement | null>(null)
const scroller = ref<HTMLElement | null>(null)
const pdf = shallowRef<any>(null)
const pageCount = ref(0)
const loading = ref(false)
const error = ref('')
const boxes = ref<{ x: number; y: number; w: number; h: number }[]>([])
// Highlight result as data, so the note follows a language switch.
const highlighted = ref<number | null>(null)
const highlightNote = computed(() =>
  highlighted.value === null
    ? ''
    : highlighted.value
      ? t('pdf.highlighted', { count: highlighted.value, page: props.page }, highlighted.value)
      : t('pdf.notHighlighted'),
)
let renderTask: any = null

const squash = (s: string) => s.replace(/\s+/g, '').toLowerCase()

function go(n: number) {
  emit('update:page', Math.min(Math.max(1, n), pageCount.value || n))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    pdf.value = await pdfjsLib.getDocument({ url: props.url, withCredentials: true }).promise
    pageCount.value = pdf.value.numPages
    await render()
  } catch (e: any) {
    error.value = t('pdf.loadFailed', { error: e?.message || String(e) })
  } finally {
    loading.value = false
  }
}

async function render() {
  if (!pdf.value || !canvas.value) return
  loading.value = true
  try {
    const page = await pdf.value.getPage(props.page)
    const width = (scroller.value?.clientWidth || 600) - 24
    const base = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({ scale: Math.min(2, width / base.width) })
    const ratio = window.devicePixelRatio || 1
    const c = canvas.value
    c.width = Math.floor(viewport.width * ratio)
    c.height = Math.floor(viewport.height * ratio)
    c.style.width = `${Math.floor(viewport.width)}px`
    c.style.height = `${Math.floor(viewport.height)}px`
    renderTask?.cancel()
    renderTask = page.render({
      canvasContext: c.getContext('2d')!,
      viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
    })
    await renderTask.promise
    boxes.value = await highlight(page, viewport)
    await nextTick()
    const first = boxes.value[0]
    if (first && scroller.value) scroller.value.scrollTo({ top: Math.max(0, first.y - 120), behavior: 'smooth' })
  } catch (e: any) {
    if (e?.name !== 'RenderingCancelledException') error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}

// Group the page's text items into lines and box every line that contains an evidence fragment.
async function highlight(page: any, viewport: any) {
  const wanted = props.evidence.map(squash).filter((s) => s.length >= 3)
  highlighted.value = null
  if (!wanted.length) return []
  const content = await page.getTextContent()
  const lines = new Map<number, any[]>()
  for (const item of content.items as any[]) {
    if (!item.str?.trim()) continue
    const key = Math.round(item.transform[5] / 3)
    if (!lines.has(key)) lines.set(key, [])
    lines.get(key)!.push(item)
  }
  const out = []
  for (const items of lines.values()) {
    const text = squash(items.map((i) => i.str).join(''))
    if (!wanted.some((w) => text.includes(w))) continue
    const rects = items.map((i) => {
      const [x1, y1, x2, y2] = viewport.convertToViewportRectangle([
        i.transform[4],
        i.transform[5] - 2,
        i.transform[4] + i.width,
        i.transform[5] + (i.height || 10),
      ])
      return { x: Math.min(x1, x2), y: Math.min(y1, y2), r: Math.max(x1, x2), b: Math.max(y1, y2) }
    })
    const x = Math.min(...rects.map((r) => r.x)) - 3
    const y = Math.min(...rects.map((r) => r.y)) - 2
    out.push({ x, y, w: Math.max(...rects.map((r) => r.r)) - x + 3, h: Math.max(...rects.map((r) => r.b)) - y + 2 })
  }
  highlighted.value = out.length
  return out
}

watch(() => props.url, load, { immediate: true })
watch(() => [props.page, props.evidence.join('|')], render)
onBeforeUnmount(() => renderTask?.cancel())
</script>
