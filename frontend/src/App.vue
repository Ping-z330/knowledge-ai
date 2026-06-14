<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import {
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import type { UploadProps } from 'ant-design-vue'

type KnowledgeBase = {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

type DocumentItem = {
  id: string
  knowledge_base_id: string
  filename: string
  content_type: string
  storage_path: string
  parse_status: string
  index_status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

type AnswerSource = {
  citation: number
  vector_id: string
  text: string
  score: number | null
  metadata: Record<string, unknown>
}

type QuestionResponse = {
  question: string
  answer: string
  sources: AnswerSource[]
}

type QuestionAnswer = QuestionResponse & {
  id: string
  knowledge_base_id: string
  top_k: number
  created_at: string
}

const api = axios.create({
  baseURL: '/api',
})

const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedKnowledgeBaseId = ref('')
const documents = ref<DocumentItem[]>([])
const questionAnswers = ref<QuestionAnswer[]>([])
const answer = ref<QuestionResponse | null>(null)
const question = ref('')
const questionError = ref('')
const documentSearch = ref('')
const documentFilter = ref('all')
const topK = ref(5)

const loadingKnowledgeBases = ref(false)
const loadingDocuments = ref(false)
const loadingQuestionAnswers = ref(false)
const creatingKnowledgeBase = ref(false)
const asking = ref(false)
const batchParsing = ref(false)
const batchIndexing = ref(false)
const busyDocumentId = ref('')
const busyAnswerId = ref('')

const createForm = ref({
  name: '',
  description: '',
})

const selectedKnowledgeBase = computed(() =>
  knowledgeBases.value.find((item) => item.id === selectedKnowledgeBaseId.value) ?? null,
)

const indexedCount = computed(
  () => documents.value.filter((item) => item.index_status === 'indexed').length,
)

const hasRunningDocuments = computed(() =>
  documents.value.some(
    (item) => item.parse_status === 'running' || item.index_status === 'running',
  ),
)

const parsedCount = computed(
  () => documents.value.filter((item) => item.parse_status === 'parsed').length,
)

const documentFilterOptions = computed(() => [
  { label: `全部 ${documents.value.length}`, value: 'all' },
  { label: `待解析 ${countDocumentsByFilter('pending_parse')}`, value: 'pending_parse' },
  { label: `解析中 ${countDocumentsByFilter('parsing')}`, value: 'parsing' },
  { label: `待索引 ${countDocumentsByFilter('pending_index')}`, value: 'pending_index' },
  { label: `索引中 ${countDocumentsByFilter('indexing')}`, value: 'indexing' },
  { label: `已索引 ${countDocumentsByFilter('indexed')}`, value: 'indexed' },
  { label: `失败 ${countDocumentsByFilter('failed')}`, value: 'failed' },
])

const filteredDocuments = computed(() => {
  const search = documentSearch.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    const matchesSearch =
      !search ||
      item.filename.toLowerCase().includes(search) ||
      item.content_type.toLowerCase().includes(search)
    return matchesSearch && matchesDocumentFilter(item, documentFilter.value)
  })
})

function matchesDocumentFilter(item: DocumentItem, filter: string) {
  if (filter === 'pending_parse') return ['uploaded', 'failed'].includes(item.parse_status)
  if (filter === 'parsing') return item.parse_status === 'running'
  if (filter === 'pending_index') {
    return item.parse_status === 'parsed' && ['pending', 'failed'].includes(item.index_status)
  }
  if (filter === 'indexing') return item.index_status === 'running'
  if (filter === 'indexed') return item.index_status === 'indexed'
  if (filter === 'failed') return item.parse_status === 'failed' || item.index_status === 'failed'
  return true
}

function countDocumentsByFilter(filter: string) {
  return documents.value.filter((item) => matchesDocumentFilter(item, filter)).length
}

const statusTone = (status: string) => {
  if (status === 'indexed' || status === 'parsed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'pending' || status === 'uploaded' || status === 'running') return 'processing'
  return 'default'
}

const formatDate = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

const loadKnowledgeBases = async () => {
  loadingKnowledgeBases.value = true
  try {
    const { data } = await api.get<KnowledgeBase[]>('/knowledge-bases')
    knowledgeBases.value = data
    if (!selectedKnowledgeBaseId.value && data.length > 0) {
      selectedKnowledgeBaseId.value = data[0].id
      await loadDocuments()
      await loadQuestionAnswers()
    }
  } finally {
    loadingKnowledgeBases.value = false
  }
}

const loadDocuments = async () => {
  if (!selectedKnowledgeBaseId.value) {
    documents.value = []
    return
  }

  loadingDocuments.value = true
  try {
    const { data } = await api.get<DocumentItem[]>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents`,
    )
    documents.value = data
  } finally {
    loadingDocuments.value = false
  }
}

const loadQuestionAnswers = async () => {
  if (!selectedKnowledgeBaseId.value) {
    questionAnswers.value = []
    return
  }

  loadingQuestionAnswers.value = true
  try {
    const { data } = await api.get<QuestionAnswer[]>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/question-answers`,
    )
    questionAnswers.value = data
  } finally {
    loadingQuestionAnswers.value = false
  }
}

const selectKnowledgeBase = async (id: string) => {
  selectedKnowledgeBaseId.value = id
  answer.value = null
  questionError.value = ''
  await loadDocuments()
  await loadQuestionAnswers()
}

const createKnowledgeBase = async () => {
  if (!createForm.value.name.trim()) return

  creatingKnowledgeBase.value = true
  try {
    const { data } = await api.post<KnowledgeBase>('/knowledge-bases', {
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim(),
    })
    knowledgeBases.value = [data, ...knowledgeBases.value]
    createForm.value = { name: '', description: '' }
    await selectKnowledgeBase(data.id)
  } finally {
    creatingKnowledgeBase.value = false
  }
}

const uploadProps = computed<UploadProps>(() => ({
  name: 'file',
  multiple: true,
  showUploadList: false,
  accept: '.pdf,.doc,.docx,.md,.txt',
  action: selectedKnowledgeBaseId.value
    ? `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/documents`
    : '',
  disabled: !selectedKnowledgeBaseId.value,
  async onChange(info) {
    if (info.file.status === 'done') {
      await loadDocuments()
    }
  },
}))

type BatchTaskResponse = {
  scheduled: number
  document_ids: string[]
}

const parsePendingDocuments = async () => {
  if (!selectedKnowledgeBaseId.value) return

  batchParsing.value = true
  try {
    const { data } = await api.post<BatchTaskResponse>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/parse-pending`,
    )
    message.info(data.scheduled ? `已触发 ${data.scheduled} 个解析任务` : '没有待解析文档')
    await loadDocuments()
  } finally {
    batchParsing.value = false
  }
}

const indexPendingDocuments = async () => {
  if (!selectedKnowledgeBaseId.value) return

  batchIndexing.value = true
  try {
    const { data } = await api.post<BatchTaskResponse>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/index-pending`,
    )
    message.info(data.scheduled ? `已触发 ${data.scheduled} 个索引任务` : '没有待索引文档')
    await loadDocuments()
  } finally {
    batchIndexing.value = false
  }
}

