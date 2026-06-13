# Enterprise RAG Knowledge Base MVP Design

## Goal

Build a multi-knowledge-base RAG question-answering management system that proves the full product loop before adding permissions.

The MVP must let a user create knowledge bases, upload documents, index them into a vector store, ask questions against a selected knowledge base, and receive grounded answers with citation markers and source snippets.

## Scope

In scope for the first version:

- Multiple knowledge bases.
- Document upload for PDF, Word, Markdown, and TXT files.
- Document parsing, text chunking, embedding, and vector indexing.
- Retrieval scoped to one selected knowledge base.
- AI answers that only use retrieved context.
- Inline citation markers such as `[1]` and `[2]`.
- Source display with document name, location metadata, and matched snippet.
- Provider abstraction for LLM and embedding services.

Out of scope for the first version:

- User accounts, teams, roles, and permissions.
- Audit logs and approval workflows.
- Web URL crawling and scheduled sync.
- Excel and structured table understanding.
- Advanced observability dashboards.
- Complex async task orchestration beyond basic index status tracking.

## Product Shape

The first version has three primary screens:

1. Knowledge base list
   - Create a knowledge base.
   - View existing knowledge bases.
   - Enter a knowledge base.
   - Delete a knowledge base if needed.

2. Knowledge base detail
   - Upload documents.
   - See document type, upload time, parse status, index status, and any error message.
   - Remove documents from the knowledge base.

3. Question-answer page
   - Ask a question against the selected knowledge base.
   - Show the answer with citation markers.
   - Show source cards mapped to citation numbers.
   - Include document name, page or section metadata where available, similarity score, and snippet text.

## Architecture

The system uses the existing intended stack:

- Frontend: Vue 3, TypeScript, Vite, Ant Design Vue.
- Backend: FastAPI.
- Relational database: SQLite.
- Vector database: Chroma.
- LLM and embedding: OpenAI-compatible provider abstraction, configured by environment variables.

The backend is organized around these modules:

- `KnowledgeBase`: owns knowledge base metadata.
- `Document`: owns uploaded file metadata, parse status, index status, and error information.
- `Parser`: converts PDF, Word, Markdown, and TXT files into normalized extracted text with source metadata.
- `Chunker`: splits extracted text into overlapping chunks.
- `EmbeddingProvider`: generates embeddings through a configured provider.
- `VectorStore`: stores and queries chunk embeddings in Chroma.
- `Retriever`: performs knowledge-base-scoped top-k retrieval.
- `LLMProvider`: calls the configured chat model.
- `AnswerService`: builds grounded prompts, calls the LLM, and returns answer plus citations.

## Data Model

SQLite stores durable application metadata:

- `knowledge_bases`
  - `id`
  - `name`
  - `description`
  - `created_at`
  - `updated_at`

- `documents`
  - `id`
  - `knowledge_base_id`
  - `filename`
  - `content_type`
  - `storage_path`
  - `parse_status`
  - `index_status`
  - `error_message`
  - `created_at`
  - `updated_at`

- `chunks`
  - `id`
  - `knowledge_base_id`
  - `document_id`
  - `chunk_index`
  - `text`
  - `source_label`
  - `page_number`
  - `section_title`
  - `vector_id`
  - `created_at`

Chroma stores chunk vectors. Each vector record includes metadata needed for filtering and citation:

- `knowledge_base_id`
- `document_id`
- `chunk_id`
- `filename`
- `page_number`
- `section_title`
- `chunk_index`

## Ingestion Flow

1. User uploads a document to a knowledge base.
2. Backend saves the file and creates a `documents` row.
3. Parser extracts text and source metadata.
4. Chunker creates overlapping chunks.
5. Embedding provider generates vectors for each chunk.
6. Chunks are stored in SQLite and vectors are stored in Chroma.
7. Document status becomes indexed, or failed with an error message.

The MVP can run indexing synchronously for simplicity, but the API and status fields should leave room for later background jobs.

## Question Flow

1. User asks a question in a selected knowledge base.
2. Backend embeds the question.
3. Retriever queries Chroma with a `knowledge_base_id` filter.
4. Backend loads matched chunk metadata from SQLite.
5. AnswerService builds a prompt that includes numbered context blocks.
6. LLM is instructed to answer only from the provided context and say it cannot confirm from the knowledge base when evidence is missing.
7. Backend returns:
   - answer text with citation markers
   - cited sources
   - retrieved source snippets

## Grounding Rules

The answer prompt must enforce:

- Use only the provided context.
- Do not invent facts.
- If the context does not answer the question, say that the answer cannot be confirmed from the current knowledge base.
- Cite relevant context blocks with `[n]` markers.
- Keep citations tied to actual retrieved chunks.

## Error Handling

Document ingestion errors should be visible in the knowledge base detail page:

- Unsupported file type.
- Parser failure.
- Empty extracted text.
- Embedding provider failure.
- Vector store write failure.

Question-answer errors should return user-readable messages:

- Knowledge base not found.
- Knowledge base has no indexed documents.
- Provider configuration missing.
- LLM or embedding request failed.

## Configuration

Provider settings are environment-driven:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`

The default implementation should target OpenAI-compatible APIs so DeepSeek, OpenAI, or local compatible gateways can be swapped without changing product code.

## Testing

Backend tests should cover:

- Knowledge base CRUD.
- Document upload validation.
- Parser behavior for TXT and Markdown with lightweight fixtures.
- Chunking overlap and metadata preservation.
- Retrieval filtering by `knowledge_base_id`.
- AnswerService prompt construction and fallback behavior when no context is available.

Frontend tests can be lighter for the MVP but should cover:

- Knowledge base list rendering.
- Document status rendering.
- Question-answer response rendering with citation source cards.

Manual acceptance test:

1. Create two knowledge bases.
2. Upload different documents into each.
3. Ask a question in each knowledge base.
4. Confirm answers only use documents from the selected knowledge base.
5. Confirm every answer either includes citations or states that the knowledge base cannot confirm the answer.

## Milestones

1. Backend foundation
   - SQLite schema.
   - Knowledge base APIs.
   - Document upload API.

2. Ingestion pipeline
   - File storage.
   - PDF, Word, Markdown, and TXT parsing.
   - Chunking.
   - Embedding.
   - Chroma indexing.

3. Retrieval and answering
   - Knowledge-base-scoped retrieval.
   - Grounded answer generation.
   - Citation response schema.

4. Frontend MVP
   - Knowledge base list.
   - Knowledge base detail and upload.
   - Question-answer page with source cards.

5. Verification
   - Automated backend tests.
   - Build checks.
   - Manual end-to-end acceptance test.

