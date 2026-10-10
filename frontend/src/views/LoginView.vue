<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuth } from '../composables/useAuth'

const { login } = useAuth()
const router = useRouter()
const route = useRoute()
const form = ref({ username: '', password: '' })
const loading = ref(false)

const onSubmit = async () => {
  if (!form.value.username || !form.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await login(form.value.username, form.value.password)
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch {
    // 401 由拦截器处理；非 401 错误由 ErrorToast 显示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-card class="login-card" :bordered="false">
    <div class="login-header">
      <h1>Knowledge Agent</h1>
      <p>企业知识库问答系统</p>
    </div>
    <a-form layout="vertical" @submit.prevent="onSubmit">
      <a-form-item label="用户名">
        <a-input
          v-model:value="form.username"
          placeholder="请输入用户名"
          size="large"
          allow-clear
          @press-enter="onSubmit"
        />
      </a-form-item>
      <a-form-item label="密码">
        <a-input-password
          v-model:value="form.password"
          placeholder="请输入密码"
          size="large"
          @press-enter="onSubmit"
        />
      </a-form-item>
      <a-button
        type="primary"
        size="large"
        block
        :loading="loading"
        @click="onSubmit"
      >
        登录
      </a-button>
    </a-form>
  </a-card>
</template>

<style scoped>
.login-card {
  width: 380px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.08);
  border-radius: 12px;
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #2f6f5e;
  margin-bottom: 4px;
}

.login-header p {
  font-size: 14px;
  color: #999;
  margin: 0;
}
</style>
