<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import {
  ApiOutlined, DeleteOutlined, FileSearchOutlined,
  InboxOutlined, ReloadOutlined,
} from '@ant-design/icons-vue'
import type { DocumentItem, KnowledgeBase } from '../types'
import { getDocumentStatusMeta } from '../composables/useDocuments'
import { formatDate } from '../utils/format'

const props = defineProps<{
  documents: DocumentItem[]
  filtered: DocumentItem[]
  selectedKnowledgeBase: KnowledgeBase | null
  selectedKnowledgeBaseId: string
  loading: boolean
  busyId: string
  documentSearch: string
  documentFilter: string
  documentPage: number
  documentPageSize: number
  documentTotal: number
  selectedIds: Set<string>
  uploadZoneVisible: boolean
  batchParsing: boolean
  batchIndexing: boolean
  reindexingAll: boolean
  filterOptions: { label: string; value: string }[]
  selectAll: boolean
  indexedCount: number
}>()

const emit = defineEmits<{
  'update:documentSearch': [value: string]
  'update:documentFilter': [value: string]
  'update:uploadZoneVisible': [value: boolean]
  'update:selectAll': [value: boolean]
  refresh: []
  goPage: [page: number]
  toggleSelect: [id: string]
  parseDocument: [item: DocumentItem]
  indexDocument: [item: DocumentItem]
  removeDocument: [item: DocumentItem]
  parsePending: []
  indexPending: []
  reindexAll: []
  batchParse: []
  batchIndex: []
  cancelSelect: []
}>()

const uploadProps: UploadProps = {
  name: 'file',
  multiple: true,
  showUploadList: false,
  accept: '.pdf,.doc,.docx,.md,.txt',
  action: props.selectedKnowledgeBaseId
    ? `/api/knowledge-bases/${props.selectedKnowledgeBaseId}/documents`
    : '',
  disabled: !props.selectedKnowledgeBaseId,
  async onChange(info) {
    if (info.file.status === 'done') {
      message.success(`「${info.file.name}」上传成功`)
      emit('refresh')
    } else if (info.file.status === 'error') {
      message.error(`「${info.file.name}」上传失败`)
    }
  },
}
</script>

<template>
  <section class="panel documents-panel">
    <div class="panel-head">
      <div>
        <h3>文档管理</h3>
        <p>PDF / Word / Markdown / TXT · 支持多文件上传</p>
      </div>
      <div class="panel-actions">
        <a-button :loading="batchParsing" :disabled="!selectedKnowledgeBaseId" @click="emit('parsePending')">
          解析待处理
        </a-button>
        <a-button type="primary" ghost :loading="batchIndexing" :disabled="!selectedKnowledgeBaseId" @click="emit('indexPending')">
          索引待处理
        </a-button>
        <a-button :loading="reindexingAll" :disabled="!selectedKnowledgeBaseId" @click="emit('reindexAll')">
          重建索引
        </a-button>
        <a-tooltip title="刷新文档列表">
          <a-button class="icon-only-button" @click="emit('refresh')">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <div class="upload-toggle-row">
      <a-button size="small" type="text" @click="emit('update:uploadZoneVisible', !uploadZoneVisible)">
        {{ uploadZoneVisible ? '收起上传区' : '展开上传区' }}
      </a-button>
    </div>
    <a-upload-dragger v-if="uploadZoneVisible" v-bind="uploadProps" class="upload-zone">
      <p class="ant-upload-drag-icon"><InboxOutlined /></p>
      <p class="ant-upload-text">拖拽或点击上传一个或多个文档</p>
      <p class="ant-upload-hint">上传后可批量解析和索引</p>
    </a-upload-dragger>

    <div class="document-toolbar">
      <a-input-search
        :value="documentSearch"
        allow-clear
        placeholder="搜索文件名或类型"
        @update:value="emit('update:documentSearch', $event)"
      />
      <a-select
        :value="documentFilter"
        class="document-filter-select"
        :options="filterOptions"
        :dropdown-match-select-width="false"
        @update:value="emit('update:documentFilter', $event)"
      />
      <span class="document-match-count document-match-count-muted">
        {{ filtered.length }} / {{ documents.length }}
      </span>
    </div>

    <a-spin :spinning="loading">
      <div v-if="selectedIds.size > 0" class="batch-bar">
        <span>已选 {{ selectedIds.size }} 个文档</span>
        <a-button size="small" :loading="batchParsing" @click="emit('batchParse')">批量解析</a-button>
        <a-button size="small" type="primary" ghost :loading="batchIndexing" @click="emit('batchIndex')">批量索引</a-button>
        <a-button size="small" @click="emit('cancelSelect')">取消选择</a-button>
      </div>

      <div v-if="documents.length > 0 && !selectedIds.size" class="document-list-header">
        <a-checkbox
          :checked="selectAll"
          @change="emit('update:selectAll', ($event.target as HTMLInputElement).checked)"
        />
        <span class="document-list-header-text">全选</span>
      </div>

      <div class="document-list">
        <article v-for="item in filtered" :key="item.id" class="document-row">
          <a-checkbox :checked="selectedIds.has(item.id)" @change="emit('toggleSelect', item.id)" />
          <div class="document-main">
            <FileSearchOutlined class="file-icon" />
            <div>
              <h4>{{ item.filename }}</h4>
              <p>{{ item.content_type }} · {{ formatDate(item.created_at) }}</p>
              <p v-if="item.error_message" class="error-text">{{ item.error_message }}</p>
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
              <a-button size="small"
                :disabled="item.parse_status === 'running' || item.index_status === 'running'"
                :loading="busyId === item.id"
                @click="emit('parseDocument', item)"
              >
                <template #icon><FileSearchOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="索引文档">
              <a-button size="small" type="primary" ghost
                :disabled="item.parse_status !== 'parsed' || item.index_status === 'running'"
                :loading="busyId === item.id"
                @click="emit('indexDocument', item)"
              >
                <template #icon><ApiOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-popconfirm title="删除这个文档？" @confirm="emit('removeDocument', item)">
              <a-tooltip title="删除文档">
                <a-button size="small" danger><template #icon><DeleteOutlined /></template></a-button>
              </a-tooltip>
            </a-popconfirm>
          </div>
        </article>

        <a-empty v-if="!documents.length" description="上传第一份文档开始构建知识库" />
        <a-empty v-else-if="!filtered.length" description="没有匹配的文档" />

        <div v-if="documentTotal > documentPageSize" class="pagination-row">
          <a-pagination
            :current="documentPage" :page-size="documentPageSize" :total="documentTotal"
            :show-size-changer="false" size="small"
            @change="(p: number) => emit('goPage', p)"
          />
        </div>
      </div>
    </a-spin>
  </section>
</template>