const parseDocument = async (item: DocumentItem) => {
  busyDocumentId.value = item.id
  item.parse_status = 'running'
  item.error_message = null
  try {
    await api.post(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}/parse`)
    await loadDocuments()
  } finally {
    busyDocumentId.value = ''
  }
}

const indexDocument = async (item: DocumentItem) => {
  busyDocumentId.value = item.id
  item.index_status = 'running'
  item.error_message = null
  try {
    await api.post(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}/index`)
    await loadDocuments()
  } finally {
    busyDocumentId.value = ''
  }
}

let documentPollTimer: number | undefined

const deleteDocument = async (item: DocumentItem) => {
  busyDocumentId.value = item.id
  try {
    await api.delete(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}`)
    await loadDocuments()
  } finally {
    busyDocumentId.value = ''
  }
}

const askQuestion = async () => {
  if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
  if (indexedCount.value === 0) {
    questionError.value = '当前知识库还没有已索引文档。请先上传、解析并索引文档。'
    answer.value = null
    return
  }

  asking.value = true
  questionError.value = ''
  answer.value = null
  try {
    const { data } = await api.post<QuestionResponse>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/questions`,
      {
        question: question.value.trim(),
        top_k: topK.value,
      },
    )
    answer.value = data
    await loadQuestionAnswers()
  } catch (error) {
    questionError.value = extractApiError(error)
  } finally {
    asking.value = false
  }
}

const selectQuestionAnswer = (item: QuestionAnswer) => {
  question.value = item.question
  topK.value = item.top_k
  answer.value = {
    question: item.question,
    answer: item.answer,
    sources: item.sources,
  }
  questionError.value = ''
}

const deleteQuestionAnswer = async (item: QuestionAnswer) => {
  busyAnswerId.value = item.id
  try {
    await api.delete(
      `/knowledge-bases/${item.knowledge_base_id}/question-answers/${item.id}`,
    )
    questionAnswers.value = questionAnswers.value.filter((answerItem) => answerItem.id !== item.id)
  } finally {
    busyAnswerId.value = ''
  }
}

const extractApiError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (error.response?.status) {
      return `请求失败：HTTP ${error.response.status}`
    }
    if (error.message) {
      return error.message
    }
  }
  return '问答请求失败，请检查后端日志或模型服务配置。'
}

