import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, processDocument } from './api'

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
