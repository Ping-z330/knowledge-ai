<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import {
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  ExclamationCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  SendOutlined,
  SearchOutlined,
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

type RetrievalResult = {
  vector_id: string
  text: string
  score: number | null
  metadata: Record<string, unknown>
}

type RetrievalResponse = {
  query: string
  results: RetrievalResult[]
}

type PaginatedResponse<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

type ConversationMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: AnswerSource[]
  created_at: string
}

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: import.meta.env.VITE_API_TOKEN
    ? { Authorization: `Bearer ${import.meta.env.VITE_API_TOKEN}` }
    : {},
})

const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedKnowledgeBaseId = ref('')
const documents = ref<DocumentItem[]>([])
const questionAnswers = ref<QuestionAnswer[]>([])
const answer = ref<QuestionResponse | null>(null)
const retrievalResults = ref<RetrievalResult[]>([])
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
const streaming = ref(false)
const streamingAnswer = ref('')
const retrieving = ref(false)
const batchParsing = ref(false)
const batchIndexing = ref(false)
const reindexingAll = ref(false)
const qaActiveTab = ref('debug')
const busyDocumentId = ref('')
const busyAnswerId = ref('')
const documentTotal = ref(0)
const documentPage = ref(1)
const documentPageSize = 50
const qaTotal = ref(0)
const qaPage = ref(1)
const qaPageSize = 20
const conversation = ref<ConversationMessage[]>([])
const convStreaming = ref(false)
const convStreamingAnswer = ref('')
const convInput = ref('')
const convAsking = ref(false)
const convMessagesRef = ref<HTMLElement | null>(null)

