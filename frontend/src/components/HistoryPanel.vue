<script setup lang="ts">
import { MessageOutlined, DeleteOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { Conversation } from '../types'
import { formatDate } from '../utils/format'

defineProps<{
  conversations: Conversation[]
  loading: boolean
  conversationId: string
}>()

const emit = defineEmits<{
  select: [item: Conversation]
  delete: [item: Conversation]
  refresh: []
  newConversation: []
}>()
</script>

<template>
  <div class="history-block history-block-tab">
    <div class="history-head">
      <div><h4>对话列表</h4><p>{{ conversations.length ? `${conversations.length} 个对话` : '开始一段新对话' }}</p></div>
      <div class="history-head-actions">
        <a-button size="small" type="primary" @click="emit('newConversation')">
          <template #icon><PlusOutlined /></template>
          新对话
        </a-button>
        <a-button size="small" @click="emit('refresh')">
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="history-list">
        <article
          v-for="conv in conversations"
          :key="conv.id"
          class="history-row"
          :class="{ active: conv.id === conversationId }"
          @click="emit('select', conv)"
        >
          <div class="history-main">
            <MessageOutlined />
            <div>
              <h5>{{ conv.title || '新对话' }}</h5>
              <small>{{ formatDate(conv.updated_at || conv.created_at) }}</small>
            </div>
          </div>
          <a-popconfirm title="删除这段对话？" @confirm.stop="emit('delete', conv)">
            <a-button size="small" danger @click.stop>
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-popconfirm>
        </article>

        <a-empty v-if="!conversations.length" description="还没有对话记录" />
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.history-head-actions {
  display: flex;
  gap: 6px;
}
.history-row.active {
  background: #f0f7f0;
  border-color: #2f6f5e;
}
</style>
