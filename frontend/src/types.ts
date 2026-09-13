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
  implementation_contract?: ImplementationContractSummary | null
}

export type WorkspaceCapability = { provider: string; configured: boolean; message: string }
export type WorkspaceStatus = {
  status: 'ready' | 'blocked'
  development_features: string[]
  translation: WorkspaceCapability
  research: WorkspaceCapability
  ocr: WorkspaceCapability
  recovery: string | null
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

export type ProcessingPreflight = {
  ready: boolean
  source_type: string
  provider: string
  page_count: number | null
  issues: { code: string; severity: 'error' | 'warning'; message: string }[]
}

export type ProcessingJob = {
  id: string
  document_id: string
  status: string
  stage: string
  progress: number
  error_message: string | null
  completed_blocks?: number | null
  total_blocks?: number | null
  cancel_requested?: boolean
  provider?: string | null
  model?: string | null
}

export type ReaderBlock = {
  id: string
  order_index: number
  page_number: number
  block_type: string
  source_text: string
  translated_text: string
  formula_latex: string | null
  page_image_url: string | null
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

export type SummaryEvidence = {
  block_id: string
  quote_text: string
  quote_start: number
  quote_end: number
  page_number: number
}

export type SummaryClaim = {
  id: string
  section_path: string | null
  text: string
  evidence: SummaryEvidence[]
}

export type SummaryVersion = {
  id: string
  source_content_hash: string
  reader_fingerprint: string
  provider: string
  model: string | null
  created_at: string
  claims: SummaryClaim[]
}

export type DocumentSummaries = {
  status: 'not_generated' | 'generating' | 'available' | 'stale' | 'failed'
  provider: string
  model: string | null
  version: SummaryVersion | null
  job: { id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'; error_message: string | null } | null
}

export type ResearchNodeType =
  | 'research_question'
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

export type ContractSection =
  | 'thesis'
  | 'data_requirements'
  | 'universe_and_sample'
  | 'signal_and_timing'
  | 'portfolio_construction'
  | 'evaluation'
  | 'frictions_and_risks'
  | 'open_decisions'

export type ContractItemType =
  | 'required_dataset'
  | 'required_field'
  | 'data_frequency'
  | 'availability_lag'
  | 'sample_period'
  | 'universe_filter'
  | 'sample_filter'
  | 'signal_formula'
  | 'signal_direction'
  | 'formation_date'
  | 'lookback_window'
  | 'weighting_rule'
  | 'rebalance_frequency'
  | 'holding_period'
  | 'long_short_definition'
  | 'benchmark_model'
  | 'evaluation_metric'
  | 'statistical_test'
  | 'transaction_cost'
  | 'turnover_assumption'
  | 'survivorship_risk'
  | 'lookahead_risk'
  | 'implementation_constraint'

export type ContractOrigin =
  | 'author_explicit'
  | 'derived'
  | 'human_decision'
  | 'missing'
export type ContractGenerationStatus = 'building' | 'complete' | 'partial' | 'failed'
export type ContractReadiness = 'blocked' | 'review_needed' | 'implementation_ready'
export type ContractResolutionStatus =
  | 'confirmed'
  | 'corrected'
  | 'decided'
  | 'questioned'
  | 'not_applicable'
export type ContractIssueSeverity = 'info' | 'warning' | 'error'
export type ContractDiffClassification =
  | 'unchanged'
  | 'type_changed'
  | 'value_changed'
  | 'origin_changed'
  | 'evidence_changed'
  | 'added'
  | 'removed'
export type ContractRuleOperator = 'include' | 'exclude' | 'rank' | 'threshold'
export type ContractPeriodUnit =
  | 'business_day'
  | 'day'
  | 'week'
  | 'month'
  | 'quarter'
  | 'year'
export type ImplementationContractJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
export type ContractExportFormat = 'json' | 'markdown'
export type ContractExportLanguage = 'en' | 'zh-TW' | 'bilingual'

export type ContractScalarValue = {
  kind: 'scalar'
  value: string | number | boolean
  unit?: string | null
}

export type ContractFormulaValue = {
  kind: 'formula'
  expression: string
  variables: string[]
}

export type ContractRuleValue = {
  kind: 'rule'
  operator: ContractRuleOperator
  field: string
  value: ContractScalarValue
}

export type ContractListValue = {
  kind: 'list'
  values: ContractScalarValue[]
}

export type ContractRangeValue = {
  kind: 'range'
  minimum: ContractScalarValue
  maximum: ContractScalarValue
  include_minimum: boolean
  include_maximum: boolean
}

export type ContractPeriodValue = {
  kind: 'period'
  amount: number
  unit: ContractPeriodUnit
  anchor?: string | null
}

export type ContractValue =
  | ContractScalarValue
  | ContractFormulaValue
  | ContractRuleValue
  | ContractListValue
  | ContractRangeValue
  | ContractPeriodValue

export type ContractEvidence = {
  id: string
  block_id: string
  research_node_id: string | null
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

export type ContractIssue = {
  id: string
  item_id: string | null
  code: string
  severity: ContractIssueSeverity
  message: string
}

export type ContractResolution = {
  id: string
  item_id: string
  revision_number: number
  supersedes_resolution_id: string | null
  status: ContractResolutionStatus
  resolved_value: ContractValue | null
  reason: string | null
  based_on_contract_version_id: string
  based_on_item_signature: string
  request_id: string
  resolved_at: string
}

export type ContractResolutionInput = {
  request_id: string
  status: ContractResolutionStatus
  based_on_item_signature: string
  resolved_value: ContractValue | null
  reason: string | null
}

export type ImplementationContractItem = {
  id: string
  item_key: string
  section: ContractSection
  item_type: ContractItemType
  draft_value: ContractValue | null
  effective_value: ContractValue | null
  origin: ContractOrigin
  effective_origin: ContractOrigin
  rationale: string | null
  is_blocking: boolean
  is_optional: boolean
  display_order: number
  item_signature: string
  evidence: ContractEvidence[]
  issues: ContractIssue[]
  resolution: ContractResolution | null
  resolution_history: ContractResolution[]
}

export type ImplementationContract = {
  id: string
  document_id: string
  research_map_version_id: string
  previous_version_id: string | null
  source_content_hash: string
  research_map_signature: string
  schema_version: string
  provider: string
  model_name: string | null
  status: ContractGenerationStatus
  readiness: ContractReadiness
  is_active: boolean
  is_resolvable: boolean
  is_current: boolean
  is_stale: boolean
  created_at: string
  completed_at: string | null
  items: ImplementationContractItem[]
  issues: ContractIssue[]
}

export type ImplementationContractVersion = Omit<
  ImplementationContract,
  'items' | 'issues' | 'is_resolvable'
>

export type ImplementationContractJob = {
  id: string
  document_id: string
  requested_research_map_version_id: string | null
  contract_version_id: string | null
  status: ImplementationContractJobStatus
  stage: string
  progress: number
  error_message: string | null
  attempt_count: number
  created_at: string
  updated_at: string
}

export type ImplementationContractSummary = {
  version_id: string
  generation_status: ContractGenerationStatus
  readiness: ContractReadiness
  is_current: boolean
  is_stale: boolean
  blocker_count: number
  reviewed_count: number
  total_reviewable_count: number
}

export type ImplementationContractItemDiff = {
  item_key: string
  classification: ContractDiffClassification
  version_item_id: string | null
  against_item_id: string | null
}

export type ImplementationContractDiff = {
  version_id: string
  against_version_id: string
  items: ImplementationContractItemDiff[]
}

export type ImplementationContractExport = {
  blob: Blob
  filename: string
  content_type: 'application/json' | 'text/markdown'
}
