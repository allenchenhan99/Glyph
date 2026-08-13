import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  activateResearchMap,
  enqueueResearchMap,
  getActiveResearchMap,
  getResearchMapDiff,
  getResearchMapJob,
  getResearchMapVersion,
  listDocuments,
  listResearchMapVersions,
  processDocument,
  reviewResearchNode
} from './api'

const evidence = {
  id: 'evidence-1',
  block_id: 'block-1',
  locator_type: 'text_span',
  quote_text: 'The strategy earns 0.8 percent per month.',
  quote_start: 0,
  quote_end: 43,
  source_quote_hash: 'a'.repeat(64),
  relation: 'supports',
  source_label: 'Primary result',
  page_number: 7,
  block_type: 'paragraph',
  translated_text: '此策略每月報酬為 0.8%。'
}

const node = {
  id: 'node-1',
  parent_node_id: null,
  node_key: 'primary_result.1',
  node_type: 'primary_result',
  title: '主要結果',
  claim_text: 'The strategy earns 0.8 percent per month.',
  effective_claim_text: 'The strategy earns 0.8 percent per month.',
  explanation: 'Long-short return.',
  provenance: 'author_explicit',
  evidence_quality: 'direct',
  display_order: 0,
  node_signature: 'b'.repeat(64),
  evidence: [evidence],
  issues: [],
  review: null
}

const researchMap = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'c'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: true,
  is_stale: false,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
  reviewed_core_nodes: 0,
  reviewable_core_nodes: 1,
  nodes: [node],
  issues: [
    {
      id: 'issue-1',
      node_id: 'node-1',
      code: 'not_reported',
      severity: 'warning',
      message: 'Transaction costs are not reported.'
    }
  ]
}

const job = {
  id: 'job-1',
  document_id: 'doc-1',
  map_version_id: null,
  status: 'queued',
  stage: 'queued',
  progress: 0,
  error_message: null,
  attempt_count: 0,
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z'
}

const review = {
  id: 'review-1',
  node_id: 'node-1',
  status: 'confirmed',
  corrected_claim_text: null,
  review_note: 'Checked.',
  revision_number: 1,
  supersedes_review_id: null,
  reviewed_at: '2026-08-12T12:01:00Z',
  based_on_map_version_id: 'map-1',
  based_on_node_signature: 'b'.repeat(64)
}

const version = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'c'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: true,
  is_stale: false,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z'
}

const diff = {
  version_id: 'map-1',
  against_version_id: 'map-0',
  nodes: [
    {
      node_key: 'primary_result.1',
      classification: 'claim_changed',
      version_node_id: 'node-1',
      against_node_id: 'node-0'
    }
  ]
}

describe('API errors', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('preserves a safe JSON detail from the backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'This document is already being processed.' }), {
          status: 409,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    const request = processDocument('doc-1')

    await expect(request).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: 'ApiError',
        status: 409,
        message: 'This document is already being processed.'
      })
    )
  })

  it('uses a status fallback for a non-JSON error response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('upstream failed', {
          status: 502,
          headers: { 'content-type': 'text/plain' }
        })
      )
    )

    await expect(processDocument('doc-1')).rejects.toEqual(
      new ApiError(502, 'Request failed with 502')
    )
  })
})

describe('Research Map API contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('accepts the schema-v1 research_question ontology value', async () => {
    const questionMap = {
      ...researchMap,
      nodes: [{ ...node, node_key: 'research_question.1', node_type: 'research_question' }]
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(questionMap), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    await expect(getActiveResearchMap('doc-1')).resolves.toEqual(questionMap)
  })

  it('validates every typed response and sends review preconditions', async () => {
    const responses = [job, job, researchMap, researchMap, [version], review, researchMap, diff]
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(responses.shift()), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(enqueueResearchMap('doc-1')).resolves.toEqual(job)
    await expect(getResearchMapJob('job-1')).resolves.toEqual(job)
    await expect(getActiveResearchMap('doc-1')).resolves.toEqual(researchMap)
    await expect(getResearchMapVersion('map-1')).resolves.toEqual(researchMap)
    await expect(listResearchMapVersions('doc-1')).resolves.toEqual([version])
    await expect(
      reviewResearchNode('node-1', {
        status: 'confirmed',
        based_on_node_signature: 'b'.repeat(64),
        corrected_claim_text: null,
        review_note: 'Checked.'
      })
    ).resolves.toEqual(review)
    await expect(activateResearchMap('map-1')).resolves.toEqual(researchMap)
    await expect(getResearchMapDiff('map-1', 'map-0')).resolves.toEqual(diff)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/documents/doc-1/research-map', {
      method: 'POST'
    })
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      '/api/research-nodes/node-1/review',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          status: 'confirmed',
          based_on_node_signature: 'b'.repeat(64),
          corrected_claim_text: null,
          review_note: 'Checked.'
        })
      })
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      '/api/research-maps/map-1/diff?against=map-0',
      undefined
    )
  })

  it('validates optional batched Research Map summaries in document rows', async () => {
    const document = {
      id: 'doc-1',
      title: 'sample.pdf',
      file_type: 'pdf',
      status: 'completed',
      research_map: {
        version_id: 'map-1',
        status: 'partial',
        is_current: true,
        is_stale: false,
        reviewed_core_nodes: 2,
        reviewable_core_nodes: 6,
        issue_count: 3
      }
    }
    const responses = [[document], [{ ...document, research_map: { ...document.research_map, issue_count: -1 } }]]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(responses.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(listDocuments()).resolves.toEqual([document])
    await expect(listDocuments()).rejects.toThrow('Unexpected API response shape')
  })

  it.each([
    ['unknown provenance', { ...node, provenance: 'model_guess' }],
    ['unknown evidence quality', { ...node, evidence_quality: 'probably_true' }],
    ['unknown node type', { ...node, node_type: 'chat_answer' }],
    [
      'malformed evidence',
      { ...node, evidence: [{ ...evidence, quote_start: -1 }] }
    ],
    ['unknown review status', { ...node, review: { ...review, status: 'approved' } }]
  ])('rejects %s at the HTTP boundary', async (_label, invalidNode) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ ...researchMap, nodes: [invalidNode] }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      )
    )

    await expect(getActiveResearchMap('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })

  it('rejects obsolete map shapes with missing structured issues', async () => {
    const { issues: _issues, ...obsoleteMap } = researchMap
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(obsoleteMap), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    await expect(getActiveResearchMap('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })

  it('rejects invalid job, review, version, and diff literal values', async () => {
    const invalidPayloads = [
      { ...job, status: 'sleeping' },
      { ...review, status: 'approved' },
      [{ ...version, status: 'draft' }],
      {
        ...diff,
        nodes: [{ ...diff.nodes[0], classification: 'semantically_similar' }]
      }
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(invalidPayloads.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(getResearchMapJob('job-1')).rejects.toThrow('Unexpected API response shape')
    await expect(
      reviewResearchNode('node-1', {
        status: 'confirmed',
        based_on_node_signature: 'b'.repeat(64),
        corrected_claim_text: null,
        review_note: null
      })
    ).rejects.toThrow('Unexpected API response shape')
    await expect(listResearchMapVersions('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getResearchMapDiff('map-1', 'map-0')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })
})
