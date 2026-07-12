<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDocuments } from '../composables/useDocuments'
import DocumentPanel from '../components/DocumentPanel.vue'

const route = useRoute()
const router = useRouter()

const kbId = computed(() => (route.params.kbId as string) || '')

const docs = useDocuments(kbId)

watch(
  () => route.params.kbId,
  async (id) => {
    const idStr = (id as string) || ''
    if (!idStr) return
    await docs.load()
  },
  { immediate: true },
)

onUnmounted(() => docs.stopPolling())
</script>

<template>
  <div class="workspace-nav">
    <a-button type="text" @click="router.push(`/${kbId}`)">
      ← 返回问答
    </a-button>
    <span class="workspace-nav-title">文档管理</span>
  </div>

  <DocumentPanel
    :documents="docs.documents.value"
    :filtered="docs.filtered.value"
    :selectedKnowledgeBase="null"
    :selectedKnowledgeBaseId="kbId"
    :loading="docs.loading.value"
    :busyId="docs.busyId.value"
    :documentSearch="docs.documentSearch.value"
    :documentFilter="docs.documentFilter.value"
    :documentPage="docs.documentPage.value"
    :documentPageSize="docs.documentPageSize"
    :documentTotal="docs.documentTotal.value"
    :selectedIds="docs.selectedIds.value"
    :uploadZoneVisible="docs.uploadZoneVisible.value"
    :batchParsing="docs.batchParsing.value"
    :batchIndexing="docs.batchIndexing.value"
    :reindexingAll="docs.reindexingAll.value"
    :filterOptions="docs.filterOptions.value"
    :selectAll="docs.selectAll.value"
    :indexedCount="docs.indexedCount.value"
    @update:documentSearch="(v: string) => docs.documentSearch.value = v"
    @update:documentFilter="(v: string) => docs.documentFilter.value = v"
    @update:uploadZoneVisible="(v: boolean) => docs.uploadZoneVisible.value = v"
    @update:selectAll="(v: boolean) => docs.selectAll.value = v"
    @refresh="docs.load"
    @goPage="(p: number) => docs.goPage(p)"
    @toggleSelect="(id: string) => docs.toggleSelect(id)"
    @parseDocument="(d: any) => docs.parseDocument(d)"
    @indexDocument="(d: any) => docs.indexDocument(d)"
    @removeDocument="(d: any) => docs.removeDocument(d)"
    @parsePending="docs.parsePending"
    @indexPending="docs.indexPending"
    @reindexAll="docs.reindexAll"
    @batchParse="docs.batchParse"
    @batchIndex="docs.batchIndex"
    @cancelSelect="docs.selectedIds.value = new Set()"
  />
</template>
