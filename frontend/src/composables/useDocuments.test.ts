import { describe, it, expect } from 'vitest'
import { ref, effectScope } from 'vue'
import { useDocuments } from './useDocuments'
import type { DocumentItem } from '../types'

function makeDoc(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    id: '1',
    knowledge_base_id: 'kb1',
    filename: 'test.pdf',
    content_type: 'application/pdf',
    storage_path: '/tmp/test.pdf',
    parse_status: 'uploaded',
    index_status: 'pending',
    error_message: null,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('useDocuments', () => {
  function setup(docs: DocumentItem[]) {
    const scope = effectScope()
    let result!: ReturnType<typeof useDocuments>
    scope.run(() => {
      const kbId = ref('kb1')
      result = useDocuments(kbId)
      result.documents.value = docs
    })
    return { scope, ...result }
  }

  describe('filtered — 搜索', () => {
    it('按文件名匹配', () => {
      const { documents, documentSearch, filtered } = setup([
        makeDoc({ id: '1', filename: '产品手册.pdf' }),
        makeDoc({ id: '2', filename: '技术规范.pdf' }),
      ])
      documents.value = [
        makeDoc({ id: '1', filename: '产品手册.pdf' }),
        makeDoc({ id: '2', filename: '技术规范.pdf' }),
      ]
      documentSearch.value = '产品'
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('1')
    })

    it('按 content_type 匹配', () => {
      const { documentSearch, filtered } = setup([
        makeDoc({ id: '1', filename: 'alpha', content_type: 'application/pdf' }),
        makeDoc({ id: '2', filename: 'beta', content_type: 'text/plain' }),
      ])
      documentSearch.value = 'pdf'
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('1')
    })

    it('无搜索词时返回全部（受 filter 影响）', () => {
      const { filtered } = setup([
        makeDoc({ id: '1' }),
        makeDoc({ id: '2' }),
      ])
      expect(filtered.value).toHaveLength(2)
    })
  })

  describe('filtered — 状态过滤', () => {
    it('pending_parse 包含 uploaded 和 failed', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'uploaded', index_status: 'pending' }),
        makeDoc({ id: '2', parse_status: 'failed', index_status: 'pending' }),
        makeDoc({ id: '3', parse_status: 'parsed', index_status: 'indexed' }),
      ])
      documentFilter.value = 'pending_parse'
      expect(filtered.value).toHaveLength(2)
    })

    it('parsing 只包含解析中', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'running', index_status: 'pending' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'pending' }),
      ])
      documentFilter.value = 'parsing'
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('1')
    })

    it('pending_index 包含已解析但索引待处理/失败', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'parsed', index_status: 'pending' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'failed' }),
        makeDoc({ id: '3', parse_status: 'parsed', index_status: 'indexed' }),
        makeDoc({ id: '4', parse_status: 'uploaded', index_status: 'pending' }),
      ])
      documentFilter.value = 'pending_index'
      expect(filtered.value).toHaveLength(2)
    })

    it('indexing 只包含索引中', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'parsed', index_status: 'running' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'indexed' }),
      ])
      documentFilter.value = 'indexing'
      expect(filtered.value).toHaveLength(1)
    })

    it('indexed 只包含已索引', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'parsed', index_status: 'indexed' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'pending' }),
      ])
      documentFilter.value = 'indexed'
      expect(filtered.value).toHaveLength(1)
    })

    it('failed 包含解析或索引失败', () => {
      const { documentFilter, filtered } = setup([
        makeDoc({ id: '1', parse_status: 'failed', index_status: 'pending' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'failed' }),
        makeDoc({ id: '3', parse_status: 'parsed', index_status: 'indexed' }),
      ])
      documentFilter.value = 'failed'
      expect(filtered.value).toHaveLength(2)
    })
  })

  describe('计算属性', () => {
    it('indexedCount 只统计已索引文档', () => {
      const { indexedCount } = setup([
        makeDoc({ id: '1', index_status: 'indexed' }),
        makeDoc({ id: '2', index_status: 'pending' }),
        makeDoc({ id: '3', index_status: 'indexed' }),
      ])
      expect(indexedCount.value).toBe(2)
    })

    it('parsedCount 只统计已解析文档', () => {
      const { parsedCount } = setup([
        makeDoc({ id: '1', parse_status: 'parsed' }),
        makeDoc({ id: '2', parse_status: 'uploaded' }),
        makeDoc({ id: '3', parse_status: 'parsed' }),
      ])
      expect(parsedCount.value).toBe(2)
    })

    it('hasRunning 检测解析中或索引中', () => {
      const { hasRunning } = setup([
        makeDoc({ id: '1', parse_status: 'running', index_status: 'pending' }),
      ])
      expect(hasRunning.value).toBe(true)

      const { hasRunning: hasRunning2 } = setup([
        makeDoc({ id: '1', parse_status: 'parsed', index_status: 'running' }),
      ])
      expect(hasRunning2.value).toBe(true)

      const { hasRunning: hasRunning3 } = setup([
        makeDoc({ id: '1', parse_status: 'parsed', index_status: 'indexed' }),
      ])
      expect(hasRunning3.value).toBe(false)
    })
  })

  describe('filterOptions', () => {
    it('统计各状态数量', () => {
      const { filterOptions } = setup([
        makeDoc({ id: '1', parse_status: 'uploaded', index_status: 'pending' }),
        makeDoc({ id: '2', parse_status: 'parsed', index_status: 'indexed' }),
        makeDoc({ id: '3', parse_status: 'failed', index_status: 'pending' }),
      ])
      const opt = (v: string) => filterOptions.value.find((o) => o.value === v)
      expect(opt('all')?.label).toContain('3')
      expect(opt('pending_parse')?.label).toContain('2') // uploaded + failed
      expect(opt('indexed')?.label).toContain('1')
      expect(opt('failed')?.label).toContain('1')
    })
  })
})
