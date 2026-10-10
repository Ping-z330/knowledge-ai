import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { KnowledgeBase } from '../types'
import { api } from '../utils/api'

export function useKnowledgeBases() {
  // 核心状态
  // 所有数据库数据，渲染列表
  const knowledgeBases = ref<KnowledgeBase[]>([])
  // 当前选中的知识库，确定操作目标
  const selectedId = ref('')
  const loading = ref(false)
  const creating = ref(false)
  // 搜索关键词，控制过滤
  const kbSearch = ref('')
  const createForm = ref({ name: '', description: '' })

  // 客户端过滤（名称+描述匹配）
  const filtered = computed(() => {
    const s = kbSearch.value.trim().toLowerCase()
    if (!s) return knowledgeBases.value
    return knowledgeBases.value.filter(
      (kb) =>
        kb.name.toLowerCase().includes(s) ||
        (kb.description ?? '').toLowerCase().includes(s),
    )
  })

  const selected = computed(() =>
    knowledgeBases.value.find((item) => item.id === selectedId.value) ?? null,
  )

  // 覆盖knowledgebases
  const load = async () => {
    loading.value = true
    try {
      const { data } = await api.get<KnowledgeBase[]>('/knowledge-bases')
      knowledgeBases.value = data
    } finally {
      loading.value = false
    }
  }

  // 插入列表头部+自动选中
  const create = async () => {
    if (!createForm.value.name.trim()) return
    creating.value = true
    try {
      const { data } = await api.post<KnowledgeBase>('/knowledge-bases', {
        name: createForm.value.name.trim(),
        description: createForm.value.description.trim(),
      })
      knowledgeBases.value = [data, ...knowledgeBases.value]
      createForm.value = { name: '', description: '' }
      selectedId.value = data.id
      message.success(`已创建知识库「${data.name}」`)
      return data
    } finally {
      creating.value = false
    }
  }

  // 过滤掉删除的知识库，并清空选中状态
  const remove = async (item: KnowledgeBase) => {
    try {
      await api.delete(`/knowledge-bases/${item.id}`)
      knowledgeBases.value = knowledgeBases.value.filter((kb) => kb.id !== item.id)
      if (selectedId.value === item.id) selectedId.value = ''
      message.success(`已删除知识库「${item.name}」`)
    } catch {
      message.error('删除失败')
    }
  }

  return {
    knowledgeBases,
    selectedId,
    selected,
    loading,
    creating,
    kbSearch,
    createForm,
    filtered,
    load,
    create,
    remove,
  }
}
