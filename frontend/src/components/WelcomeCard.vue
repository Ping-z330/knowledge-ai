<script setup lang="ts">
import { DatabaseOutlined } from '@ant-design/icons-vue'
</script>

<template>
  <div class="welcome-card">
    <div class="welcome-icon"><DatabaseOutlined /></div>
    <h2>欢迎使用 Knowledge Agent</h2>
    <p>企业 RAG 知识库问答系统 — 上传文档，让 AI 基于你的资料回答问题。</p>
    <div class="welcome-steps">
      <div><strong>1.</strong> 在左侧创建一个知识库</div>
      <div><strong>2.</strong> 上传 PDF / Word / Markdown 文档</div>
      <div><strong>3.</strong> 点击解析 → 索引</div>
      <div><strong>4.</strong> 开始提问或对话</div>
    </div>
  </div>
</template>
