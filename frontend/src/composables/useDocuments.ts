import { computed, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import type { DocumentItem, PaginatedResponse, BatchTaskResponse, DocumentStatusMeta } from '../types'
import { api } from '../utils/api'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'

export function useDocuments(selectedKnowledgeBaseId: Ref<string>) {
  const documents = ref<DocumentItem[]>([])
  const loading = ref(false)
  const busyId = ref('')
  const documentSearch = ref('')
  const documentFilter = ref('all')
  const documentPage = ref(1)
  const documentPageSize = 50
  const documentTotal = ref(0)
  const selectedIds = ref<Set<string>>(new Set())
  const uploadZoneVisible = ref(true)
  const batchParsing = ref(false)
  const batchIndexing = ref(false)
  const reindexingAll = ref(false)

  let pollTimer: number | undefined

  const stopPolling = () => {
    if (pollTimer !== undefined) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
    }
  }

  const startPolling = () => {
    if (pollTimer !== undefined) return
    pollTimer = window.setInterval(() => {
      if (!selectedKnowledgeBaseId.value || loading.value) return
      if (!hasRunning.value) { stopPolling(); return }
      load()
    }, 2000)
  }

  const indexedCount = computed(
    () => documents.value.filter((item) => item.index_status === 'indexed').length,
  )

  const hasRunning = computed(() =>
    documents.value.some(
      (item) => item.parse_status === 'running' || item.index_status === 'running',
    ),
  )

  const parsedCount = computed(
    () => documents.value.filter((item) => item.parse_status === 'parsed').length,
  )

  function matchesFilter(item: DocumentItem, filter: string) {
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

  const filtered = computed(() => {
    const search = documentSearch.value.trim().toLowerCase()
    return documents.value.filter((item) => {
      const matchesSearch =
        !search ||
        item.filename.toLowerCase().includes(search) ||
        item.content_type.toLowerCase().includes(search)
      return matchesSearch && matchesFilter(item, documentFilter.value)
    })
  })

  const filterOptions = computed(() => {
    const count = (f: string) => documents.value.filter((d) => matchesFilter(d, f)).length
    return [
      { label: `全部 ${documents.value.length}`, value: 'all' },
      { label: `待解析 ${count('pending_parse')}`, value: 'pending_parse' },
      { label: `解析中 ${count('parsing')}`, value: 'parsing' },
      { label: `待索引 ${count('pending_index')}`, value: 'pending_index' },
      { label: `索引中 ${count('indexing')}`, value: 'indexing' },
      { label: `已索引 ${count('indexed')}`, value: 'indexed' },
      { label: `失败 ${count('failed')}`, value: 'failed' },
    ]
  })

  const selectAll = computed({
    get: () => filtered.value.length > 0 && filtered.value.every((d) => selectedIds.value.has(d.id)),
    set: (val: boolean) => {
      if (val) filtered.value.forEach((d) => selectedIds.value.add(d.id))
      else filtered.value.forEach((d) => selectedIds.value.delete(d.id))
      selectedIds.value = new Set(selectedIds.value)
    },
  })

  const load = async () => {
    if (!selectedKnowledgeBaseId.value) {
      documents.value = []
      stopPolling()
      return
    }
    loading.value = true
    try {
      const offset = (documentPage.value - 1) * documentPageSize
      const { data } = await api.get<PaginatedResponse<DocumentItem>>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents`,
        { params: { limit: documentPageSize, offset } },
      )
      documents.value = data.items
      documentTotal.value = data.total
      if (hasRunning.value) startPolling()
    } finally {
      loading.value = false
    }
  }

  const goPage = async (page: number) => {
    documentPage.value = page
    await load()
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selectedIds.value = next
  }

  const parseDocument = async (item: DocumentItem) => {
    busyId.value = item.id
    try {
      await api.post(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}/parse`)
      await load()
    } finally {
      busyId.value = ''
    }
  }

  const indexDocument = async (item: DocumentItem) => {
    busyId.value = item.id
    try {
      await api.post(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}/index`)
      await load()
    } finally {
      busyId.value = ''
    }
  }

  const removeDocument = async (item: DocumentItem) => {
    busyId.value = item.id
    try {
      await api.delete(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.id}`)
      await load()
    } finally {
      busyId.value = ''
    }
  }

  const parsePending = async () => {
    if (!selectedKnowledgeBaseId.value) return
    batchParsing.value = true
    try {
      const { data } = await api.post<BatchTaskResponse>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/parse-pending`,
      )
      message.info(data.scheduled ? `已触发 ${data.scheduled} 个解析任务` : '没有待解析文档')
      await load()
    } finally {
      batchParsing.value = false
    }
  }

  const indexPending = async () => {
    if (!selectedKnowledgeBaseId.value) return
    batchIndexing.value = true
    try {
      const { data } = await api.post<BatchTaskResponse>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/index-pending`,
      )
      message.info(data.scheduled ? `已触发 ${data.scheduled} 个索引任务` : '没有待索引文档')
      await load()
    } finally {
      batchIndexing.value = false
    }
  }

  const reindexAll = async () => {
    if (!selectedKnowledgeBaseId.value) return
    reindexingAll.value = true
    try {
      const { data } = await api.post<BatchTaskResponse>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/reindex-all`,
      )
      message.info(data.scheduled ? `已触发 ${data.scheduled} 个重建索引任务` : '没有已解析文档')
      await load()
    } finally {
      reindexingAll.value = false
    }
  }

  const batchParse = async () => {
    if (!selectedKnowledgeBaseId.value || !selectedIds.value.size) return
    batchParsing.value = true
    let count = 0
    try {
      for (const id of selectedIds.value) {
        const doc = documents.value.find((d) => d.id === id)
        if (!doc || doc.parse_status === 'running') continue
        await api.post(`/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/${id}/parse`)
        count++
      }
      message.success(`已触发 ${count} 个解析任务`)
      selectedIds.value = new Set()
      await load()
    } catch {
      message.error('部分解析请求失败')
    } finally {
      batchParsing.value = false
    }
  }

  const batchIndex = async () => {
    if (!selectedKnowledgeBaseId.value || !selectedIds.value.size) return
    batchIndexing.value = true
    let count = 0
    try {
      for (const id of selectedIds.value) {
        const doc = documents.value.find((d) => d.id === id)
        if (!doc || doc.index_status === 'running' || doc.parse_status !== 'parsed') continue
        await api.post(`/knowledge-bases/${selectedKnowledgeBaseId.value}/documents/${id}/index`)
        count++
      }
      message.success(`已触发 ${count} 个索引任务`)
      selectedIds.value = new Set()
      await load()
    } catch {
      message.error('部分索引请求失败')
    } finally {
      batchIndexing.value = false
    }
  }

  // 重置分页和选择
  watch(selectedKnowledgeBaseId, () => {
    documentPage.value = 1
    selectedIds.value = new Set()
  })

  return {
    documents, loading, busyId, documentSearch, documentFilter, documentPage,
    documentPageSize, documentTotal, selectedIds, uploadZoneVisible,
    batchParsing, batchIndexing, reindexingAll,
    indexedCount, hasRunning, parsedCount, filtered, filterOptions, selectAll,
    load, goPage, toggleSelect,
    parseDocument, indexDocument, removeDocument,
    parsePending, indexPending, reindexAll, batchParse, batchIndex,
    stopPolling,
  }
}

export function getDocumentStatusMeta(item: DocumentItem): DocumentStatusMeta {
  if (item.parse_status === 'failed' || item.index_status === 'failed') {
    return {
      label: '失败', tone: 'error', icon: ExclamationCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }
  if (item.parse_status === 'running') {
    return {
      label: '解析中', tone: 'processing', icon: SyncOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }
  if (item.index_status === 'running') {
    return {
      label: '索引中', tone: 'processing', icon: SyncOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }
  if (item.index_status === 'indexed') {
    return {
      label: '已就绪', tone: 'success', icon: CheckCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }
  if (item.parse_status === 'parsed') {
    return {
      label: '待索引', tone: 'default', icon: ClockCircleOutlined,
      detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
    }
  }
  return {
    label: '待解析', tone: 'default', icon: ClockCircleOutlined,
    detail: `解析: ${item.parse_status} · 索引: ${item.index_status}`,
  }
}
