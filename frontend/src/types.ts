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
  research_map?: ResearchMapSummary | null
}

export type ResearchMapSummary = {
  version_id: string
  status: ResearchMapStatus
  is_current: boolean
  is_stale: boolean
  reviewed_core_nodes: number
  reviewable_core_nodes: number
  issue_count: number
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

export type ResearchNodeType =
  | 'author_claim'
  | 'economic_mechanism'
  | 'hypothesis'
  | 'data_and_sample'
  | 'data_source'
  | 'sample_filter'
  | 'signal_definition'
  | 'variable_definition'
  | 'portfolio_construction'
  | 'rebalancing_rule'
  | 'empirical_method'
  | 'benchmark_model'
  | 'identification_strategy'
  | 'primary_result'
  | 'statistical_evidence'
  | 'economic_magnitude'
  | 'turnover'
  | 'transaction_cost'
  | 'robustness_test'
  | 'subsample_result'
  | 'alternative_explanation'
  | 'implementation_constraint'
  | 'limitations'
  | 'unanswered_question'

export type ResearchProvenance = 'author_explicit' | 'ai_synthesis' | 'human_created'
export type EvidenceQuality =
  | 'direct'
  | 'synthesized'
  | 'insufficient'
  | 'conflicted'
  | 'not_reported'
export type EvidenceRelation = 'supports' | 'qualifies' | 'contradicts' | 'context'
export type EvidenceLocatorType = 'text_span' | 'equation' | 'table' | 'figure' | 'caption'
export type ReviewStatus = 'confirmed' | 'questioned' | 'corrected'
export type ResearchMapStatus = 'building' | 'complete' | 'partial' | 'failed'
export type ResearchMapJobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type ResearchIssueSeverity = 'info' | 'warning' | 'error'
export type ResearchMapDiffClassification =
  | 'unchanged'
  | 'claim_changed'
  | 'evidence_changed'
  | 'added'
  | 'removed'

export type ResearchMapJob = {
  id: string
  document_id: string
  map_version_id: string | null
  status: ResearchMapJobStatus
  stage: string
  progress: number
  error_message: string | null
  attempt_count: number
  created_at: string
  updated_at: string
}

export type ResearchEvidence = {
  id: string
  block_id: string
  locator_type: EvidenceLocatorType
  quote_text: string
  quote_start: number
  quote_end: number
  source_quote_hash: string
  relation: EvidenceRelation
  source_label: string | null
  page_number: number
  block_type: string
  translated_text: string
}

export type ResearchMapIssue = {
  id: string
  node_id: string | null
  code: string
  severity: ResearchIssueSeverity
  message: string
}

export type ResearchNodeReview = {
  id: string
  status: ReviewStatus
  corrected_claim_text: string | null
  review_note: string | null
  revision_number: number
  supersedes_review_id: string | null
  reviewed_at: string
}

export type ResearchNodeReviewRecord = ResearchNodeReview & {
  node_id: string
  based_on_map_version_id: string
  based_on_node_signature: string
}

export type ResearchNodeReviewInput = {
  status: ReviewStatus
  based_on_node_signature: string
  corrected_claim_text: string | null
  review_note: string | null
}

export type ResearchNode = {
  id: string
  parent_node_id: string | null
  node_key: string
  node_type: ResearchNodeType
  title: string
  claim_text: string
  effective_claim_text: string
  explanation: string
  provenance: ResearchProvenance
  evidence_quality: EvidenceQuality
  display_order: number
  node_signature: string
  evidence: ResearchEvidence[]
  issues: ResearchMapIssue[]
  review: ResearchNodeReview | null
}

export type ResearchMap = {
  id: string
  document_id: string
  previous_version_id: string | null
  source_content_hash: string
  schema_version: string
  provider: string
  model_name: string | null
  status: ResearchMapStatus
  is_active: boolean
  is_current: boolean
  is_stale: boolean
  created_at: string
  completed_at: string | null
  reviewed_core_nodes: number
  reviewable_core_nodes: number
  nodes: ResearchNode[]
  issues: ResearchMapIssue[]
}

export type ResearchMapVersion = Omit<
  ResearchMap,
  'reviewed_core_nodes' | 'reviewable_core_nodes' | 'nodes' | 'issues'
>

export type ResearchNodeDiff = {
  node_key: string
  classification: ResearchMapDiffClassification
  version_node_id: string | null
  against_node_id: string | null
}

export type ResearchMapDiff = {
  version_id: string
  against_version_id: string
  nodes: ResearchNodeDiff[]
}
