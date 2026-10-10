# Knowledge Agent Frontend

Knowledge Agent 的 Vue 3 管理端，提供知识库管理、文档处理、流式问答、
引用联动、多轮对话和 Agentic 调试信息展示。

## Local development

先在项目根目录启动 FastAPI 后端，然后运行：

```bash
npm install
npm run dev
```

开发地址为 `http://localhost:5173`，Vite 将 `/api` 请求代理到
`http://127.0.0.1:8000`。

## Checks

```bash
npm run build
npm run test:e2e
```

技术栈：Vue 3、TypeScript、Vite、Ant Design Vue、Vue Router、Axios 和
Playwright。完整项目说明见根目录 [`README.md`](../README.md)。
