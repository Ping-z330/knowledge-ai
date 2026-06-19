<script setup lang="ts">
import { SendOutlined } from '@ant-design/icons-vue'
import type { ConversationMessage } from '../types'
import { renderAnswerWithCitations, handleCitationClick } from '../utils/citations'
import { api } from '../utils/api'

defineProps<{
  selectedKnowledgeBaseId: string
  indexedCount: number
  conversation: ConversationMessage[]
  input: string
  asking: boolean
  streaming: boolean
  streamingAnswer: string
  messagesRef: HTMLElement | null
}>()

const emit = defineEmits<{
  'update:input': [value: string]
  ask: []
  clear: []
  submitRating: [answerId: string, rating: number]
}>()

const submitRating = async (answerId: string, rating: number, kbId: string) => {
  if (!answerId) return
  try {
    await api.patch(`/knowledge-bases/${kbId}/question-answers/${answerId}/rating`, { rating })
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="conversation-box">
    <div class="conv-toolbar">
      <span class="conv-count" v-if="conversation.length">{{ conversation.length }} 条消息</span>
      <a-button size="small" :disabled="!conversation.length && !streaming" @click="emit('clear')">清空对话</a-button>
    </div>

    <div class="conv-messages" ref="messagesRef">
      <a-empty v-if="!conversation.length && !streaming" description="开始多轮对话，LLM 会记住前面的上下文" />

      <div v-for="msg in conversation" :key="msg.id" class="conv-bubble" :class="msg.role">
        <div class="conv-role">{{ msg.role === 'user' ? '你' : 'Assistant' }}</div>
        <div class="conv-content">
          <p v-if="msg.role === 'user'">{{ msg.content }}</p>
          <p v-else v-html="renderAnswerWithCitations(msg.content)" @click="handleCitationClick"></p>
        </div>

        <div v-if="msg.role === 'assistant' && msg.answerId" class="conv-rating">
          <button class="conv-rating-btn" :class="{ active: msg.rating === 1 }" :disabled="asking"
            @click="submitRating(msg.answerId, 1, selectedKnowledgeBaseId); msg.rating = 1">👍</button>
          <button class="conv-rating-btn" :class="{ active: msg.rating === -1 }" :disabled="asking"
            @click="submitRating(msg.answerId, -1, selectedKnowledgeBaseId); msg.rating = -1">👎</button>
        </div>

        <div v-if="msg.role === 'assistant' && msg.sources.length" class="conv-sources">
          <a-collapse :bordered="false">
            <a-collapse-panel :header="`引用来源 (${msg.sources.length} 条)`">
              <div v-for="source in msg.sources" :key="source.vector_id"
                class="conv-source-item" :data-source-citation="source.citation"
              >
                <a-tag color="blue">[{{ source.citation }}]</a-tag>
                <span>{{ source.metadata.filename || source.metadata.source_label }}</span>
                <small v-if="source.score">score {{ source.score.toFixed(3) }}</small>
                <p>{{ source.text }}</p>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </div>
      </div>

      <div v-if="streaming" class="conv-bubble assistant">
        <div class="conv-role">Assistant <span class="streaming-dot"></span></div>
        <div class="conv-content"><p v-html="renderAnswerWithCitations(streamingAnswer)"></p></div>
      </div>
    </div>

    <div class="conv-input-row">
      <a-textarea
        :value="input" :rows="2" placeholder="输入追问…" :disabled="asking"
        @update:value="emit('update:input', $event)"
        @pressEnter="emit('ask')"
      />
      <a-button type="primary" :loading="asking"
        :disabled="!selectedKnowledgeBaseId || !input.trim() || indexedCount === 0"
        @click="emit('ask')"
      >
        <template #icon><SendOutlined /></template>
      </a-button>
    </div>
  </div>
</template>
