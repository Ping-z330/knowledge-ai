<script setup lang="ts">
import { DatabaseOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { KnowledgeBase } from '../types'

defineProps<{
  knowledgeBases: KnowledgeBase[]
  filtered: KnowledgeBase[]
  selectedId: string
  loading: boolean
  creating: boolean
  kbSearch: string
  createForm: { name: string; description: string }
}>()

const emit = defineEmits<{
  'update:kbSearch': [value: string]
  'update:createForm': [value: { name: string; description: string }]
  select: [id: string]
  create: []
  remove: [item: KnowledgeBase]
  refresh: []
}>()
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark"><DatabaseOutlined /></div>
      <div>
        <p class="eyebrow">Knowledge Agent</p>
        <h1>企业知识库</h1>
      </div>
    </div>

    <section class="create-panel">
      <a-input
        :value="createForm.name"
        placeholder="新知识库名称"
        @update:value="emit('update:createForm', { ...createForm, name: $event })"
      />
      <a-textarea
        :value="createForm.description"
        placeholder="描述"
        :rows="2"
        @update:value="emit('update:createForm', { ...createForm, description: $event })"
      />
      <a-button type="primary" block :loading="creating" @click="emit('create')">
        <template #icon><PlusOutlined /></template>
        创建知识库
      </a-button>
    </section>

    <section class="kb-list">
      <div class="section-line">
        <span>知识库</span>
        <a-button type="text" size="small" @click="emit('refresh')">
          <template #icon><ReloadOutlined /></template>
        </a-button>
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
          @click="emit('select', item.id)"
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
  </aside>
</template>
