<script setup lang="ts">
import {
  ApiOutlined, CheckCircleOutlined, CloudUploadOutlined,
  SearchOutlined, SendOutlined,
} from '@ant-design/icons-vue'
import type { AnswerSource, QuestionAnswer, RetrievalResult, KnowledgeBase } from '../types'
import { renderAnswerWithCitations, handleCitationClick, highlightSourceCitation, clearSourceCitation } from '../utils/citations'
import { getResultTitle, getResultSubtitle, getResultFilename, getResultSectionTitle, getResultChunkLabel } from '../utils/retrieval'
import { scoreColor, scoreBarWidth, highlightText } from '../utils/citations'
import HistoryPanel from './HistoryPanel.vue'

defineProps<{
  selectedKnowledgeBaseId: string
  selectedKnowledgeBase: KnowledgeBase | null
  indexedCount: number
  question: string
  questionError: string
  answer: { question: string; answer: string; sources: AnswerSource[] } | null
  retrievalResults: RetrievalResult[]
  questionAnswers: QuestionAnswer[]
  topK: number
  asking: boolean
  streaming: boolean
  streamingAnswer: string
  retrieving: boolean
  currentAnswerId: string
  currentAnswerRating: number | null
  ratingSubmitting: boolean
  loadingHistory: boolean
  busyAnswerId: string
  qaActiveTab: string
  qaPage: number
  qaPageSize: number
  qaTotal: number
  citedVectorIds: Set<string>
  retrievalSummary: string
  retrievalQuery: string
}>()

