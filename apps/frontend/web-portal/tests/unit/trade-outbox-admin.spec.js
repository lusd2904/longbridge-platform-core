import { describe, expect, it } from 'vitest'
import {
  isTradeOutboxEndpointMissing,
  supportsTradeOutboxAdminDetails,
  resolveTradeOutboxAdminPayload
} from '@/utils/tradeOutboxAdmin.js'

describe('trade outbox admin helpers', () => {
  it('detects missing endpoints from 404 responses', () => {
    expect(isTradeOutboxEndpointMissing({ response: { status: 404 } })).toBe(true)
    expect(isTradeOutboxEndpointMissing({ status: 404 })).toBe(true)
    expect(isTradeOutboxEndpointMissing({ response: { status: 500 } })).toBe(false)
  })

  it('gracefully degrades to health-only mode when detail endpoints are unavailable', () => {
    const result = resolveTradeOutboxAdminPayload({
      healthResult: {
        status: 'fulfilled',
        value: {
          status: 'degraded',
          outbox: {
            pendingCount: 2
          }
        }
      },
      eventsResult: {
        status: 'rejected',
        reason: {
          response: { status: 404 },
          data: { error: 'not found' }
        }
      },
      sagasResult: {
        status: 'rejected',
        reason: {
          response: { status: 404 }
        }
      }
    })

    expect(result.mode).toBe('health-only')
    expect(result.summary.status).toBe('degraded')
    expect(result.events).toEqual([])
    expect(result.sagas).toEqual([])
    expect(result.message).toContain('事件列表')
    expect(result.message).toContain('Saga')
    expect(result.error).toBeNull()
  })

  it('surfaces unexpected failures so the page can still warn the user', () => {
    const error = {
      response: { status: 500 },
      message: 'internal error'
    }

    const result = resolveTradeOutboxAdminPayload({
      healthResult: {
        status: 'fulfilled',
        value: {
          status: 'healthy'
        }
      },
      eventsResult: {
        status: 'rejected',
        reason: error
      },
      sagasResult: {
        status: 'fulfilled',
        value: {
          data: [{ sagaId: 'saga-1' }]
        }
      }
    })

    expect(result.mode).toBe('partial')
    expect(result.error).toBe(error)
    expect(result.sagas).toEqual([{ sagaId: 'saga-1' }])
  })

  it('treats legacy health payloads without event-stream capabilities as health-only', () => {
    expect(supportsTradeOutboxAdminDetails({
      status: 'healthy',
      outbox: {
        pendingCount: 16
      }
    })).toBe(false)

    expect(supportsTradeOutboxAdminDetails({
      status: 'degraded',
      eventStream: {
        status: 'ok'
      }
    })).toBe(true)
  })
})
