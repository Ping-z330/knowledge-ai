"""检索质量评估测试集。

每道题：
- question: 用户问题
- relevant_keywords: 期望检索结果中包含的关键词（用于自动判断是否命中）
- expected_answer_clues: 期望答案中应包含的关键信息
"""

EVAL_QUESTIONS = [
    {
        "question": "系统支持哪些文档格式？",
        "relevant_keywords": ["PDF", "DOCX", "Markdown", "TXT", "md", "txt"],
        "expected_answer_clues": ["PDF", "DOCX", "Markdown", "TXT"],
    },
    {
        "question": "如何配置 embedding 模型？",
        "relevant_keywords": ["EMBEDDING", "embedding", "nomic-embed-text", "Ollama"],
        "expected_answer_clues": ["EMBEDDING_BASE_URL", "embedding", "nomic-embed-text"],
    },
    {
        "question": "上传文档后如何让它可被检索？",
        "relevant_keywords": ["解析", "索引", "chunk", "parse", "index"],
        "expected_answer_clues": ["解析", "索引", "chunk"],
    },
    {
        "question": "问答系统使用了什么技术？",
        "relevant_keywords": ["RAG", "检索增强生成", "向量", "embedding"],
        "expected_answer_clues": ["RAG", "检索", "向量", "embedding"],
    },
    {
        "question": "API 认证是怎么实现的？",
        "relevant_keywords": ["API_TOKEN", "Bearer", "token", "Authorization"],
        "expected_answer_clues": ["API_TOKEN", "Bearer", "Authorization"],
    },
    {
        "question": "支持哪些大语言模型？",
        "relevant_keywords": ["DeepSeek", "Ollama", "OpenAI", "LLM", "qwen"],
        "expected_answer_clues": ["DeepSeek", "Ollama", "OpenAI"],
    },
    {
        "question": "向量数据库用的什么？",
        "relevant_keywords": ["Chroma", "chromadb", "ChromaDB"],
        "expected_answer_clues": ["Chroma", "ChromaDB"],
    },
    {
        "question": "文档切块是怎么做的？",
        "relevant_keywords": ["chunk", "段落", "切块", "1200", "重叠"],
        "expected_answer_clues": ["段落", "切块", "chunk"],
    },
    {
        "question": "什么是 RRF？",
        "relevant_keywords": ["RRF", "Reciprocal", "Rank", "Fusion", "混合", "融合"],
        "expected_answer_clues": ["RRF", "融合"],
    },
    {
        "question": "这个系统前后端用什么技术栈？",
        "relevant_keywords": ["FastAPI", "Vue", "TypeScript", "Ant Design", "Python"],
        "expected_answer_clues": ["FastAPI", "Vue", "TypeScript"],
    },
]
