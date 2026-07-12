<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ExclamationCircleOutlined } from '@ant-design/icons-vue'

interface Toast {
  id: number
  message: string
}

let nextId = 0
const toasts = ref<Toast[]>([])

function handleError(e: Event) {
  const detail = (e as CustomEvent).detail as string
  const id = nextId++
  toasts.value = [...toasts.value, { id, message: detail }]
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 6000)
}

onMounted(() => window.addEventListener('app-error', handleError))
onUnmounted(() => window.removeEventListener('app-error', handleError))
</script>

<template>
  <Teleport to="body">
    <div class="error-toast-stack">
      <TransitionGroup name="toast-fade">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="error-toast"
        >
          <ExclamationCircleOutlined />
          <span>{{ toast.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.error-toast-stack {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: grid;
  gap: 8px;
  max-width: 520px;
  pointer-events: none;
}
.error-toast {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 16px;
  background: #b42318;
  color: #fff;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  box-shadow: 0 8px 24px rgba(180, 35, 24, 0.3);
  pointer-events: auto;
  cursor: pointer;
}
.error-toast .anticon {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 14px;
}
.toast-fade-enter-active { transition: all 0.3s ease; }
.toast-fade-leave-active { transition: all 0.3s ease; }
.toast-fade-enter-from { opacity: 0; transform: translateY(12px); }
.toast-fade-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
