import { describe, expect, it } from 'vitest'
import { sanitizeNarrativeText } from '@/utils/contentSanitizer.js'
import {
  buildTradingReadModelSummary,
  formatReadModelSourceLabel
} from '@/utils/readModelSource.js'

describe('display content cleanup', () => {
  it('removes generated placeholder summaries before rendering', () => {
    expect(sanitizeNarrativeText('系统已生成无模型降级摘要。', '系统会综合市场数据库生成推荐。')).toBe('')
    expect(sanitizeNarrativeText('系统已生成推荐摘要。科技股偏强。')).toBe('科技股偏强')
  })

  it('formats read model source names as business labels', () => {
    expect(formatReadModelSourceLabel('account_asset_snapshots.payload.recentOrders')).toBe('订单快照')
    expect(formatReadModelSourceLabel('quote_snapshots')).toBe('报价快照')
  })

  it('does not expose technical source names in read model summaries', () => {
    const summary = buildTradingReadModelSummary({
      hasAccount: true,
      tradeMeta: {
        snapshotAt: '2026-05-13T10:00:00Z',
        sources: {
          account: 'account_asset_snapshots',
          positions: 'position_snapshots'
        }
      },
      orderMeta: {
        snapshotAt: '2026-05-13T10:00:00Z',
        sources: { orders: 'trade_order_projections' },
        realtimeOverlay: ['order-stream']
      },
      hasLiveOverlay: true,
      hasRecentOrderStreamCoverage: true,
      recentOrderCount: 2
    })

    const rendered = [summary.detail, summary.statusText, ...summary.tags.map((tag) => tag.text)].join(' ')
    expect(rendered).toContain('账户快照')
    expect(rendered).toContain('订单快照')
    expect(rendered).not.toMatch(/account_asset_snapshots|position_snapshots|trade_order_projections|order-stream|WebSocket/)
  })
})
