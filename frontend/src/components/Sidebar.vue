<script setup lang="ts">
import { ref } from 'vue'
import { DatabaseOutlined, DeleteOutlined, MenuOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { KnowledgeBase } from '../types'

defineProps<{
  knowledgeBases: KnowledgeBase[]
  filtered: KnowledgeBase[]
  selectedId: string
  loading: boolean
  creating: boolean
  kbSearch: string
}>()

const emit = defineEmits<{
  'update:kbSearch': [value: string]
  select: [id: string]
  create: [name: string, description: string]
  remove: [item: KnowledgeBase]
  refresh: []
}>()

const modalOpen = ref(false)
const formName = ref('')
const formDesc = ref('')
const sidebarOpen = ref(false)

const openCreate = () => {
  formName.value = ''
  formDesc.value = ''
  modalOpen.value = true
}

const handleCreate = () => {
  if (!formName.value.trim()) return
  emit('create', formName.value.trim(), formDesc.value.trim())
  modalOpen.value = false
}

const selectKb = (id: string) => {
  emit('select', id)
  sidebarOpen.value = false
}
</script>

<template>
  <!-- 移动端汉堡按钮 -->
  <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" aria-label="菜单">
    <MenuOutlined />
  </button>

  <!-- 移动端遮罩 -->
  <div v-if="sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false" />

  <aside class="sidebar" :class="{ open: sidebarOpen }">
    <div class="brand">
      <div class="brand-mark"><DatabaseOutlined /></div>
      <div>
        <p class="eyebrow">Knowledge Agent</p>
        <h1>企业知识库</h1>
      </div>
    </div>

    <section class="kb-list">
      <div class="section-line">
        <span>知识库</span>
        <div class="section-line-actions">
          <a-button type="text" size="small" @click="openCreate">
            <template #icon><PlusOutlined /></template>
          </a-button>
          <a-button type="text" size="small" @click="emit('refresh')">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </div>
      </div>

      <a-input
        v-if="knowledgeBases.length > 3"
        :value="kbSearch"
        placeholder="搜索知识库…"
        allow-clear
        size="small"
        class="kb-search"
        @update:value="emit('update:kbSearch', $event)"
      />

      <a-spin :spinning="loading">
        <div
          v-for="item in filtered"
          :key="item.id"
          class="kb-item"
          :class="{ active: item.id === selectedId }"
          @click="selectKb(item.id)"
        >
          <div class="kb-item-main">
            <span>{{ item.name }}</span>
            <small>{{ item.description || '无描述' }}</small>
          </div>
          <a-popconfirm
            title="删除这个知识库？所有文档和索引数据都会被清除。"
            ok-text="确认删除"
            cancel-text="取消"
            ok-type="danger"
            @confirm.stop="emit('remove', item)"
            @cancel.stop
          >
            <a-button size="small" type="text" danger class="kb-delete-btn" @click.stop>
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-popconfirm>
        </div>
        <a-empty v-if="!knowledgeBases.length" description="还没有知识库" />
        <a-empty v-else-if="!filtered.length" description="没有匹配的知识库" />
      </a-spin>
    </section>

    <a-modal
      v-model:open="modalOpen"
      title="创建知识库"
      ok-text="创建"
      cancel-text="取消"
      :confirm-loading="creating"
      @ok="handleCreate"
    >
      <a-input
        v-model:value="formName"
        placeholder="知识库名称"
        style="margin-bottom: 12px"
      />
      <a-textarea
        v-model:value="formDesc"
        placeholder="描述（可选）"
        :rows="2"
      />
    </a-modal>
  </aside>
</template>
