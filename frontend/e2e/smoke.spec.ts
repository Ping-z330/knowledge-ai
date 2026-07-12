import { expect, test } from '@playwright/test'

test.describe('Knowledge Agent — Smoke Tests', () => {

  test('welcome page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.dashboard-hero')).toBeVisible()
    await expect(page.locator('.dashboard-hero-text h2')).toHaveText('知识库管理')
  })

  test('create knowledge base', async ({ page }) => {
    await page.goto('/')
    // 点击侧栏 + 按钮打开创建弹窗
    await page.locator('.section-line-actions .ant-btn').first().click()
    await expect(page.locator('.ant-modal')).toBeVisible()

    // 填写名称并创建
    const name = `E2E-${Date.now()}`
    await page.locator('.ant-modal input').fill(name)
    await page.locator('.ant-modal .ant-btn-primary').click()

    // 等待跳转到问答页
    await expect(page.locator('.workspace-nav-title')).toHaveText('问答')
    // 确认侧栏出现刚创建的知识库
    await expect(page.locator('.kb-item.active')).toBeVisible()
  })

  test('workspace shows conversation tab by default', async ({ page }) => {
    // 直接进入已存在的知识库
    await page.goto('/')
    const kbItem = page.locator('.kb-item').first()
    if (await kbItem.count() === 0) {
      test.skip(true, 'No knowledge base available')
      return
    }
    await kbItem.click()
    await expect(page.locator('.workspace-nav-title')).toHaveText('问答')

    // 默认显示对话 tab
    await expect(page.locator('.ant-tabs-tab-active')).toContainText('对话')
    // 对话输入框可见
    await expect(page.locator('.conv-input-row textarea')).toBeVisible()
  })

  test('switch to conversation history tab', async ({ page }) => {
    await page.goto('/')
    const kbItem = page.locator('.kb-item').first()
    if (await kbItem.count() === 0) {
      test.skip(true, 'No knowledge base available')
      return
    }
    await kbItem.click()

    // 切换到对话记录 tab
    await page.locator('.ant-tabs-tab').filter({ hasText: '对话记录' }).click()
    await expect(page.locator('.history-block')).toBeVisible()
  })

  test('navigate to documents page', async ({ page }) => {
    await page.goto('/')
    const kbItem = page.locator('.kb-item').first()
    if (await kbItem.count() === 0) {
      test.skip(true, 'No knowledge base available')
      return
    }
    await kbItem.click()

    // 点击「管理文档 →」
    await page.locator('text=管理文档').click()
    await expect(page).toHaveURL(/\/documents$/)
    await expect(page.locator('.document-toolbar')).toBeVisible()
    await expect(page.locator('.panel-head h3')).toContainText('文档管理')
  })

  test('mobile sidebar toggle', async ({ page }) => {
    // 模拟平板宽度
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.goto('/')

    // 汉堡按钮可见
    const toggle = page.locator('.sidebar-toggle')
    await expect(toggle).toBeVisible()

    // 侧栏初始隐藏
    const sidebar = page.locator('.sidebar')
    await expect(sidebar).not.toHaveClass(/open/)

    // 点击打开侧栏
    await toggle.click()
    await expect(sidebar).toHaveClass(/open/)

    // 点击遮罩关闭
    await page.locator('.sidebar-overlay').click()
    await expect(sidebar).not.toHaveClass(/open/)
  })

})
