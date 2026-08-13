import type { ResearchEvidence, ResearchMap, ResearchNode, ResearchNodeType } from './types'

const nodeTypes: ResearchNodeType[] = [
  'author_claim',
  'data_and_sample',
  'signal_definition',
  'empirical_method',
  'primary_result',
  'limitations'
]

const titles = [
  'Research question',
  'Data and sample',
  'Signal definition',
  'Empirical method',
  'Primary result',
  'Limitations'
]

function evidence(index: number): ResearchEvidence {
  return {
    id: `evidence-${index}`,
    block_id: `block-${index}`,
    locator_type: index === 4 ? 'table' : 'text_span',
    quote_text: `Verbatim source evidence ${index}`,
    quote_start: 0,
    quote_end: 27,
    source_quote_hash: `${index}`.repeat(64).slice(0, 64),
    relation: index === 5 ? 'qualifies' : 'supports',
    source_label: index === 4 ? 'Table 3' : null,
    page_number: index + 1,
    block_type: index === 4 ? 'table' : 'paragraph',
    translated_text: `繁體中文證據翻譯 ${index}`
  }
}

function node(index: number): ResearchNode {
  return {
    id: `node-${index}`,
    parent_node_id: null,
    node_key: `${nodeTypes[index]}.1`,
    node_type: nodeTypes[index],
    title: titles[index],
    claim_text: `AI draft claim ${index}`,
    effective_claim_text: `AI draft claim ${index}`,
    explanation: `Explanation ${index}`,
    provenance: index === 2 ? 'ai_synthesis' : 'author_explicit',
    evidence_quality: index === 5 ? 'insufficient' : index === 2 ? 'synthesized' : 'direct',
    display_order: index,
    node_signature: `${index + 1}`.repeat(64).slice(0, 64),
    evidence: [evidence(index)],
    issues: [],
    review: null
  }
}

export const researchMapFixture: ResearchMap = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'a'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: false,
  is_stale: true,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
  reviewed_core_nodes: 0,
  reviewable_core_nodes: 6,
  nodes: nodeTypes.map((_, index) => node(index)),
  issues: [
    {
      id: 'issue-1',
      node_id: null,
      code: 'missing_core_node',
      severity: 'error',
      message: 'The Research Map is missing implementation cost evidence.'
    }
  ]
}
