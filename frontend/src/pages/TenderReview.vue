<template>
	<ProcessingOverlay v-if="busy" :file-name="fileName" :loading-results="loadingResults" />
	<div class="flex h-full flex-col" :inert="busy" :aria-hidden="busy">
		<!-- Page header: where am I, what is this tender, what can I do -->
		<header class="shrink-0 border-b bg-surface-white px-6 pt-3">
			<router-link
				to="/"
				class="inline-flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-8"
			>
				<FeatherIcon name="chevron-left" class="h-4 w-4" aria-hidden="true" />
				{{ t('list.title') }}
			</router-link>
			<div class="mt-1 flex items-start justify-between gap-4">
				<div class="min-w-0 flex-1">
					<div class="flex flex-wrap items-center gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-ink-gray-9">
							{{ tender.doc?.project_name || '…' }}
						</h1>
						<StatusPill
							v-if="tender.doc"
							:theme="TENDER_STATUS[tender.doc.status]?.theme"
							:icon="TENDER_ICON[tender.doc.status]"
							>{{ t(`tenderStatus.${tender.doc.status}`) }}</StatusPill
						>
					</div>
					<div
						class="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-5"
					>
						<span v-if="tender.doc?.trade" class="inline-flex items-center gap-1">
							<FeatherIcon name="wind" class="h-3.5 w-3.5" aria-hidden="true" />
							{{ tradeLabel(tender.doc.trade) }}
						</span>
						<span v-if="tender.doc?.tender_file" class="inline-flex items-center gap-1">
							<FeatherIcon name="file-text" class="h-3.5 w-3.5" aria-hidden="true" />
							{{ fileName }}
						</span>
						<span
							v-if="processingText"
							class="inline-flex items-center gap-1"
							:title="processingText"
						>
							<FeatherIcon name="cpu" class="h-3.5 w-3.5" aria-hidden="true" />
							<span class="max-w-md truncate">{{ processingText }}</span>
						</span>
						<span
							v-if="tender.doc?.catalog_priced_at"
							class="inline-flex items-center gap-1"
						>
							<FeatherIcon name="clock" class="h-3.5 w-3.5" aria-hidden="true" />
							{{
								t('review.pricedAt', {
									date: formatDate(tender.doc.catalog_priced_at),
								})
							}}
						</span>
					</div>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					<Button
						variant="outline"
						icon-left="tag"
						:disabled="!summary.data"
						:loading="refresh.loading"
						@click="previewRefresh"
						>{{ t('review.refreshPrices') }}</Button
					>
					<button
						class="inline-flex h-7 items-center gap-1.5 rounded bg-brand-600 px-3 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
						:disabled="!summary.data"
						@click="exportExcel"
					>
						<FeatherIcon name="download" class="h-4 w-4" aria-hidden="true" />
						{{ t('review.export') }}
					</button>
					<Dropdown :options="moreActions" align="end">
						<Button
							variant="ghost"
							icon="more-horizontal"
							:aria-label="t('review.more')"
						/>
					</Dropdown>
				</div>
			</div>

			<!-- Overview: progress of the review, cost baseline, chosen bid -->
			<div v-if="summary.data" class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-4">
				<div class="rounded-xl border bg-surface-white px-4 py-3 lg:col-span-2">
					<div class="flex items-baseline justify-between">
						<span class="text-sm font-medium text-ink-gray-7">{{
							t('review.progress')
						}}</span>
						<span class="text-xs text-ink-gray-5">{{
							t('review.positions', { count: totalCount }, totalCount)
						}}</span>
					</div>
					<div
						class="mt-2 flex h-2.5 overflow-hidden rounded-full bg-surface-gray-3"
						role="img"
						:aria-label="progressGroups.map((g) => `${g.label}: ${g.count}`).join(', ')"
					>
						<div
							v-for="g in progressGroups"
							:key="g.key"
							:class="g.bar"
							:style="{ width: `${totalCount ? (g.count / totalCount) * 100 : 0}%` }"
						/>
					</div>
					<div class="mt-2 grid grid-cols-3 gap-2">
						<button
							v-for="g in progressGroups"
							:key="g.key"
							class="rounded-lg px-2 py-1 text-left hover:bg-surface-gray-1"
							@click="filterGroup(g.filter)"
						>
							<div class="flex items-center gap-1.5 text-xs text-ink-gray-5">
								<span
									class="h-2 w-2 rounded-full"
									:class="g.bar"
									aria-hidden="true"
								/>
								{{ g.label }}
							</div>
							<div class="mt-0.5 flex items-baseline gap-2">
								<span class="text-lg font-semibold tabular-nums text-ink-gray-9">{{
									formatNumber(g.count, { maxDigits: 0 })
								}}</span>
								<span
									v-if="g.value !== null"
									class="text-xs tabular-nums text-ink-gray-5"
									>{{ formatCHF(g.value, { digits: 0 }) }}</span
								>
							</div>
						</button>
					</div>
				</div>
				<div class="rounded-xl border bg-surface-white px-4 py-3">
					<div class="flex items-center gap-2 text-sm font-medium text-ink-gray-7">
						<FeatherIcon
							name="layers"
							class="h-4 w-4 text-ink-gray-5"
							aria-hidden="true"
						/>
						{{ t('kpi.baseline.label') }}
					</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums text-ink-gray-9">
						{{ formatCHF(summary.data.build_up.cost_baseline, { digits: 0 }) }}
					</div>
					<div class="mt-1 text-xs text-ink-gray-5">
						{{
							t('review.directCostLine', {
								amount: formatCHF(summary.data.totals.direct_cost, { digits: 0 }),
							})
						}}
					</div>
				</div>
				<button
					class="rounded-xl border px-4 py-3 text-left transition-colors"
					:class="
						summary.data.selected_bid
							? 'border-brand-200 bg-brand-50 hover:bg-brand-100'
							: 'border-dashed bg-surface-white hover:bg-surface-gray-1'
					"
					@click="tab = 'bid'"
				>
					<div class="flex items-center gap-2 text-sm font-medium text-ink-gray-7">
						<FeatherIcon
							name="award"
							class="h-4 w-4 text-brand-600"
							aria-hidden="true"
						/>
						{{ t('review.bidCard') }}
					</div>
					<template v-if="summary.data.selected_bid">
						<div class="mt-1 text-2xl font-semibold tabular-nums text-brand-800">
							{{ formatCHF(summary.data.selected_bid.bid_price_chf, { digits: 0 }) }}
						</div>
						<div class="mt-1 text-xs text-ink-gray-6">
							{{ t(`scenario.${summary.data.selected_bid.scenario}`) }} ·
							{{ t('bid.margin') }}
							{{ formatPercent(summary.data.selected_bid.margin_pct / 100) }}
						</div>
					</template>
					<template v-else>
						<div class="mt-1 text-base font-medium text-ink-gray-8">
							{{ t('review.bidNone') }}
						</div>
						<div class="mt-1 text-xs text-brand-700">{{ t('review.bidChoose') }} →</div>
					</template>
				</button>
			</div>

			<!-- Tabs -->
			<nav class="mt-3 flex gap-6" role="tablist">
				<button
					v-for="tb in tabs"
					:key="tb.key"
					role="tab"
					:aria-selected="tab === tb.key"
					class="-mb-px inline-flex items-center gap-2 border-b-2 pb-2.5 text-sm font-medium"
					:class="
						tab === tb.key
							? 'border-brand-600 text-ink-gray-9'
							: 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'
					"
					@click="tab = tb.key"
				>
					<FeatherIcon :name="tb.icon" class="h-4 w-4" aria-hidden="true" />
					{{ tb.label }}
					<span
						v-if="tb.badge"
						class="rounded-full bg-surface-gray-2 px-1.5 text-xs tabular-nums text-ink-gray-6"
						>{{ tb.badge }}</span
					>
				</button>
			</nav>
		</header>

		<!-- Offer tab -->
		<div v-if="tab === 'bid'" class="min-h-0 flex-1 overflow-auto">
			<BidPanel
				v-if="summary.data"
				:summary="summary.data"
				:tender="name"
				@update="(s) => summary.setData(s)"
			/>
		</div>

		<!-- Positions tab -->
		<div v-show="tab === 'positions'" class="flex min-h-0 flex-1">
			<main
				class="flex min-w-0 flex-col bg-surface-white"
				:class="panelOpen ? 'flex-[7] border-r' : 'flex-1'"
			>
				<!-- Toolbar: quick status filters, search, system, PDF -->
				<div class="flex flex-wrap items-center gap-2 border-b px-5 py-2.5">
					<div
						class="flex flex-wrap items-center gap-1.5"
						role="group"
						:aria-label="t('review.col.status')"
					>
						<button
							class="inline-flex h-7 items-center rounded-full px-3 text-xs font-medium"
							:class="
								!groupFilter
									? 'bg-navy-900 text-white'
									: 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'
							"
							:aria-pressed="!groupFilter"
							@click="groupFilter = ''"
						>
							{{ t('review.filter.all') }}
							<span class="ml-1.5 tabular-nums opacity-70">{{ totalCount }}</span>
						</button>
						<button
							v-for="g in groupCounts"
							:key="g.key"
							class="inline-flex h-7 items-center gap-1 rounded-full px-3 text-xs font-medium ring-1 ring-inset"
							:class="groupFilter === g.key ? CHIP_ACTIVE[g.theme] : CHIP[g.theme]"
							:aria-pressed="groupFilter === g.key"
							:disabled="!g.count"
							@click="filterGroup(groupFilter === g.key ? '' : g.key)"
						>
							<FeatherIcon :name="g.icon" class="h-3 w-3" aria-hidden="true" />
							{{ t(`review.filter.${g.key}`) }}
							<span class="tabular-nums opacity-70">{{ g.count }}</span>
						</button>
					</div>
					<div class="relative ml-auto">
						<FeatherIcon
							name="search"
							class="pointer-events-none absolute left-2 top-1.5 h-4 w-4 text-ink-gray-4"
							aria-hidden="true"
						/>
						<input
							v-model="search"
							type="search"
							:placeholder="t('review.search')"
							:aria-label="t('review.search')"
							class="form-input h-7 w-60 rounded-lg border-outline-gray-2 pl-8 text-sm"
						/>
					</div>
					<select
						v-model="systemFilter"
						class="form-select h-7 max-w-[14rem] rounded-lg border-outline-gray-2 py-0 text-sm"
						:aria-label="t('review.allSystems')"
					>
						<option value="">{{ t('review.allSystems') }}</option>
						<option v-for="s in systems" :key="s" :value="s">{{ s }}</option>
					</select>
					<Button
						:variant="showPdf ? 'subtle' : 'outline'"
						:icon-left="showPdf ? 'eye-off' : 'file-text'"
						:aria-pressed="showPdf"
						@click="setShowPdf(!showPdf)"
						>{{ showPdf ? t('review.hidePdf') : t('review.showPdf') }}</Button
					>
				</div>
				<div
					class="flex items-center justify-between border-b bg-surface-gray-1 px-5 py-1.5 text-xs text-ink-gray-5"
				>
					<span>{{
						t('review.positions', { count: filtered.length }, filtered.length)
					}}</span>
					<span class="tabular-nums">{{
						t('review.filteredTotal', {
							amount: formatCHF(filteredTotal, { digits: 0 }),
						})
					}}</span>
				</div>

				<div class="min-h-0 flex-1 overflow-auto">
					<table class="w-full text-left text-sm">
						<thead
							class="sticky top-0 z-10 bg-surface-white text-xs uppercase tracking-wide text-ink-gray-5 shadow-[0_1px_0_0_rgba(0,0,0,0.06)]"
						>
							<tr>
								<th class="py-2.5 pl-5 pr-3 font-medium">
									{{ t('review.col.lvId') }}
								</th>
								<th class="px-3 py-2.5 font-medium">
									{{ t('review.col.description') }}
								</th>
								<th class="px-3 py-2.5 text-right font-medium">
									{{ t('review.col.quantity') }}
								</th>
								<th class="px-3 py-2.5 font-medium">
									{{ t('review.col.product') }}
								</th>
								<th class="px-3 py-2.5 text-right font-medium">
									{{ t('review.col.directCost') }}
								</th>
								<th class="px-3 py-2.5 font-medium">
									{{ t('review.col.status') }}
								</th>
								<th class="py-2.5 pl-3 pr-5 font-medium">
									{{ t('review.col.source') }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-if="items.loading && !items.data?.length">
								<td colspan="7" class="px-3 py-10 text-center text-ink-gray-5">
									{{ t('review.loadingPositions') }}
								</td>
							</tr>
							<tr v-else-if="!filtered.length">
								<td colspan="7" class="px-3 py-12 text-center">
									<FeatherIcon
										name="filter"
										class="mx-auto mb-2 h-6 w-6 text-ink-gray-4"
										aria-hidden="true"
									/>
									<div class="text-sm text-ink-gray-6">
										{{ t('review.noMatch') }}
									</div>
									<button
										class="mt-2 text-sm text-brand-700 hover:underline"
										@click="clearFilters"
									>
										{{ t('review.clearFilters') }}
									</button>
								</td>
							</tr>
							<tr
								v-for="row in filtered"
								:key="row.name"
								class="cursor-pointer border-l-4 border-t align-top transition-colors"
								:class="[
									STATUS[row.status]?.bar,
									row.name === selected?.name
										? 'bg-brand-50'
										: 'hover:bg-surface-gray-1',
								]"
								tabindex="0"
								@click="select(row)"
								@keydown.enter="select(row)"
							>
								<td class="whitespace-nowrap py-3 pl-4 pr-3">
									<div class="font-mono text-xs text-ink-gray-6">
										{{ row.position_id }}
									</div>
									<div
										v-if="row.golden_lv_id"
										class="mt-1 inline-flex items-center gap-0.5 rounded bg-green-50 px-1.5 text-xs font-medium text-green-700"
										:title="t('review.verifiedReference')"
									>
										<FeatherIcon
											name="check"
											class="h-3 w-3"
											aria-hidden="true"
										/>
										{{ row.golden_lv_id }}
									</div>
								</td>
								<td class="px-3 py-3">
									<div class="line-clamp-2 font-medium text-ink-gray-9">
										{{ row.description }}
									</div>
									<div class="mt-0.5 truncate text-xs text-ink-gray-5">
										{{ row.system }}
									</div>
								</td>
								<td
									class="whitespace-nowrap px-3 py-3 text-right tabular-nums text-ink-gray-8"
								>
									{{ formatQuantity(row.quantity) }}
									<span class="text-ink-gray-5">{{ unitLabel(row.unit) }}</span>
								</td>
								<td class="max-w-[16rem] px-3 py-3">
									<template v-if="row.matched_product">
										<div class="font-mono text-xs text-ink-gray-8">
											{{ row.matched_product }}
										</div>
										<div class="truncate text-xs text-ink-gray-5">
											{{ catalogDescription[row.matched_product] }}
										</div>
									</template>
									<span v-else class="text-ink-gray-4">{{ MISSING }}</span>
								</td>
								<td
									class="whitespace-nowrap px-3 py-3 text-right tabular-nums"
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
											:aria-label="t('review.quoteTitle')"
											class="form-input h-7 w-32 rounded-lg text-right text-sm"
											:class="
												row.quote_override
													? 'border-green-300'
													: 'border-amber-300 bg-amber-50'
											"
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
											class="mt-1 text-xs"
											:class="
												row.quote_override
													? 'text-green-700'
													: 'text-amber-700'
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
									<span
										v-else-if="STATUS[row.status]?.priced"
										class="font-medium text-ink-gray-9"
										>{{ formatCHF(row.direct_cost) }}</span
									>
									<span
										v-else
										class="text-ink-gray-4"
										:title="t('review.noPriceYet')"
										>{{ MISSING }}</span
									>
								</td>
								<td class="px-3 py-3">
									<StatusPill
										:theme="STATUS[row.status]?.theme"
										:icon="STATUS[row.status]?.icon"
										>{{ statusLabel(row.status) }}</StatusPill
									>
								</td>
								<td class="whitespace-nowrap py-3 pl-3 pr-5">
									<button
										class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-blue-3 hover:bg-surface-blue-1"
										:title="t('review.openInPdf')"
										@click.stop="openPdfAt(row)"
									>
										<FeatherIcon
											name="file-text"
											class="h-3.5 w-3.5"
											aria-hidden="true"
										/>
										{{ t('review.page', { page: row.source_page }) }}
									</button>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</main>

			<!-- Traceability -->
			<aside
				v-if="panelOpen"
				class="flex flex-col bg-surface-white"
				:class="showPdf ? 'min-w-[380px] flex-[3]' : 'w-[420px] shrink-0'"
			>
				<div class="flex items-center justify-between gap-2 border-b px-4 py-2">
					<h2 class="text-base font-semibold text-ink-gray-9">
						{{ t('review.traceability') }}
					</h2>
					<Button
						variant="ghost"
						icon="x"
						:aria-label="t('review.closePanel')"
						:title="t('review.closePanel')"
						@click="closePanel"
					/>
				</div>

				<div
					v-if="selected"
					class="overflow-auto border-b bg-surface-gray-1 p-4 text-sm"
					:class="showPdf ? 'max-h-[38%]' : 'min-h-0 flex-1'"
				>
					<!-- What this position is -->
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<div class="flex items-center gap-2 font-mono text-xs text-ink-gray-5">
								{{ selected.position_id }}
								<span
									v-if="selected.golden_lv_id"
									class="inline-flex items-center gap-0.5 rounded bg-green-50 px-1.5 font-sans font-medium text-green-700"
								>
									<FeatherIcon name="check" class="h-3 w-3" aria-hidden="true" />
									{{ selected.golden_lv_id }}
								</span>
							</div>
							<div class="mt-0.5 font-semibold text-ink-gray-9">
								{{ selected.description }}
							</div>
							<div class="mt-0.5 text-xs text-ink-gray-5">
								{{ selected.system }} ·
								<button
									class="text-ink-blue-3 hover:underline"
									@click="openPdfAt(selected)"
								>
									{{ t('review.page', { page: selected.source_page }) }}
								</button>
							</div>
						</div>
						<StatusPill
							:theme="STATUS[selected.status]?.theme"
							:icon="STATUS[selected.status]?.icon"
							>{{ statusLabel(selected.status) }}</StatusPill
						>
					</div>

					<!-- Why it has this status -->
					<div
						class="mt-3 flex gap-2 rounded-lg px-3 py-2"
						:class="
							STATUS[selected.status]?.priced
								? 'bg-surface-white text-ink-gray-7'
								: 'bg-red-50 text-red-800'
						"
					>
						<FeatherIcon
							name="info"
							class="mt-0.5 h-4 w-4 shrink-0 opacity-70"
							aria-hidden="true"
						/>
						<span>{{
							reasonText(
								t,
								selected.reason_code,
								selected.reason_args,
								selected.status_reason,
								familyLabel,
							)
						}}</span>
					</div>
					<p
						v-if="attrs.system_conflict"
						class="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-amber-800"
					>
						{{ t('review.documentConflict') }}: {{ conflictText }}
					</p>
					<p
						v-if="selected.error"
						class="mt-2 rounded-lg bg-red-50 px-3 py-2 text-red-800"
					>
						{{ t('review.technicalError') }}: {{ selected.error }}
					</p>

					<!-- Edit: product and status (a quote is entered in the table) -->
					<section class="mt-3 rounded-xl bg-surface-white p-3 shadow-card">
						<h3
							class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
						>
							<FeatherIcon name="edit-3" class="h-3.5 w-3.5" aria-hidden="true" />
							{{ t('review.section.edit') }}
						</h3>
						<label class="block text-xs text-ink-gray-5">
							{{ t('review.col.product') }}
							<select
								class="form-select mt-0.5 h-8 w-full rounded-lg border-outline-gray-2 py-0 text-sm"
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
						<label class="mt-2 block text-xs text-ink-gray-5">
							{{ t('review.col.status') }}
							<select
								class="form-select mt-0.5 h-8 w-full rounded-lg border-outline-gray-2 py-0 text-sm"
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
						<p
							v-if="lastSave"
							class="mt-2 flex items-center gap-1 text-xs text-green-700"
						>
							<FeatherIcon name="check" class="h-3 w-3" aria-hidden="true" />
							{{ lastSave }}
						</p>
						<ErrorMessage class="mt-2" :message="saveError" />
					</section>

					<!-- Price breakdown -->
					<section class="mt-3 rounded-xl bg-surface-white p-3 shadow-card">
						<h3
							class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
						>
							<FeatherIcon
								name="dollar-sign"
								class="h-3.5 w-3.5"
								aria-hidden="true"
							/>
							{{ t('review.section.price') }}
						</h3>
						<dl class="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1.5">
							<template v-if="selected.family">
								<dt class="text-ink-gray-5">{{ t('review.family') }}</dt>
								<dd class="text-right text-ink-gray-8">
									{{ familyLabel(selected.family) }}
								</dd>
							</template>
							<template v-if="selected.position_ref">
								<dt class="text-ink-gray-5">{{ t('review.positionRef') }}</dt>
								<dd class="text-right font-mono text-xs">
									{{ selected.position_ref }}
								</dd>
							</template>
							<dt class="text-ink-gray-5">{{ t('review.col.quantity') }}</dt>
							<dd class="text-right tabular-nums text-ink-gray-8">
								{{ formatQuantity(selected.quantity) }}
								{{ unitLabel(selected.unit) }}
							</dd>
							<dt class="text-ink-gray-5">{{ t('review.confidence') }}</dt>
							<dd class="text-right tabular-nums text-ink-gray-8">
								{{
									formatPercent(selected.extraction_confidence, { maxDigits: 0 })
								}}
								/
								{{ formatPercent(selected.match_confidence, { maxDigits: 0 }) }}
							</dd>
							<template v-if="STATUS[selected.status]?.priced">
								<dt class="text-ink-gray-5">{{ t('review.material') }}</dt>
								<dd class="text-right tabular-nums text-ink-gray-8">
									{{ formatCHF(selected.material_cost) }}
									<div
										v-if="!selected.quote_override"
										class="text-xs text-ink-gray-5"
									>
										{{
											t('review.materialFormula', {
												quantity: formatQuantity(selected.quantity),
												price: formatCHF(selected.net_unit_cost),
												waste: formatPercent(wasteFraction),
											})
										}}
									</div>
									<div v-else class="text-xs text-green-700">
										{{ t('review.quoted') }}
									</div>
								</dd>
								<dt class="text-ink-gray-5">{{ t('review.labour') }}</dt>
								<dd class="text-right tabular-nums text-ink-gray-8">
									{{ formatCHF(selected.labour_cost) }}
									<div class="text-xs text-ink-gray-5">
										{{
											t('review.labourFormula', {
												hours: formatNumber(selected.labour_hours, {
													maxDigits: 2,
												}),
												rate: formatCHF(selected.labour_rate, {
													digits: 0,
												}),
											})
										}}
									</div>
								</dd>
								<div class="col-span-2 my-0.5 border-t" aria-hidden="true" />
								<dt class="font-medium text-ink-gray-8">
									{{ t('review.col.directCost') }}
								</dt>
								<dd
									class="text-right text-base font-semibold tabular-nums text-ink-gray-9"
								>
									{{ formatCHF(selected.direct_cost) }}
								</dd>
							</template>
						</dl>
					</section>

					<!-- Printed attributes (source evidence, never translated) -->
					<section class="mt-3 rounded-xl bg-surface-white p-3 shadow-card">
						<h3
							class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
						>
							<FeatherIcon name="list" class="h-3.5 w-3.5" aria-hidden="true" />
							{{ t('review.customAttributes') }}
						</h3>
						<table v-if="customRows.length" class="w-full text-xs">
							<tr
								v-for="[label, value] in customRows"
								:key="label"
								class="border-t first:border-t-0"
							>
								<td class="w-1/3 py-1 pr-2 text-ink-gray-5">{{ label }}</td>
								<td class="py-1 text-ink-gray-8">{{ value }}</td>
							</tr>
						</table>
						<p v-else class="text-xs text-ink-gray-4">
							{{ t('review.noCustomAttributes') }}
						</p>
					</section>

					<!-- What the LLM answered (model text is English and shown as returned) -->
					<section
						v-if="llmAnswer"
						class="mt-3 rounded-xl bg-surface-white p-3 shadow-card"
					>
						<h3
							class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
						>
							<FeatherIcon name="cpu" class="h-3.5 w-3.5" aria-hidden="true" />
							{{ t('review.llmAnswer', { by: t(`review.matchedBy.${matchedBy}`) }) }}
						</h3>
						<div class="text-ink-gray-8">
							<span class="font-mono text-xs">{{
								llmAnswer.product_id || t('review.llmNoProduct')
							}}</span>
							<span class="ml-1 text-xs text-ink-gray-5"
								>({{ t(`review.fit.${llmAnswer.fit}`) }})</span
							>
						</div>
						<div
							v-if="llmAnswer.note"
							class="mt-1 text-xs italic text-ink-gray-6"
							lang="en"
						>
							{{ llmAnswer.note }}
						</div>
					</section>
				</div>
				<div
					v-else
					class="flex items-center gap-2 border-b px-4 py-4 text-sm text-ink-gray-5"
				>
					<FeatherIcon name="mouse-pointer" class="h-4 w-4" aria-hidden="true" />
					{{ t('review.selectHint') }}
				</div>

				<div v-if="showPdf" class="min-h-0 flex-1">
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
		<DeleteTenderDialog
			v-model="showDelete"
			:tender="tender.doc ? { name, project_name: tender.doc.project_name } : null"
			@deleted="() => router.push('/')"
		/>
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
	Dialog,
	Dropdown,
	ErrorMessage,
	FeatherIcon,
	createDocumentResource,
	createListResource,
	createResource,
} from 'frappe-ui'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import BidPanel from '@/components/BidPanel.vue'
import DeleteTenderDialog from '@/components/DeleteTenderDialog.vue'
import PdfViewer from '@/components/PdfViewer.vue'
import StatusPill from '@/components/StatusPill.vue'
import ProcessingOverlay from '@/components/ProcessingOverlay.vue'
import { currentLocale } from '@/i18n'
import { api, errorText } from '@/utils/api'
import {
	STATUS,
	STATUS_CODES,
	STATUS_GROUPS,
	TENDER_ICON,
	TENDER_STATUS,
	UNIT_CODES,
} from '@/utils/codes'
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

