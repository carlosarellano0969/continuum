import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('Continuum API client', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('uses the contract health endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok', version: 'v1', services: {} }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.health()).resolves.toMatchObject({ status: 'ok', version: 'v1' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }))
  })

  it('returns the API detail for failed contract responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Proposal is already decided' }), { status: 409 })))

    await expect(api.decideProposal('proposal-1', 'approve')).rejects.toMatchObject({ message: 'Proposal is already decided', status: 409 })
  })

  it('turns a transport failure into an actionable message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network error')))

    await expect(api.memories()).rejects.toThrow('Cannot reach the Continuum API')
  })
})
