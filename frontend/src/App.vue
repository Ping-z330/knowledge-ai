<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { KnowledgeBase } from './types'
import { useKnowledgeBases } from './composables/useKnowledgeBases'
import Sidebar from './components/Sidebar.vue'
import ErrorToast from './components/ErrorToast.vue'

const route = useRoute()
const router = useRouter()
const kb = useKnowledgeBases()

// 登录页等 public 路由绕过 shell，不加载侧栏
const isPublic = computed(() => !!route.meta.public)

// 侧栏高亮从 URL 读取，不依赖 composable 内部状态
const selectedId = computed(() => (route.params.kbId as string) || '')

const selectKb = (id: string) => {
  if (id && id !== selectedId.value) {
    router.push(`/${id}`)
  }
}

const createKb = async (name: string, description: string) => {
  kb.createForm.value = { name, description }
  const data = await kb.create()
  if (data) {
    router.push(`/${data.id}`)
  }
}

const removeKb = async (item: KnowledgeBase) => {
  await kb.remove(item)
  if (selectedId.value === item.id) {
    router.push('/')
  }
}

// 未登录时不加载知识库列表，避免连环 401
onMounted(() => {
  if (!isPublic.value) kb.load()
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
    <ErrorToast />
    <main v-if="isPublic" class="public-view">
      <router-view />
    </main>
    <main v-else class="shell">
      <Sidebar
        :knowledgeBases="kb.knowledgeBases.value"
        :filtered="kb.filtered.value"
        :selectedId="selectedId"
        :loading="kb.loading.value"
        :creating="kb.creating.value"
        :kbSearch="kb.kbSearch.value"
        @update:kbSearch="(v: string) => kb.kbSearch.value = v"
        @select="selectKb"
        @create="createKb"
        @remove="removeKb"
        @refresh="kb.load"
      />

      <section class="workspace" :class="{ 'workspace-qa': $route.name === 'workspace' }">
        <router-view />
      </section>
    </main>
  </a-config-provider>
</template>

<style scoped>
.public-view {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}
</style>
