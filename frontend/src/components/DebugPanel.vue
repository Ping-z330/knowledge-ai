<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { CheckCircleOutlined } from '@ant-design/icons-vue'
import type { Conversation, ConversationMessage } from '../types'

const HistoryPanel = defineAsyncComponent(() => import('./HistoryPanel.vue'))
const ConversationPanel = defineAsyncComponent(() => import('./ConversationPanel.vue'))

defineProps<{
  selectedKnowledgeBaseId: string
  indexedCount: number
  qaActiveTab: string
  // Conversation
  conversation: ConversationMessage[]
  convInput: string
  convAsking: boolean
  convStreaming: boolean
  convStreamingAnswer: string
  convMessagesRef: HTMLElement | null
  // Agentic controls
  topK: number
  agenticMode: boolean
  enableWebSearch: boolean
  agenticStatus: string
  agenticRounds: number
  agenticScore: number | null
  agenticSubQueries: string[]
  conversations: Conversation[]
  conversationId: string
  loadingConversations: boolean
}>()

const emit = defineEmits<{
  'update:qaActiveTab': [value: string]
  'update:agenticMode': [value: boolean]
  'update:enableWebSearch': [value: boolean]
  selectConversation: [item: Conversation]
  deleteConversation: [item: Conversation]
  refreshConversations: []
  // Conversation
  'update:convInput': [value: string]
  'update:topK': [value: number]
  convAsk: []
  convClear: []
  convSubmitRating: [answerId: string, rating: number]
  convSwitchConversation: [convId: string]
  convNewConversation: []
  convDeleteConversation: [convId: string]
}>()
</script>

<template>
  <section class="panel qa-panel">
    <div class="panel-head">
      <div>
        <h3>问答面板</h3>
        <p>提问后查看回答、引用来源与检索命中详情</p>
      </div>
      <a-tag color="success" v-if="indexedCount > 0">
        <CheckCircleOutlined /> ready
      </a-tag>
    </div>

    <a-tabs :activeKey="qaActiveTab" class="qa-tabs" @update:activeKey="emit('update:qaActiveTab', $event)">
      <a-tab-pane key="conversation" tab="对话">
        <ConversationPanel
          :selectedKnowledgeBaseId="selectedKnowledgeBaseId"
          :indexedCount="indexedCount"
          :conversation="conversation"
          :input="convInput"
          :asking="convAsking"
          :streaming="convStreaming"
          :streamingAnswer="convStreamingAnswer"
          :messagesRef="convMessagesRef"
          :topK="topK"
          :agenticMode="agenticMode"
          :enableWebSearch="enableWebSearch"
          :agenticStatus="agenticStatus"
          :agenticRounds="agenticRounds"
          :agenticScore="agenticScore"
          :agenticSubQueries="agenticSubQueries"
          @update:input="(v: string) => emit('update:convInput', v)"
          @update:topK="(v: number) => emit('update:topK', v)"
          @update:agenticMode="(v: boolean) => emit('update:agenticMode', v)"
          @update:enableWebSearch="(v: boolean) => emit('update:enableWebSearch', v)"
          @ask="emit('convAsk')"
          @clear="emit('convClear')"
          @submitRating="(id: string, r: number) => emit('convSubmitRating', id, r)"
        />
      </a-tab-pane>

      <a-tab-pane key="history" tab="对话记录">
        <HistoryPanel
          :conversations="conversations"
          :loading="loadingConversations"
          :conversationId="conversationId"
          @select="(conv: any) => emit('selectConversation', conv)"
          @delete="(conv: any) => emit('deleteConversation', conv)"
          @refresh="emit('refreshConversations')"
          @newConversation="emit('convNewConversation')"
        />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>
