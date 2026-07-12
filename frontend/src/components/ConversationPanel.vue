<script setup lang="ts">
import { ref } from 'vue'
import {
  FileTextOutlined, SendOutlined, ThunderboltOutlined,
} from '@ant-design/icons-vue'
import type { ConversationMessage } from '../types'
import { renderAnswerWithCitations, handleCitationClick, highlightSourceCitation, clearSourceCitation, extractCitedIds } from '../utils/citations'
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
  topK: number
  agenticMode: boolean
  enableWebSearch: boolean
  agenticStatus: string
  agenticRounds: number
  agenticScore: number | null
  agenticSubQueries: string[]
}>()

const emit = defineEmits<{
  'update:input': [value: string]
  'update:topK': [value: number]
  'update:agenticMode': [value: boolean]
  'update:enableWebSearch': [value: boolean]
  ask: []
  clear: []
  submitRating: [answerId: string, rating: number]
}>()

const expandedSources = ref<Set<string>>(new Set())

const toggleSources = (msgId: string) => {
  const s = new Set(expandedSources.value)
  if (s.has(msgId)) s.delete(msgId)
  else s.add(msgId)
  expandedSources.value = s
}

const citedOnly = (msg: ConversationMessage) => {
  if (!msg.content) return msg.sources
  const used = extractCitedIds(msg.content)
  if (used.size === 0) return msg.sources
  return msg.sources.filter((s) => used.has(s.citation))
}

const submitRating = async (answerId: string, rating: number, kbId: string) => {
  if (!answerId) return
  try {
    await api.patch(`/knowledge-bases/${kbId}/question-answers/${answerId}/rating`, { rating })
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="conversation-box">
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
          <div class="conv-sources-toggle" @click="toggleSources(msg.id)">
            <FileTextOutlined />
            <span>引用来源 · {{ citedOnly(msg).length }}/{{ msg.sources.length }}</span>
            <span class="conv-sources-arrow">{{ expandedSources.has(msg.id) ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expandedSources.has(msg.id)" class="sources-list conv-sources-list">
            <article
              v-for="source in citedOnly(msg)"
              :key="source.vector_id"
              class="source-card"
              :data-source-citation="source.citation"
              @mouseenter="highlightSourceCitation"
              @mouseleave="clearSourceCitation"
            >
              <div class="source-card-head">
                <a-tag color="blue" size="small">[{{ source.citation }}]</a-tag>
                <span class="source-card-score" v-if="source.score">{{ source.score.toFixed(2) }}</span>
              </div>
              <p class="source-card-filename">{{ source.metadata.filename || source.metadata.source_label || '未知来源' }}</p>
              <p class="source-card-text">{{ source.text.slice(0, 120) }}{{ source.text.length > 120 ? '...' : '' }}</p>
            </article>
          </div>
        </div>
      </div>

      <div v-if="streaming" class="conv-bubble assistant">
        <div class="conv-role">Assistant <span class="streaming-dot"></span></div>
        <div class="conv-content"><p v-html="renderAnswerWithCitations(streamingAnswer)"></p></div>
      </div>
    </div>

    <div class="conv-input-area">
      <div class="conv-controls">
        <div class="conv-controls-left">
          <span class="toolbar-label">Top-K</span>
          <a-input-number :value="topK" :min="1" :max="20" size="small"
            @update:value="(v: number) => emit('update:topK', v)" />
          <a-divider type="vertical" />
          <a-tooltip title="Agentic 模式：Agent 自主分析查询、评估检索质量、必要时改写重试">
            <a-switch
              :checked="agenticMode" checked-children="Agentic" un-checked-children="标准"
              size="small"
              @change="(v: boolean) => emit('update:agenticMode', v)"
            />
          </a-tooltip>
          <a-checkbox
            v-if="agenticMode"
            :checked="enableWebSearch"
            @change="(e: any) => emit('update:enableWebSearch', e.target.checked)"
          >
            Web 搜索回退
          </a-checkbox>
        </div>
      </div>

      <div class="conv-input-row">
        <a-textarea
          :value="input" :rows="2" placeholder="输入问题…" :disabled="asking"
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

      <div v-if="agenticMode && asking && agenticStatus" class="agentic-status">
        <a-tag color="processing"><ThunderboltOutlined /> {{ agenticStatus }}</a-tag>
        <span v-if="agenticRounds > 0" class="agentic-detail">
          {{ agenticRounds }} 轮检索 · 评分 {{ agenticScore ?? '?' }}/5
          <span v-if="agenticSubQueries.length"> · 子查询: {{ agenticSubQueries.join(' | ') }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.conv-input-area {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e3e9e5;
}
.conv-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.conv-controls-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.conv-controls-left .toolbar-label {
  font-weight: 640;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #65726c;
}
.conv-sources-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
  font-size: 12px;
  color: #2f6f5e;
  cursor: pointer;
  user-select: none;
  font-weight: 640;
}
.conv-sources-toggle:hover {
  color: #1b4d3e;
}
.conv-sources-arrow {
  font-size: 10px;
  margin-left: 2px;
}
.conv-sources-list {
  margin-top: 6px;
  max-height: 320px;
  overflow-y: auto;
}
</style>
