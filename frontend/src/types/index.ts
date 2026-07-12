export type KnowledgeBase = {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export type DocumentItem = {
  id: string
  knowledge_base_id: string
  filename: string
  content_type: string
  storage_path: string
  parse_status: string
  index_status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export type AnswerSource = {
  citation: number
  vector_id: string
  text: string
  score: number | null
  metadata: Record<string, unknown>
}

export type QuestionResponse = {
  question: string
  answer: string
  sources: AnswerSource[]
}

export type QuestionAnswer = QuestionResponse & {
  id: string
  knowledge_base_id: string
  conversation_id: string | null
  top_k: number
  rating: number | null
  created_at: string
}

export type Conversation = {
  id: string
  knowledge_base_id: string
  title: string
  created_at: string
  updated_at: string
  messages?: QuestionAnswer[]
}

export type RetrievalResult = {
  vector_id: string
  text: string
  score: number | null
  metadata: Record<string, unknown>
}

export type RetrievalResponse = {
  query: string
  results: RetrievalResult[]
}

export type PaginatedResponse<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type ConversationMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: AnswerSource[]
  rating: number | null
  answerId: string
  created_at: string
}

export type BatchTaskResponse = {
  scheduled: number
  document_ids: string[]
}

export type AgenticQuestionResponse = {
  question: string
  answer: string
  sources: AnswerSource[]
  retrieval_rounds_used: number
  context_score: number | null
  web_search_used: boolean
  sub_queries_used: string[]
}

export type DocumentStatusTone = 'default' | 'processing' | 'success' | 'error'

export type DocumentStatusMeta = {
  label: string
  tone: DocumentStatusTone
  icon: object
  detail: string
}
