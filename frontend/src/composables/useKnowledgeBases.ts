import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { KnowledgeBase } from '../types'
import { api } from '../utils/api'

export function useKnowledgeBases() {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const selectedId = ref('')
  const loading = ref(false)
  const creating = ref(false)
  const kbSearch = ref('')
  const createForm = ref({ name: '', description: '' })

  const filtered = computed(() => {
    const s = kbSearch.value.trim().toLowerCase()
    if (!s) return knowledgeBases.value
    return knowledgeBases.value.filter(
      (kb) => kb.name.toLowerCase().includes(s) || kb.description.toLowerCase().includes(s),
    )
  })

  const selected = computed(() =>
    knowledgeBases.value.find((item) => item.id === selectedId.value) ?? null,
  )

  const load = async () => {
    loading.value = true
    try {
      const { data } = await api.get<KnowledgeBase[]>('/knowledge-bases')
      knowledgeBases.value = data
    } finally {
      loading.value = false
    }
  }

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
      return data
    } finally {
      creating.value = false
    }
  }

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
