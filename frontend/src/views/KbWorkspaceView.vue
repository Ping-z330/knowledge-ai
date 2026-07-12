<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDocuments } from '../composables/useDocuments'
import { useQA } from '../composables/useQA'
import { useConversation } from '../composables/useConversation'
import DebugPanel from '../components/DebugPanel.vue'
import { api } from '../utils/api'
import type { Conversation } from '../types'

const route = useRoute()
const router = useRouter()

const kbId = computed(() => (route.params.kbId as string) || '')

const docs = useDocuments(kbId)
const qa = useQA(kbId, docs.indexedCount)

const topK = ref(5)
const agenticMode = ref(false)
const enableWebSearch = ref(false)

const conv = useConversation(kbId, docs.indexedCount, topK, agenticMode, enableWebSearch)

// KB 切换时加载文档
watch(
  () => route.params.kbId,
  async (id) => {
    if (!id) return
    await docs.load()
  },
  { immediate: true },
)

const selectConversation = (item: Conversation) => {
  conv.loadConversation(item.id)
  qa.qaActiveTab.value = 'conversation'
}

const newConversation = () => {
  conv.clear()
  qa.qaActiveTab.value = 'conversation'
}

const deleteConversation = async (item: Conversation) => {
  const kbIdVal = kbId.value
  if (!kbIdVal) return
  try {
    await api.delete(`/knowledge-bases/${kbIdVal}/conversations/${item.id}`)
    if (conv.conversationId.value === item.id) {
      conv.clear()
    } else {
      conv.loadConversations()
    }
  } catch { /* ignore */ }
}

onUnmounted(() => docs.stopPolling())
</script>

<template>
  <div class="workspace-nav">
    <span class="workspace-nav-title">问答</span>
    <a-button type="text" @click="router.push(`/${kbId}/documents`)">
      管理文档 →
    </a-button>
  </div>

  <DebugPanel
    :selectedKnowledgeBaseId="kbId"
    :indexedCount="docs.indexedCount.value"
    :qaActiveTab="qa.qaActiveTab.value"
    :conversation="conv.conversation.value"
    :convInput="conv.input.value"
    :convAsking="conv.asking.value"
    :convStreaming="conv.streaming.value"
    :convStreamingAnswer="conv.streamingAnswer.value"
    :convMessagesRef="conv.messagesRef.value"
    :topK="topK"
    :agenticMode="agenticMode"
    :enableWebSearch="enableWebSearch"
    :agenticStatus="conv.agenticStatus.value"
    :agenticRounds="conv.agenticRounds.value"
    :agenticScore="conv.agenticScore.value"
    :agenticSubQueries="conv.agenticSubQueries.value"
    :conversations="conv.conversations.value"
    :conversationId="conv.conversationId.value"
    :loadingConversations="conv.loadingConversations.value"
    @update:qaActiveTab="(v: string) => qa.qaActiveTab.value = v"
    @update:agenticMode="(v: boolean) => agenticMode = v"
    @update:enableWebSearch="(v: boolean) => enableWebSearch = v"
    @selectConversation="selectConversation"
    @deleteConversation="deleteConversation"
    @refreshConversations="conv.loadConversations"
    @update:convInput="(v: string) => conv.input.value = v"
    @update:topK="(v: number) => topK = v"
    @convAsk="conv.ask"
    @convClear="conv.clear"
    @convSubmitRating="(id: string, r: number) => conv.updateLocalRating(id, r)"
    @convSwitchConversation="(id: string) => conv.loadConversation(id)"
    @convNewConversation="newConversation"
    @convDeleteConversation="(id: string) => deleteConversation({ id } as Conversation)"
  />
</template>
