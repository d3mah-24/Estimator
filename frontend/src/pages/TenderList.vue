<template>
  <div class="mx-auto max-w-5xl px-6 py-10">
    <div class="mb-8 flex items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold text-ink-gray-9">Ausschreibungen</h1>
        <p class="mt-1 text-base text-ink-gray-6">
          Leistungsverzeichnis hochladen, Positionen prüfen, Erstpreis erstellen.
        </p>
      </div>
      <Button variant="solid" icon-left="upload" @click="showNew = true">Neue Ausschreibung</Button>
    </div>

    <div class="overflow-hidden rounded-lg border">
      <table class="w-full text-left text-base">
        <thead class="bg-surface-gray-2 text-sm text-ink-gray-6">
          <tr>
            <th class="px-4 py-2 font-medium">Projekt</th>
            <th class="px-4 py-2 font-medium">Status</th>
            <th class="px-4 py-2 text-right font-medium">Direkte Kosten</th>
            <th class="px-4 py-2 text-right font-medium">Kostenbasis</th>
            <th class="px-4 py-2 text-right font-medium">Offene Positionen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="tenders.loading && !tenders.data?.length">
            <td colspan="5" class="px-4 py-6 text-center text-ink-gray-5">Lädt …</td>
          </tr>
          <tr v-else-if="!tenders.data?.length">
            <td colspan="5" class="px-4 py-6 text-center text-ink-gray-5">Noch keine Ausschreibung erfasst.</td>
          </tr>
          <tr
            v-for="t in tenders.data"
            :key="t.name"
            class="cursor-pointer border-t hover:bg-surface-gray-1"
            @click="open(t.name)"
          >
            <td class="px-4 py-3 font-medium text-ink-gray-9">{{ t.project_name }}</td>
            <td class="px-4 py-3">
              <Badge :theme="TENDER_STATUS[t.status]?.theme" :label="TENDER_STATUS[t.status]?.label || t.status" />
            </td>
            <td class="px-4 py-3 text-right tabular-nums">{{ chf(t.direct_cost, 0) }}</td>
            <td class="px-4 py-3 text-right tabular-nums">{{ chf(t.cost_baseline, 0) }}</td>
            <td class="px-4 py-3 text-right tabular-nums">{{ t.unresolved_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Dialog v-model="showNew" :options="{ title: 'Neue Ausschreibung' }">
      <template #body-content>
        <div class="space-y-4">
          <FormControl v-model="projectName" label="Projektname" placeholder="z. B. Schulhaus Oberglatt – Lüftung" />
          <FileUploader
            file-types=".pdf"
            :upload-args="{ private: true }"
            :validate-file="validatePdf"
            @success="(file) => (uploaded = file)"
          >
            <template #default="{ openFileSelector, uploading, progress, error }">
              <div class="flex items-center gap-3">
                <Button :loading="uploading" icon-left="file-text" @click="openFileSelector">
                  {{ uploading ? `Hochladen ${progress} %` : 'Leistungsverzeichnis (PDF) wählen' }}
                </Button>
                <span v-if="uploaded" class="truncate text-sm text-ink-gray-7">{{ uploaded.file_name }}</span>
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
          Hochladen und verarbeiten
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { Badge, Dialog, ErrorMessage, FileUploader, FormControl, call, createListResource } from 'frappe-ui'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { TENDER_STATUS, chf } from '@/utils/format'

const router = useRouter()
const showNew = ref(false)
const projectName = ref('')
const uploaded = ref<any>(null)
const creating = ref(false)
const createError = ref('')

const tenders = createListResource({
  doctype: 'Tender',
  fields: ['name', 'project_name', 'status', 'direct_cost', 'cost_baseline', 'unresolved_count', 'modified'],
  orderBy: 'modified desc',
  pageLength: 50,
  auto: true,
})

function validatePdf(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf')) return 'Bitte eine PDF-Datei wählen.'
  if (file.size > 50 * 1024 * 1024) return 'Die Datei ist grösser als 50 MB.'
}

function open(name: string) {
  router.push({ name: 'TenderReview', params: { name } })
}

async function create() {
  creating.value = true
  createError.value = ''
  try {
    const doc = await tenders.insert.submit({ project_name: projectName.value, tender_file: uploaded.value.file_url })
    await call('equans_bid.api.start_processing', { tender: doc.name })
    showNew.value = false
    open(doc.name)
  } catch (e: any) {
    createError.value = e?.messages?.join(', ') || e?.message || 'Erstellen fehlgeschlagen'
  } finally {
    creating.value = false
  }
}
</script>