const emit = defineEmits<{
  'update:question': [value: string]
  'update:topK': [value: number]
  'update:qaActiveTab': [value: string]
  retrieve: []
  ask: []
  submitRating: [answerId: string, rating: number]
  selectHistoryItem: [item: QuestionAnswer]
  deleteHistoryItem: [item: QuestionAnswer]
  refreshHistory: []
  goQaPage: [page: number]
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
      <a-tab-pane key="debug" tab="问答">
        <div class="ask-box">
          <a-textarea
            :value="question" :rows="4"
            placeholder="输入问题，例如：这个系统支持哪些文档格式？"
            @update:value="emit('update:question', $event)"
          />
          <div class="ask-actions">
            <a-input-number :value="topK" :min="1" :max="20" @update:value="emit('update:topK', $event)" />
            <div class="ask-buttons">
              <a-button
                :loading="retrieving"
                :disabled="!selectedKnowledgeBaseId || !question.trim() || indexedCount === 0"
                @click="emit('retrieve')"
              >
                <template #icon><SearchOutlined /></template> 仅检索
              </a-button>
              <a-button type="primary"
                :loading="asking"
                :disabled="!selectedKnowledgeBaseId || !question.trim() || indexedCount === 0"
                @click="emit('ask')"
              >
                <template #icon><SendOutlined /></template> 提问
              </a-button>
            </div>
          </div>
        </div>

        <a-alert v-if="selectedKnowledgeBaseId && indexedCount === 0" class="question-alert"
          type="warning" show-icon message="当前知识库还没有已索引文档。" />
        <a-alert v-if="questionError" class="question-alert" type="error" show-icon :message="questionError" />

        <!-- 检索结果 -->
        <div class="debug-block">
          <div class="debug-head">
            <div><h4>检索结果</h4><p>看命中了哪些片段、分数如何、上下文是否足够</p></div>
            <div class="debug-summary">
              <span class="debug-summary-line">{{ retrievalSummary }}</span>
              <span class="document-match-count document-match-count-muted">{{ retrievalResults.length }} 条</span>
            </div>
          </div>

          <a-empty v-if="!retrievalResults.length" description="点击「仅检索」或「提问」查看命中片段" />

          <div v-else class="debug-list">
            <article v-for="(result, index) in retrievalResults" :key="result.vector_id"
              class="debug-row"
              :class="{
                'debug-row-cited': answer && citedVectorIds.has(result.vector_id),
                'debug-row-uncited': answer && !citedVectorIds.has(result.vector_id),
              }"
            >
              <div class="debug-row-head">
                <div class="debug-rank">
                  <span>#{{ index + 1 }}</span>
                  <span v-if="result.score !== null" class="score-bar-wrap">
                    <span class="score-bar-fill" :style="{ width: scoreBarWidth(result.score), background: scoreColor(result.score) }"></span>
                    <span class="score-bar-label">{{ result.score.toFixed(3) }}</span>
                  </span>
                  <a-tag v-if="answer && citedVectorIds.has(result.vector_id)" color="success">已引用</a-tag>
                  <a-tag v-else-if="answer && !citedVectorIds.has(result.vector_id)" color="default">未采用</a-tag>
                </div>
                <div class="debug-meta">
                  <strong>{{ getResultTitle(result.metadata) }}</strong>
                  <small>{{ getResultSubtitle(result.metadata) }}</small>
                </div>
              </div>
              <div class="debug-metadata">
                <a-tag v-if="getResultFilename(result.metadata)" color="green">{{ getResultFilename(result.metadata) }}</a-tag>
                <a-tag v-if="getResultSectionTitle(result.metadata)" color="default">{{ getResultSectionTitle(result.metadata) }}</a-tag>
                <a-tag v-if="getResultChunkLabel(result.metadata)" color="gold">{{ getResultChunkLabel(result.metadata) }}</a-tag>
              </div>
              <details class="debug-details">
                <summary>查看片段</summary>
                <p v-html="highlightText(result.text, retrievalQuery)"></p>
              </details>
            </article>
          </div>
        </div>

        <!-- 回答 -->
        <div v-if="answer || streaming" class="answer-block">
          <div class="answer-label">
            <ApiOutlined /><span>Answer</span>
            <span v-if="streaming" class="streaming-dot"></span>
          </div>
          <p class="answer-text"
            v-html="renderAnswerWithCitations(streaming ? streamingAnswer : answer?.answer || '')"
            @click="handleCitationClick"
          ></p>

          <div v-if="!streaming && answer && currentAnswerId" class="rating-row">
            <a-tooltip title="回答准确有用">
              <a-button size="small" type="text"
                :class="{ 'rating-active': currentAnswerRating === 1 }"
                :loading="ratingSubmitting"
                @click="emit('submitRating', currentAnswerId, 1)"
              >👍</a-button>
            </a-tooltip>
            <a-tooltip title="回答不准确或无用">
              <a-button size="small" type="text"
                :class="{ 'rating-active': currentAnswerRating === -1 }"
                :loading="ratingSubmitting"
                @click="emit('submitRating', currentAnswerId, -1)"
              >👎</a-button>
            </a-tooltip>
          </div>

          <div v-if="!streaming && answer" class="sources">
            <h4>引用来源</h4>
            <article v-for="source in answer.sources" :key="source.vector_id"
              :data-source-citation="source.citation"
              @mouseenter="highlightSourceCitation" @mouseleave="clearSourceCitation"
            >
              <div class="source-head">
                <a-tag color="blue">[{{ source.citation }}]</a-tag>
                <span>{{ source.metadata.filename || source.metadata.source_label }}</span>
                <small v-if="source.score">score {{ source.score.toFixed(3) }}</small>
              </div>
              <p>{{ source.text }}</p>
            </article>
            <a-empty v-if="!answer.sources.length" description="没有可引用的来源" />
          </div>
        </div>

        <div v-else class="empty-answer">
          <CloudUploadOutlined />
          <p>完成文档索引后，可以先检索命中片段，再查看回答与引用来源。</p>
        </div>
      </a-tab-pane>

      <a-tab-pane key="history" tab="最近问答">
        <HistoryPanel
          :questionAnswers="questionAnswers"
          :loading="loadingHistory"
          :busyAnswerId="busyAnswerId"
          :qaPage="qaPage"
          :qaPageSize="qaPageSize"
          :qaTotal="qaTotal"
          @select="emit('selectHistoryItem', $event)"
          @delete="emit('deleteHistoryItem', $event)"
          @refresh="emit('refreshHistory')"
          @goPage="emit('goQaPage', $event)"
        />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>
