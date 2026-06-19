<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import type { QuestionAnswer } from './types'
import { useKnowledgeBases } from './composables/useKnowledgeBases'
import { useDocuments } from './composables/useDocuments'
import { useQA } from './composables/useQA'
import { useConversation } from './composables/useConversation'
import Sidebar from './components/Sidebar.vue'
import WelcomeCard from './components/WelcomeCard.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import DebugPanel from './components/DebugPanel.vue'
import ConversationPanel from './components/ConversationPanel.vue'

const kb = useKnowledgeBases()
const docs = useDocuments(kb.selectedId)
const qa = useQA(kb.selectedId, docs.indexedCount)
const conv = useConversation(kb.selectedId, docs.indexedCount)

const selectKb = async (id: string) => {
  kb.selectedId.value = id
  qa.answer.value = null
  qa.retrievalResults.value = []
  qa.questionError.value = ''
  qa.qaPage.value = 1
  await docs.load()
  await qa.loadHistory()
}

const createKb = async () => {
  const data = await kb.create()
  if (data) {
    await docs.load()
    await qa.loadHistory()
  }
}

const selectHistoryItem = (item: QuestionAnswer) => {
  qa.selectHistoryItem(item)
  qa.qaActiveTab.value = 'debug'
}

onMounted(() => kb.load())
onUnmounted(() => docs.stopPolling())
</script>

<template>
  <a-config-provider
    :theme="{
      token: {
        colorPrimary: '#2f6f5e',
        borderRadius: 6,
        fontFamily: 'Aptos, Segoe UI, sans-serif',
      },
    }"
  >
    <main class="shell">
      <Sidebar
        :knowledgeBases="kb.knowledgeBases.value"
        :filtered="kb.filtered.value"
        :selectedId="kb.selectedId.value"
        :loading="kb.loading.value"
        :creating="kb.creating.value"
        :kbSearch="kb.kbSearch.value"
        :createForm="kb.createForm.value"
        @update:kbSearch="(v: string) => kb.kbSearch.value = v"
        @update:createForm="(v: { name: string; description: string }) => kb.createForm.value = v"
        @select="selectKb"
        @create="createKb"
        @remove="kb.remove"
        @refresh="kb.load"
      />

      <section class="workspace">
        <WelcomeCard v-if="!kb.knowledgeBases.value.length && !kb.loading.value" />

        <template v-if="kb.selectedId.value">
          <header class="workspace-head">
            <div>
              <p class="eyebrow">RAG Pipeline</p>
              <h2>{{ kb.selected.value?.name || '选择一个知识库' }}</h2>
              <p class="muted">{{ kb.selected.value?.description || '上传文档后完成解析和索引，再开始问答。' }}</p>
            </div>
            <div class="metrics">
              <div><strong>{{ docs.documents.value.length }}</strong><span>文档</span></div>
              <div><strong>{{ docs.parsedCount.value }}</strong><span>已解析</span></div>
              <div><strong>{{ docs.indexedCount.value }}</strong><span>已索引</span></div>
            </div>
          </header>

          <div class="main-grid">
            <DocumentPanel
              :documents="docs.documents.value"
              :filtered="docs.filtered.value"
              :selectedKnowledgeBase="kb.selected.value"
              :selectedKnowledgeBaseId="kb.selectedId.value"
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
                :selectedKnowledgeBaseId="kb.selectedId.value"
                :selectedKnowledgeBase="kb.selected.value"
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
              />

              <ConversationPanel
                :selectedKnowledgeBaseId="kb.selectedId.value"
                :indexedCount="docs.indexedCount.value"
                :conversation="conv.conversation.value"
                :input="conv.input.value"
                :asking="conv.asking.value"
                :streaming="conv.streaming.value"
                :streamingAnswer="conv.streamingAnswer.value"
                :messagesRef="conv.messagesRef.value"
                @update:input="(v: string) => conv.input.value = v"
                @ask="conv.ask"
                @clear="conv.clear"
                @submitRating="(id: string, r: number) => conv.updateLocalRating(id, r)"
              />
            </div>
          </div>
        </template>
      </section>
    </main>
  </a-config-provider>
</template>
