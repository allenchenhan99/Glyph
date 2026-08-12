export type DocumentStatus =
  | 'discovered'
  | 'uploaded'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'stale'
  | 'missing'

export type DocumentRecord = {
  id: string
  title: string
  file_type: string
  status: DocumentStatus
}

export type ProcessingJob = {
  id: string
  document_id: string
  status: string
  stage: string
  progress: number
  error_message: string | null
}

export type ReaderBlock = {
  id: string
  order_index: number
  page_number: number
  block_type: string
  source_text: string
  translated_text: string
  formula_latex: string | null
  page_image_url: string
  section_path: string | null
  confidence: number
}

export type ReaderSection = {
  id: string
  title: string
  path: string
  order_index: number
  summary: string
  progress: number
}

export type ReaderPayload = {
  document: DocumentRecord
  blocks: ReaderBlock[]
  sections: ReaderSection[]
  summary: string
}