function scrollConvToBottom() {
  nextTick(() => {
    const el = convMessagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch([conversation, convStreamingAnswer], () => scrollConvToBottom(), { deep: true })

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

function getResultTitle(metadata: Record<string, unknown>) {
  const filename = metadata.filename || metadata.source_label || '未知来源'
  return String(filename)
}

function getResultSubtitle(metadata: Record<string, unknown>) {
  const parts = []
  if (metadata.section_title) parts.push(String(metadata.section_title))
  if (typeof metadata.chunk_index === 'number') parts.push(`chunk ${metadata.chunk_index + 1}`)
  if (!parts.length && metadata.document_id) parts.push(String(metadata.document_id))
  return parts.join(' · ')
}

function getResultFilename(metadata: Record<string, unknown>) {
  const value = metadata.filename || metadata.source_label
  return value ? String(value) : ''
}

function getResultSectionTitle(metadata: Record<string, unknown>) {
  return metadata.section_title ? String(metadata.section_title) : ''
}

function getResultChunkLabel(metadata: Record<string, unknown>) {
  return typeof metadata.chunk_index === 'number' ? `chunk ${metadata.chunk_index + 1}` : ''
}

const retrievalQuery = computed(() => question.value.trim())

const retrievalSummary = computed(() => {
  if (!retrievalQuery.value) return '尚未发起检索'
  return `Query: ${retrievalQuery.value} · top_k: ${topK.value} · 命中 ${retrievalResults.value.length} 条`
})

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function highlightText(text: string, query: string) {
  const cleanQuery = query.trim()
  if (!cleanQuery) return escapeHtml(text)

  const terms = Array.from(
    new Set(
      cleanQuery
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 6),
    ),
  )
  if (!terms.length) return escapeHtml(text)

  const pattern = new RegExp(`(${terms.map((term) => escapeRegExp(term)).join('|')})`, 'gi')
  return escapeHtml(text).replace(pattern, '<mark>$1</mark>')
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function renderAnswerWithCitations(answerText: string) {
  return answerText.replace(
    /\[(\d+)\]/g,
    '<sup><a href="#" class="citation-link" data-citation="$1">[$1]</a></sup>',
  )
}

let convIdCounter = 0

function nextConvId() {
  convIdCounter++
  return `conv-${Date.now()}-${convIdCounter}`
}

function buildConversationHistory(): { role: string; content: string }[] {
  const recent = conversation.value.slice(-10)
  return recent.map((m) => ({ role: m.role, content: m.content }))
}

const askConversation = async () => {
  const question = convInput.value.trim()
  if (!selectedKnowledgeBaseId.value || !question) return
  if (indexedCount.value === 0) {
    questionError.value = '当前知识库还没有已索引文档。请先上传、解析并索引文档。'
    return
  }

  convAsking.value = true
  convStreaming.value = true
  convStreamingAnswer.value = ''
  questionError.value = ''

  // 添加用户消息
  const userMsg: ConversationMessage = {
    id: nextConvId(),
    role: 'user',
    content: question,
    sources: [],
    created_at: new Date().toISOString(),
  }
  conversation.value = [...conversation.value, userMsg]
  convInput.value = ''

  const assistantMsg: ConversationMessage = {
    id: nextConvId(),
    role: 'assistant',
    content: '',
    sources: [],
    created_at: new Date().toISOString(),
  }

  try {
    const token = import.meta.env.VITE_API_TOKEN
    const response = await fetch(
      `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/questions/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          top_k: topK.value,
          conversation_history: buildConversationHistory(),
        }),
      },
    )

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null)
      throw new Error(errorBody?.detail || `HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('Stream not supported')

    const decoder = new TextDecoder()
    let buffer = ''
    let sources: AnswerSource[] = []

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        try {
          const event = JSON.parse(data)
          if (event.type === 'sources') {
            sources = event.sources.map((s: AnswerSource) => ({
              citation: s.citation ?? 0,
              vector_id: s.vector_id,
              text: s.text,
              score: s.score,
              metadata: s.metadata,
            }))
          } else if (event.type === 'token') {
            convStreamingAnswer.value += event.content
          } else if (event.type === 'done') {
            assistantMsg.content = convStreamingAnswer.value
            assistantMsg.sources = sources
            conversation.value = [...conversation.value, assistantMsg]
            convStreaming.value = false
            convStreamingAnswer.value = ''
            await loadQuestionAnswers()
          } else if (event.type === 'error') {
            questionError.value = event.message || 'Stream error'
            convStreaming.value = false
          }
        } catch {
          // skip
        }
      }
    }
  } catch (error) {
    convStreaming.value = false
    questionError.value = error instanceof Error ? error.message : '流式请求失败'
  } finally {
    convAsking.value = false
    // 处理意外中断
    if (convStreaming.value && convStreamingAnswer.value) {
      assistantMsg.content = convStreamingAnswer.value
      conversation.value = [...conversation.value, assistantMsg]
      convStreaming.value = false
      convStreamingAnswer.value = ''
    }
    // 如果中断且无内容，移除占位
    if (!convStreaming.value && !assistantMsg.content && conversation.value.at(-1)?.id === assistantMsg.id) {
      conversation.value = conversation.value.slice(0, -1)
    }
  }
}

function clearConversation() {
  conversation.value = []
  convStreaming.value = false
  convStreamingAnswer.value = ''
}

function handleCitationClick(event: Event) {
  const target = event.target as HTMLElement
  if (!target.classList.contains('citation-link')) return
  event.preventDefault()
  const citation = target.dataset.citation
  const sourceEl = document.querySelector(`[data-source-citation="${citation}"]`)
  if (sourceEl) {
    sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    sourceEl.classList.add('source-flash')
    setTimeout(() => sourceEl.classList.remove('source-flash'), 2000)
  }
}

type DocumentStatusTone = 'default' | 'processing' | 'success' | 'error'

type DocumentStatusMeta = {
  label: string
  tone: DocumentStatusTone
  icon: typeof CheckCircleOutlined | typeof ClockCircleOutlined | typeof SyncOutlined | typeof ExclamationCircleOutlined
  detail: string
}

const getDocumentStatusMeta = (item: DocumentItem): DocumentStatusMeta => {
  if (item.parse_status === 'failed' || item.index_status === 'failed') {
    return {
      label: '失败',
      tone: 'error',
      icon: ExclamationCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }

  if (item.parse_status === 'running') {
    return {
      label: '解析中',
      tone: 'processing',
      icon: SyncOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }

  if (item.index_status === 'running') {
    return {
      label: '索引中',
      tone: 'processing',
      icon: SyncOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }

  if (item.index_status === 'indexed') {
    return {
      label: '已就绪',
      tone: 'success',
      icon: CheckCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }

  if (item.parse_status === 'parsed') {
    return {
      label: '待索引',
      tone: 'default',
      icon: ClockCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }

  return {
    label: '待解析',
    tone: 'default',
    icon: ClockCircleOutlined,
    detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
  }
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
    stopDocumentPolling()
    return
  }

  loadingDocuments.value = true
  try {
    const offset = (documentPage.value - 1) * documentPageSize
    const { data } = await api.get<PaginatedResponse<DocumentItem>>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents`,
      { params: { limit: documentPageSize, offset } },
    )
    documents.value = data.items
    documentTotal.value = data.total
    if (hasRunningDocuments.value) {
      startDocumentPolling()
    }
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
    const offset = (qaPage.value - 1) * qaPageSize
    const { data } = await api.get<PaginatedResponse<QuestionAnswer>>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/question-answers`,
      { params: { limit: qaPageSize, offset } },
    )
    questionAnswers.value = data.items
    qaTotal.value = data.total
  } finally {
    loadingQuestionAnswers.value = false
  }
}

const selectKnowledgeBase = async (id: string) => {
  selectedKnowledgeBaseId.value = id
  answer.value = null
  retrievalResults.value = []
  questionError.value = ''
  documentPage.value = 1
  qaPage.value = 1
  await loadDocuments()
  await loadQuestionAnswers()
}

const goDocumentPage = async (page: number) => {
  documentPage.value = page
  await loadDocuments()
}

const goQaPage = async (page: number) => {
  qaPage.value = page
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

const retrieveOnly = async () => {
  if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
  if (indexedCount.value === 0) {
    questionError.value = '当前知识库还没有已索引文档。请先上传、解析并索引文档。'
    retrievalResults.value = []
    answer.value = null
    return
  }

  retrieving.value = true
  questionError.value = ''
  answer.value = null
  try {
    const { data } = await api.post<RetrievalResponse>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/retrieve`,
      {
        query: question.value.trim(),
        top_k: topK.value,
      },
    )
    retrievalResults.value = data.results
  } catch (error) {
    retrievalResults.value = []
    questionError.value = extractApiError(error)
  } finally {
    retrieving.value = false
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

const reindexAllDocuments = async () => {
  if (!selectedKnowledgeBaseId.value) return

  reindexingAll.value = true
  try {
    const { data } = await api.post<BatchTaskResponse>(
      `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/reindex-all`,
    )
    message.info(data.scheduled ? `已触发 ${data.scheduled} 个重建索引任务` : '没有已解析文档')
    await loadDocuments()
  } finally {
    reindexingAll.value = false
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

function startDocumentPolling() {
  if (documentPollTimer !== undefined) return
  documentPollTimer = window.setInterval(() => {
    if (!selectedKnowledgeBaseId.value || loadingDocuments.value) return
    if (!hasRunningDocuments.value) {
      stopDocumentPolling()
      return
    }
    loadDocuments()
  }, 2000)
}

function stopDocumentPolling() {
  if (documentPollTimer !== undefined) {
    window.clearInterval(documentPollTimer)
    documentPollTimer = undefined
  }
}

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
    retrievalResults.value = []
    return
  }

  asking.value = true
  streaming.value = true
  streamingAnswer.value = ''
  questionError.value = ''
  answer.value = null

  try {
    const token = import.meta.env.VITE_API_TOKEN
    const response = await fetch(
      `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/questions/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question: question.value.trim(),
          top_k: topK.value,
        }),
      },
    )

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null)
      throw new Error(errorBody?.detail || `HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('Stream not supported')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        try {
          const event = JSON.parse(data)
          if (event.type === 'sources') {
            retrievalResults.value = event.sources.map((s: AnswerSource) => ({
              vector_id: s.vector_id,
              text: s.text,
              score: s.score,
              metadata: s.metadata,
            }))
          } else if (event.type === 'token') {
            streamingAnswer.value += event.content
          } else if (event.type === 'done') {
            answer.value = {
              question: question.value.trim(),
              answer: streamingAnswer.value,
              sources: retrievalResults.value.map((r, i) => ({
                citation: i + 1,
                vector_id: r.vector_id,
                text: r.text,
                score: r.score,
                metadata: r.metadata,
              })),
            }
            streaming.value = false
            await loadQuestionAnswers()
          } else if (event.type === 'error') {
            questionError.value = event.message || 'Stream error'
            streaming.value = false
          }
        } catch {
          // skip unparseable lines
        }
      }
    }
  } catch (error) {
    retrievalResults.value = []
    streaming.value = false
    questionError.value = error instanceof Error ? error.message : '流式请求失败'
  } finally {
    asking.value = false
    if (streaming.value && !questionError.value) {
      // 流意外结束但有内容，固化回答
      answer.value = {
        question: question.value.trim(),
        answer: streamingAnswer.value || '（回答中断）',
        sources: retrievalResults.value.map((r, i) => ({
          citation: i + 1,
          vector_id: r.vector_id,
          text: r.text,
          score: r.score,
          metadata: r.metadata,
        })),
      }
      streaming.value = false
    }
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
  retrievalResults.value = item.sources.map((source) => ({
    vector_id: source.vector_id,
    text: source.text,
    score: source.score,
    metadata: source.metadata,
  }))
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
})

onUnmounted(() => {
  stopDocumentPolling()
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
                <a-button
                  :loading="reindexingAll"
                  :disabled="!selectedKnowledgeBaseId"
                  @click="reindexAllDocuments"
                >
                  重建索引
                </a-button>
                <a-tooltip title="刷新文档列表">
                  <a-button class="icon-only-button" @click="loadDocuments">
                  <template #icon><ReloadOutlined /></template>
                  </a-button>
                </a-tooltip>
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
              <a-select
                v-model:value="documentFilter"
                class="document-filter-select"
                :options="documentFilterOptions"
                :dropdown-match-select-width="false"
              />
              <span class="document-match-count document-match-count-muted">
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

                  <a-tooltip :title="getDocumentStatusMeta(item).detail">
                    <a-tag class="document-status-pill" :color="getDocumentStatusMeta(item).tone">
                      <component :is="getDocumentStatusMeta(item).icon" />
                      {{ getDocumentStatusMeta(item).label }}
                    </a-tag>
                  </a-tooltip>

                  <div class="document-actions">
                    <a-tooltip title="解析文档">
                      <a-button
                        size="small"
                        :disabled="item.parse_status === 'running' || item.index_status === 'running'"
                        :loading="busyDocumentId === item.id || item.parse_status === 'running'"
                        @click="parseDocument(item)"
                      >
                        <template #icon><FileSearchOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="索引文档">
                      <a-button
                        size="small"
                        type="primary"
                        ghost
                        :disabled="item.parse_status !== 'parsed' || item.index_status === 'running'"
                        :loading="busyDocumentId === item.id || item.index_status === 'running'"
                        @click="indexDocument(item)"
                      >
                        <template #icon><ApiOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-popconfirm title="删除这个文档？" @confirm="deleteDocument(item)">
                      <a-tooltip title="删除文档">
                        <a-button size="small" danger>
                          <template #icon><DeleteOutlined /></template>
                        </a-button>
                      </a-tooltip>
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

                <div v-if="documentTotal > documentPageSize" class="pagination-row">
                  <a-pagination
                    :current="documentPage"
                    :page-size="documentPageSize"
                    :total="documentTotal"
                    :show-size-changer="false"
                    size="small"
                    @change="goDocumentPage"
                  />
                </div>
              </div>
            </a-spin>
          </section>

          <section class="panel qa-panel">
            <div class="panel-head">
              <div>
                <h3>问答调试面板</h3>
                <p>先检索，再问答，定位命中情况</p>
              </div>
              <a-tag color="success" v-if="indexedCount > 0">
                <CheckCircleOutlined />
                ready
              </a-tag>
            </div>

            <a-tabs v-model:activeKey="qaActiveTab" class="qa-tabs">
              <a-tab-pane key="debug" tab="调试面板">
                <div class="ask-box">
                  <a-textarea
                    v-model:value="question"
                    :rows="4"
                    placeholder="输入问题，例如：这个系统支持哪些文档格式？"
                  />
                  <div class="ask-actions">
                    <a-input-number v-model:value="topK" :min="1" :max="20" />
                    <div class="ask-buttons">
                      <a-button
                        :loading="retrieving"
                        :disabled="!selectedKnowledgeBaseId || !question.trim() || indexedCount === 0"
                        @click="retrieveOnly"
                      >
                        <template #icon><SearchOutlined /></template>
                        仅检索
                      </a-button>
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

                <div class="debug-block">
                  <div class="debug-head">
                    <div>
                      <h4>检索结果</h4>
                      <p>看命中了哪些片段、分数如何、上下文是否足够</p>
                    </div>
                    <div class="debug-summary">
                      <span class="debug-summary-line">{{ retrievalSummary }}</span>
                      <span class="document-match-count document-match-count-muted">
                        {{ retrievalResults.length }} 条
                      </span>
                    </div>
                  </div>

                  <a-empty
                    v-if="!retrievalResults.length"
                    description="点击“仅检索”或“提问”查看命中片段"
                  />

                  <div v-else class="debug-list">
                    <article v-for="(result, index) in retrievalResults" :key="result.vector_id" class="debug-row">
                      <div class="debug-row-head">
                        <div class="debug-rank">
                          <span>#{{ index + 1 }}</span>
                          <a-tag color="blue" v-if="result.score !== null">
                            score {{ result.score.toFixed(3) }}
                          </a-tag>
                        </div>
                        <div class="debug-meta">
                          <strong>{{ getResultTitle(result.metadata) }}</strong>
                          <small>{{ getResultSubtitle(result.metadata) }}</small>
                        </div>
                      </div>

                      <div class="debug-metadata">
                        <a-tag v-if="getResultFilename(result.metadata)" color="green">
                          {{ getResultFilename(result.metadata) }}
                        </a-tag>
                        <a-tag v-if="getResultSectionTitle(result.metadata)" color="default">
                          {{ getResultSectionTitle(result.metadata) }}
                        </a-tag>
                        <a-tag v-if="getResultChunkLabel(result.metadata)" color="gold">
                          {{ getResultChunkLabel(result.metadata) }}
                        </a-tag>
                      </div>

                      <details class="debug-details">
                        <summary>查看片段</summary>
                        <p v-html="highlightText(result.text, retrievalQuery)"></p>
                      </details>
                    </article>
                  </div>
                </div>

                <div v-if="answer || streaming" class="answer-block">
                  <div class="answer-label">
                    <ApiOutlined />
                    <span>Answer</span>
                    <span v-if="streaming" class="streaming-dot"></span>
                  </div>
                  <p
                    class="answer-text"
                    v-html="renderAnswerWithCitations(streaming ? streamingAnswer : answer?.answer || '')"
                    @click="handleCitationClick"
                  ></p>

                  <div v-if="!streaming && answer" class="sources">
                    <h4>引用来源</h4>
                    <article
                      v-for="source in answer.sources"
                      :key="source.vector_id"
                      :data-source-citation="source.citation"
                    >
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
                  <p>完成文档索引后，可以先检索命中片段，再查看回答与引用来源。</p>
                </div>
              </a-tab-pane>

              <a-tab-pane key="conversation" tab="对话">
                <div class="conversation-box">
                  <div class="conv-toolbar">
                    <span class="conv-count" v-if="conversation.length">
                      {{ conversation.length }} 条消息
                    </span>
                    <a-button
                      size="small"
                      :disabled="!conversation.length && !convStreaming"
                      @click="clearConversation"
                    >
                      清空对话
                    </a-button>
                  </div>

                  <div class="conv-messages" ref="convMessagesRef">
                    <a-empty
                      v-if="!conversation.length && !convStreaming"
                      description="开始多轮对话，LLM 会记住前面的上下文"
                    />

                    <div
                      v-for="msg in conversation"
                      :key="msg.id"
                      class="conv-bubble"
                      :class="msg.role"
                    >
                      <div class="conv-role">
                        {{ msg.role === 'user' ? '你' : 'Assistant' }}
                      </div>
                      <div class="conv-content">
                        <p v-if="msg.role === 'user'">{{ msg.content }}</p>
                        <p
                          v-else
                          v-html="renderAnswerWithCitations(msg.content)"
                          @click="handleCitationClick"
                        ></p>
                      </div>
                      <div
                        v-if="msg.role === 'assistant' && msg.sources.length"
                        class="conv-sources"
                      >
                        <a-collapse :bordered="false">
                          <a-collapse-panel header="引用来源 ({{ msg.sources.length }} 条)">
                            <div
                              v-for="source in msg.sources"
                              :key="source.vector_id"
                              class="conv-source-item"
                              :data-source-citation="source.citation"
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

                    <!-- 流式生成中的 assistant 消息 -->
                    <div v-if="convStreaming" class="conv-bubble assistant">
                      <div class="conv-role">
                        Assistant
                        <span class="streaming-dot"></span>
                      </div>
                      <div class="conv-content">
                        <p v-html="renderAnswerWithCitations(convStreamingAnswer)"></p>
                      </div>
                    </div>
                  </div>

                  <div class="conv-input-row">
                    <a-textarea
                      v-model:value="convInput"
                      :rows="2"
                      placeholder="输入追问…"
                      :disabled="convAsking"
                      @pressEnter="askConversation"
                    />
                    <a-button
                      type="primary"
                      :loading="convAsking"
                      :disabled="!selectedKnowledgeBaseId || !convInput.trim() || indexedCount === 0"
                      @click="askConversation"
                    >
                      <template #icon><SendOutlined /></template>
                    </a-button>
                  </div>
                </div>
              </a-tab-pane>

              <a-tab-pane key="history" tab="最近问答">
                <div class="history-block history-block-tab">
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

                      <div v-if="qaTotal > qaPageSize" class="pagination-row">
                        <a-pagination
                          :current="qaPage"
                          :page-size="qaPageSize"
                          :total="qaTotal"
                          :show-size-changer="false"
                          size="small"
                          @change="goQaPage"
                        />
                      </div>
                    </div>
                  </a-spin>
                </div>
              </a-tab-pane>
            </a-tabs>
          </section>
        </div>
      </section>
    </main>
  </a-config-provider>
</template>