// Filters: quick status groups (chips), search, system.
const search = ref('')
const groupFilter = ref('')
const systemFilter = ref('')
const groupOf: Record<string, string> = Object.fromEntries(
	STATUS_GROUPS.flatMap((g) => g.statuses.map((st) => [st, g.key])),
)
const systems = computed(() =>
	[...new Set((items.data || []).map((i: any) => i.system).filter(Boolean))].sort(),
)
const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	return (items.data || []).filter((i: any) => {
		if (groupFilter.value && groupOf[i.status] !== groupFilter.value) return false
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
const totalCount = computed(() => items.data?.length || 0)
const groupCounts = computed(() =>
	STATUS_GROUPS.map((g) => ({
		...g,
		count: (items.data || []).filter((i: any) => g.statuses.includes(i.status)).length,
	})),
)
function filterGroup(key: string) {
	tab.value = 'positions'
	groupFilter.value = key
}
function clearFilters() {
	groupFilter.value = ''
	systemFilter.value = ''
	search.value = ''
}
const CHIP: Record<string, string> = {
	red: 'bg-red-50 text-red-700 ring-red-200 hover:bg-red-100',
	orange: 'bg-amber-50 text-amber-700 ring-amber-200 hover:bg-amber-100',
	blue: 'bg-blue-50 text-blue-700 ring-blue-200 hover:bg-blue-100',
	green: 'bg-green-50 text-green-700 ring-green-200 hover:bg-green-100',
	gray: 'bg-gray-50 text-gray-600 ring-gray-200 hover:bg-gray-100',
}
const CHIP_ACTIVE: Record<string, string> = {
	red: 'bg-red-600 text-white ring-red-600',
	orange: 'bg-amber-500 text-white ring-amber-500',
	blue: 'bg-blue-600 text-white ring-blue-600',
	green: 'bg-green-600 text-white ring-green-600',
	gray: 'bg-gray-600 text-white ring-gray-600',
}

// Overview: how far the review is, by number of positions (and value where there is one).
// Each group opens the matching quick filter in the table.
const progressGroups = computed(() => {
	const by = summary.data?.by_status || {}
	const sum = (codes: string[], field: 'positions' | 'direct_cost') =>
		codes.reduce((s, c) => s + (by[c]?.[field] || 0), 0)
	return [
		{
			key: 'calculated',
			filter: 'calculated',
			codes: ['calculated'],
			bar: 'bg-green-500',
			value: true,
		},
		{
			key: 'provisional',
			filter: 'quote',
			codes: ['supplier_quote_required', 'assumption_applied'],
			bar: 'bg-amber-400',
			value: true,
		},
		{
			key: 'open',
			filter: 'open',
			codes: ['review_required', 'insufficient_information'],
			bar: 'bg-red-500',
			value: false,
		},
	].map((g) => ({
		key: g.key,
		filter: g.filter,
		bar: g.bar,
		label: t(`review.group.${g.key}`),
		count: sum(g.codes, 'positions'),
		value: g.value ? sum(g.codes, 'direct_cost') : null,
	}))
})

// The open tab is part of the URL (?tab=bid), so a link or reload keeps it.
const route = useRoute()
const router = useRouter()
const tab = ref<'positions' | 'bid'>(route.query.tab === 'bid' ? 'bid' : 'positions')
watch(tab, (value) =>
	router.replace({ query: { ...route.query, tab: value === 'bid' ? 'bid' : undefined } }),
)
const tabs = computed(() => [
	{
		key: 'positions',
		icon: 'list',
		label: t('review.tab.positions'),
		badge: totalCount.value || '',
	},
	{ key: 'bid', icon: 'award', label: t('review.tab.bid'), badge: '' },
])
const moreActions = computed(() => [
	{ label: t('review.reprocess'), icon: 'refresh-cw', onClick: () => reprocess() },
	{ label: t('delete.title'), icon: 'trash-2', onClick: () => (showDelete.value = true) },
])
const showDelete = ref(false)

const catalogDescription = computed<Record<string, string>>(() =>
	Object.fromEntries((catalog.data || []).map((c: any) => [c.name, c.description])),
)

// Selection and traceability
const selected = ref<any>(null)
const activePage = ref(1)
function select(row: any) {
	selected.value = row
	activePage.value = row.source_page
}

// PDF preview is optional (off by default); the choice is remembered in this browser.
const PDF_KEY = 'equans_bid.showPdf'
function readShowPdf() {
	try {
		return window.localStorage.getItem(PDF_KEY) === '1'
	} catch {
		return false
	}
}
const showPdf = ref(readShowPdf())
function setShowPdf(value: boolean) {
	showPdf.value = value
	try {
		window.localStorage.setItem(PDF_KEY, value ? '1' : '0')
	} catch {
		// storage blocked (private mode): the choice lasts for this page only
	}
}
function openPdfAt(row: any) {
	select(row)
	setShowPdf(true)
}
// The side panel takes space only when it shows something: the PDF, or a selected position.
const panelOpen = computed(() => showPdf.value || !!selected.value)
function closePanel() {
	selected.value = null
	setShowPdf(false)
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
// While it runs the screen is frozen (ProcessingOverlay); it is released only once the new
// positions and totals are loaded, so the estimator never sees half-updated results.
const reprocessing = ref(false)
const loadingResults = ref(false)
const busy = computed(
	() => tender.doc?.status === 'Processing' || reprocessing.value || loadingResults.value,
)
let timer: ReturnType<typeof setInterval> | null = null
function poll() {
	if (timer) return
	timer = setInterval(async () => {
		await tender.reload()
		if (tender.doc?.status !== 'Processing') {
			clearInterval(timer!)
			timer = null
			loadingResults.value = true
			reprocessing.value = false
			selected.value = null
			try {
				await Promise.all([items.reload(), summary.reload()])
			} finally {
				loadingResults.value = false
			}
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
	try {
		await api('equans_bid.api.start_processing', { tender: props.name })
		await tender.reload()
		poll()
	} catch (e) {
		reprocessing.value = false
		throw e
	}
}
onBeforeUnmount(() => timer && clearInterval(timer))
</script>
