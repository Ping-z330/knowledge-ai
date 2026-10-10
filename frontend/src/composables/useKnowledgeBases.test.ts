import { describe, it, expect } from 'vitest'
import { useKnowledgeBases } from './useKnowledgeBases'
import type { KnowledgeBase } from '../types'

function makeKb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    id: '1',
    name: '测试库',
    description: '描述内容',
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('useKnowledgeBases', () => {
  describe('filtered', () => {
    it('无搜索词时返回全部', () => {
      const { knowledgeBases, filtered } = useKnowledgeBases()
      knowledgeBases.value = [makeKb({ id: '1' }), makeKb({ id: '2' })]
      expect(filtered.value).toHaveLength(2)
    })

    it('按名称匹配', () => {
      const { knowledgeBases, kbSearch, filtered } = useKnowledgeBases()
      knowledgeBases.value = [
        makeKb({ id: '1', name: '产品文档' }),
        makeKb({ id: '2', name: '技术手册' }),
      ]
      kbSearch.value = '产品'
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('1')
    })

    it('按描述匹配', () => {
      const { knowledgeBases, kbSearch, filtered } = useKnowledgeBases()
      knowledgeBases.value = [
        makeKb({ id: '1', description: '产品相关资料' }),
        makeKb({ id: '2', description: '技术相关资料' }),
      ]
      kbSearch.value = '产品'
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('1')
    })

    it('description 为 null 时不崩溃', () => {
      const { knowledgeBases, kbSearch, filtered } = useKnowledgeBases()
      knowledgeBases.value = [
        // 模拟后端返回 null 的异常场景
        makeKb({ id: '1', description: null as unknown as string }),
        makeKb({ id: '2', name: '产品', description: '产品文档' }),
      ]
      kbSearch.value = '产品'
      expect(() => filtered.value).not.toThrow()
      expect(filtered.value).toHaveLength(1)
      expect(filtered.value[0].id).toBe('2')
    })

    it('搜索大小写不敏感', () => {
      const { knowledgeBases, kbSearch, filtered } = useKnowledgeBases()
      knowledgeBases.value = [makeKb({ id: '1', name: 'Product' })]
      kbSearch.value = 'PRODUCT'
      expect(filtered.value).toHaveLength(1)
    })

    it('空格搜索词等价于无搜索', () => {
      const { knowledgeBases, kbSearch, filtered } = useKnowledgeBases()
      knowledgeBases.value = [makeKb({ id: '1' }), makeKb({ id: '2' })]
      kbSearch.value = '   '
      expect(filtered.value).toHaveLength(2)
    })
  })

  describe('selected', () => {
    it('返回选中的知识库', () => {
      const { knowledgeBases, selectedId, selected } = useKnowledgeBases()
      knowledgeBases.value = [makeKb({ id: '1' }), makeKb({ id: '2' })]
      selectedId.value = '2'
      expect(selected.value?.id).toBe('2')
    })

    it('未匹配时返回 null', () => {
      const { knowledgeBases, selectedId, selected } = useKnowledgeBases()
      knowledgeBases.value = [makeKb({ id: '1' })]
      selectedId.value = 'nonexistent'
      expect(selected.value).toBeNull()
    })

    it('未选中时返回 null', () => {
      const { selected } = useKnowledgeBases()
      expect(selected.value).toBeNull()
    })
  })
})
