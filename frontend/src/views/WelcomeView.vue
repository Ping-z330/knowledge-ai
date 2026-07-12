<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { DatabaseOutlined, PlusOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { useKnowledgeBases } from '../composables/useKnowledgeBases'
import { formatDate } from '../utils/format'

const router = useRouter()
const kb = useKnowledgeBases()

onMounted(() => kb.load())

const openKb = (id: string) => router.push(`/${id}`)

const quickCreate = async () => {
  const data = await kb.create()
  if (data) router.push(`/${data.id}`)
}
</script>

<template>
  <div class="dashboard">
    <!-- Hero -->
    <div class="dashboard-hero">
      <div class="dashboard-hero-text">
        <h2>Knowledge Agent</h2>
        <p>企业 RAG 知识库问答系统 — 上传文档，让 AI 基于你的资料回答问题</p>
      </div>
      <div class="dashboard-hero-actions">
        <a-button type="primary" size="large" @click="quickCreate" :loading="kb.creating.value">
          <template #icon><PlusOutlined /></template> 创建知识库
        </a-button>
      </div>
    </div>

    <!-- Stats row -->
    <div class="dashboard-stats">
      <div class="dashboard-stat">
        <DatabaseOutlined class="dashboard-stat-icon" />
        <div>
          <span class="dashboard-stat-num">{{ kb.knowledgeBases.value.length }}</span>
          <span class="dashboard-stat-label">知识库</span>
        </div>
      </div>
    </div>

    <!-- KB list -->
    <div class="dashboard-section">
      <div class="dashboard-section-head">
        <h3>我的知识库</h3>
        <a-button size="small" @click="kb.load()" :loading="kb.loading.value">刷新</a-button>
      </div>

      <a-spin :spinning="kb.loading.value">
        <div v-if="kb.knowledgeBases.value.length" class="dashboard-kb-grid">
          <article
            v-for="item in kb.knowledgeBases.value"
            :key="item.id"
            class="dashboard-kb-card"
            @click="openKb(item.id)"
          >
            <div class="dashboard-kb-card-icon"><DatabaseOutlined /></div>
            <div class="dashboard-kb-card-body">
              <h4>{{ item.name }}</h4>
              <p v-if="item.description">{{ item.description }}</p>
              <small>创建于 {{ formatDate(item.created_at) }}</small>
            </div>
          </article>
        </div>

        <div v-else-if="!kb.loading.value" class="dashboard-empty">
          <FileTextOutlined />
          <h3>还没有知识库</h3>
          <p>创建第一个知识库，开始上传文档并提问</p>
          <a-button type="primary" @click="quickCreate" :loading="kb.creating.value">
            <template #icon><PlusOutlined /></template> 创建知识库
          </a-button>
        </div>
      </a-spin>
    </div>
  </div>
</template>
