<template>
	<div class="flex h-screen flex-col bg-surface-gray-1">
		<AppHeader />
		<div class="min-h-0 flex-1">
			<router-view />
		</div>
	</div>
</template>

<script setup lang="ts">
import AppHeader from '@/components/AppHeader.vue'
</script>
