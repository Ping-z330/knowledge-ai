<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDocuments } from '../composables/useDocuments'
import { useQA } from '../composables/useQA'
import { useConversation } from '../composables/useConversation'
import DocumentPanel from '../components/DocumentPanel.vue'
import DebugPanel from '../components/DebugPanel.vue'
import type { QuestionAnswer } from '../types'

const route = useRoute()

// kbId 从 URL 参数派生，作为 composables 的输入
const kbId = computed(() => (route.params.kbId as string) || '')

// 每个知识库页面拥有独立的 composable 实例
const docs = useDocuments(kbId)
const qa = useQA(kbId, docs.indexedCount)
const conv = useConversation(kbId, docs.indexedCount)

// URL 参数变化时加载数据（支持浏览器前进/后退、刷新）
watch(
  () => route.params.kbId,
  async (id) => {
    const idStr = (id as string) || ''
    if (!idStr) return
    qa.answer.value = null
    qa.retrievalResults.value = []
    qa.questionError.value = ''
    qa.qaPage.value = 1
    await docs.load()
    await qa.loadHistory()
  },
  { immediate: true },
)

const selectHistoryItem = (item: QuestionAnswer) => {
  qa.selectHistoryItem(item)
  qa.qaActiveTab.value = 'debug'
}

onUnmounted(() => docs.stopPolling())
</script>

<template>
  <div class="main-grid">
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

    <div class="qa-column">
      <DebugPanel
        :selectedKnowledgeBaseId="kbId"
        :selectedKnowledgeBase="null"
        :indexedCount="docs.indexedCount.value"
        :question="qa.question.value"
        :questionError="qa.questionError.value"
        :answer="qa.answer.value"
        :retrievalResults="qa.retrievalResults.value"
        :questionAnswers="qa.questionAnswers.value"
        :topK="qa.topK.value"
        :asking="qa.asking.value"
        :streaming="qa.streaming.value"
        :streamingAnswer="qa.streamingAnswer.value"
        :retrieving="qa.retrieving.value"
        :currentAnswerId="qa.currentAnswerId.value"
        :currentAnswerRating="qa.currentAnswerRating.value"
        :ratingSubmitting="qa.ratingSubmitting.value"
        :loadingHistory="qa.loadingHistory.value"
        :busyAnswerId="qa.busyAnswerId.value"
        :qaActiveTab="qa.qaActiveTab.value"
        :qaPage="qa.qaPage.value"
        :qaPageSize="qa.qaPageSize"
        :qaTotal="qa.qaTotal.value"
        :citedVectorIds="qa.citedVectorIds.value"
        :retrievalSummary="qa.retrievalSummary.value"
        :retrievalQuery="qa.retrievalQuery.value"
        :conversation="conv.conversation.value"
        :convInput="conv.input.value"
        :convAsking="conv.asking.value"
        :convStreaming="conv.streaming.value"
        :convStreamingAnswer="conv.streamingAnswer.value"
        :convMessagesRef="conv.messagesRef.value"
        @update:question="(v: string) => qa.question.value = v"
        @update:topK="(v: number) => qa.topK.value = v"
        @update:qaActiveTab="(v: string) => qa.qaActiveTab.value = v"
        @retrieve="qa.retrieveOnly"
        @ask="qa.askQuestion"
        @submitRating="(id: string, r: number) => qa.submitRating(id, r)"
        @selectHistoryItem="selectHistoryItem"
        @deleteHistoryItem="(item: any) => qa.deleteHistoryItem(item)"
        @refreshHistory="qa.loadHistory"
        @goQaPage="(p: number) => qa.goQaPage(p)"
        @update:convInput="(v: string) => conv.input.value = v"
        @convAsk="conv.ask"
        @convClear="conv.clear"
        @convSubmitRating="(id: string, r: number) => conv.updateLocalRating(id, r)"
      />
    </div>
  </div>
</template>