onMounted(() => {
  loadKnowledgeBases()
  documentPollTimer = window.setInterval(() => {
    if (selectedKnowledgeBaseId.value && hasRunningDocuments.value && !loadingDocuments.value) {
      loadDocuments()
    }
  }, 2000)
})

onUnmounted(() => {
  if (documentPollTimer !== undefined) {
    window.clearInterval(documentPollTimer)
  }
})
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
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark">
            <DatabaseOutlined />
          </div>
          <div>
            <p class="eyebrow">Knowledge Agent</p>
            <h1>企业知识库</h1>
          </div>
        </div>

        <section class="create-panel">
          <a-input v-model:value="createForm.name" placeholder="新知识库名称" />
          <a-textarea
            v-model:value="createForm.description"
            placeholder="描述"
            :rows="2"
          />
          <a-button
            type="primary"
            block
            :loading="creatingKnowledgeBase"
            @click="createKnowledgeBase"
          >
            <template #icon><PlusOutlined /></template>
            创建知识库
          </a-button>
        </section>

        <section class="kb-list">
          <div class="section-line">
            <span>知识库</span>
            <a-button type="text" size="small" @click="loadKnowledgeBases">
              <template #icon><ReloadOutlined /></template>
            </a-button>
          </div>

          <a-spin :spinning="loadingKnowledgeBases">
            <button
              v-for="item in knowledgeBases"
              :key="item.id"
              class="kb-item"
              :class="{ active: item.id === selectedKnowledgeBaseId }"
              @click="selectKnowledgeBase(item.id)"
            >
              <span>{{ item.name }}</span>
              <small>{{ item.description || '无描述' }}</small>
            </button>
            <a-empty
              v-if="!knowledgeBases.length"
              description="还没有知识库"
            />
          </a-spin>
        </section>
      </aside>

      <section class="workspace">
        <header class="workspace-head">
          <div>
            <p class="eyebrow">RAG Pipeline</p>
            <h2>{{ selectedKnowledgeBase?.name || '选择一个知识库' }}</h2>
            <p class="muted">
              {{ selectedKnowledgeBase?.description || '上传文档后完成解析和索引，再开始问答。' }}
            </p>
          </div>
          <div class="metrics">
            <div>
              <strong>{{ documents.length }}</strong>
              <span>文档</span>
            </div>
            <div>
              <strong>{{ parsedCount }}</strong>
              <span>已解析</span>
            </div>
            <div>
              <strong>{{ indexedCount }}</strong>
              <span>已索引</span>
            </div>
          </div>
        </header>

        <div class="main-grid">
          <section class="panel documents-panel">
            <div class="panel-head">
              <div>
                <h3>文档管理</h3>
                <p>PDF / Word / Markdown / TXT · 支持多文件上传</p>
              </div>
              <div class="panel-actions">
                <a-button
                  :loading="batchParsing"
                  :disabled="!selectedKnowledgeBaseId"
                  @click="parsePendingDocuments"
                >
                  解析待处理
                </a-button>
                <a-button
                  type="primary"
                  ghost
                  :loading="batchIndexing"
                  :disabled="!selectedKnowledgeBaseId"
                  @click="indexPendingDocuments"
                >
                  索引待处理
                </a-button>
                <a-button @click="loadDocuments">
                  <template #icon><ReloadOutlined /></template>
                </a-button>
              </div>
            </div>

            <a-upload-dragger v-bind="uploadProps" class="upload-zone">
              <p class="ant-upload-drag-icon"><InboxOutlined /></p>
              <p class="ant-upload-text">拖拽或点击上传一个或多个文档</p>
              <p class="ant-upload-hint">上传后可批量解析和索引</p>
            </a-upload-dragger>

            <div class="document-toolbar">
              <a-input-search
                v-model:value="documentSearch"
                allow-clear
                placeholder="搜索文件名或类型"
              />
              <a-segmented
                v-model:value="documentFilter"
                :options="documentFilterOptions"
              />
              <span class="document-match-count">
                {{ filteredDocuments.length }} / {{ documents.length }}
              </span>
            </div>

            <a-spin :spinning="loadingDocuments">
              <div class="document-list">
                <article v-for="item in filteredDocuments" :key="item.id" class="document-row">
                  <div class="document-main">
                    <FileSearchOutlined class="file-icon" />
                    <div>
                      <h4>{{ item.filename }}</h4>
                      <p>{{ item.content_type }} · {{ formatDate(item.created_at) }}</p>
                      <p v-if="item.error_message" class="error-text">
                        {{ item.error_message }}
                      </p>
                    </div>
                  </div>

                  <div class="document-status">
                    <a-tag :color="statusTone(item.parse_status)">
                      parse: {{ item.parse_status }}
                    </a-tag>
                    <a-tag :color="statusTone(item.index_status)">
                      index: {{ item.index_status }}
                    </a-tag>
                  </div>

                  <div class="document-actions">
                    <a-button
                      size="small"
                      :disabled="item.parse_status === 'running' || item.index_status === 'running'"
                      :loading="busyDocumentId === item.id || item.parse_status === 'running'"
                      @click="parseDocument(item)"
                    >
                      解析
                    </a-button>
                    <a-button
                      size="small"
                      type="primary"
                      ghost
                      :disabled="item.parse_status !== 'parsed' || item.index_status === 'running'"
                      :loading="busyDocumentId === item.id || item.index_status === 'running'"
                      @click="indexDocument(item)"
                    >
                      索引
                    </a-button>
                    <a-popconfirm title="删除这个文档？" @confirm="deleteDocument(item)">
                      <a-button size="small" danger>
                        <template #icon><DeleteOutlined /></template>
                      </a-button>
                    </a-popconfirm>
                  </div>
                </article>

                <a-empty
                  v-if="!documents.length"
                  description="上传第一份文档开始构建知识库"
                />
                <a-empty
                  v-else-if="!filteredDocuments.length"
                  description="没有匹配的文档"
                />
              </div>
            </a-spin>
          </section>

          <section class="panel qa-panel">
            <div class="panel-head">
              <div>
                <h3>知识库问答</h3>
                <p>回答必须来自已索引文档</p>
              </div>
              <a-tag color="success" v-if="indexedCount > 0">
                <CheckCircleOutlined />
                ready
              </a-tag>
            </div>

            <div class="ask-box">
              <a-textarea
                v-model:value="question"
                :rows="4"
                placeholder="输入问题，例如：这个系统支持哪些文档格式？"
              />
              <div class="ask-actions">
                <a-input-number v-model:value="topK" :min="1" :max="20" />
                <a-button
                  type="primary"
                  :loading="asking"
                  :disabled="!selectedKnowledgeBaseId || !question.trim() || indexedCount === 0"
                  @click="askQuestion"
                >
                  <template #icon><SendOutlined /></template>
                  提问
                </a-button>
              </div>
            </div>

            <a-alert
              v-if="selectedKnowledgeBaseId && indexedCount === 0"
              class="question-alert"
              type="warning"
              show-icon
              message="当前知识库还没有已索引文档。请先上传、解析并索引文档。"
            />

            <a-alert
              v-if="questionError"
              class="question-alert"
              type="error"
              show-icon
              :message="questionError"
            />

            <div v-if="answer" class="answer-block">
              <div class="answer-label">
                <ApiOutlined />
                <span>Answer</span>
              </div>
              <p class="answer-text">{{ answer.answer }}</p>

              <div class="sources">
                <h4>引用来源</h4>
                <article v-for="source in answer.sources" :key="source.vector_id">
                  <div class="source-head">
                    <a-tag color="blue">[{{ source.citation }}]</a-tag>
                    <span>{{ source.metadata.filename || source.metadata.source_label }}</span>
                    <small v-if="source.score">score {{ source.score.toFixed(3) }}</small>
                  </div>
                  <p>{{ source.text }}</p>
                </article>
                <a-empty
                  v-if="!answer.sources.length"
                  description="没有可引用的来源"
                />
              </div>
            </div>

            <div v-else class="empty-answer">
              <CloudUploadOutlined />
              <p>完成文档索引后，在这里提出问题并查看引用来源。</p>
            </div>

            <div class="history-block">
              <div class="history-head">
                <div>
                  <h4>最近问答</h4>
                  <p>保存当前知识库的问答记录</p>
                </div>
                <a-button size="small" @click="loadQuestionAnswers">
                  <template #icon><ReloadOutlined /></template>
                </a-button>
              </div>

              <a-spin :spinning="loadingQuestionAnswers">
                <div class="history-list">
                  <article
                    v-for="item in questionAnswers"
                    :key="item.id"
                    class="history-row"
                    @click="selectQuestionAnswer(item)"
                  >
                    <div class="history-main">
                      <ClockCircleOutlined />
                      <div>
                        <h5>{{ item.question }}</h5>
                        <p>{{ item.answer }}</p>
                        <small>{{ formatDate(item.created_at) }} · top {{ item.top_k }}</small>
                      </div>
                    </div>
                    <a-popconfirm title="删除这条问答历史？" @confirm.stop="deleteQuestionAnswer(item)">
                      <a-button
                        size="small"
                        danger
                        :loading="busyAnswerId === item.id"
                        @click.stop
                      >
                        <template #icon><DeleteOutlined /></template>
                      </a-button>
                    </a-popconfirm>
                  </article>

                  <a-empty
                    v-if="!questionAnswers.length"
                    description="还没有问答历史"
                  />
                </div>
              </a-spin>
            </div>
          </section>
        </div>
      </section>
    </main>
  </a-config-provider>
</template>
