<script setup lang="ts">
import { ClockCircleOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { QuestionAnswer } from '../types'
import { formatDate } from '../utils/format'

defineProps<{
  questionAnswers: QuestionAnswer[]
  loading: boolean
  busyAnswerId: string
  qaPage: number
  qaPageSize: number
  qaTotal: number
}>()

const emit = defineEmits<{
  select: [item: QuestionAnswer]
  delete: [item: QuestionAnswer]
  refresh: []
  goPage: [page: number]
}>()
</script>

<template>
  <div class="history-block history-block-tab">
    <div class="history-head">
      <div><h4>最近问答</h4><p>保存当前知识库的问答记录</p></div>
      <a-button size="small" @click="emit('refresh')"><template #icon><ReloadOutlined /></template></a-button>
    </div>

    <a-spin :spinning="loading">
      <div class="history-list">
        <article v-for="item in questionAnswers" :key="item.id" class="history-row" @click="emit('select', item)">
          <div class="history-main">
            <ClockCircleOutlined />
            <div>
              <h5>{{ item.question }}</h5>
              <p>{{ item.answer }}</p>
              <small>{{ formatDate(item.created_at) }} · top {{ item.top_k }}</small>
            </div>
          </div>
          <a-popconfirm title="删除这条问答历史？" @confirm.stop="emit('delete', item)">
            <a-button size="small" danger :loading="busyAnswerId === item.id" @click.stop>
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-popconfirm>
        </article>

        <a-empty v-if="!questionAnswers.length" description="还没有问答历史" />

        <div v-if="qaTotal > qaPageSize" class="pagination-row">
          <a-pagination
            :current="qaPage" :page-size="qaPageSize" :total="qaTotal"
            :show-size-changer="false" size="small"
            @change="(p: number) => emit('goPage', p)"
          />
        </div>
      </div>
    </a-spin>
  </div>
</template>
