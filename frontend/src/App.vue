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

onMounted(() => kb.load())
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
    <main class="shell">
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
