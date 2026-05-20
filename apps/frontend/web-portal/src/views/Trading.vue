<template>
  <div class="trading-page">
    <PageHero
      title="交易台"
      :chips="tradeHeroChips"
      :compact="isPhoneLayout"
    >
      <template #actions>
        <div class="header-actions" :class="{ 'mobile-command-controls': isPhoneLayout }">
          <el-select v-model="selectedAccount" placeholder="选择账户" :class="{ 'mobile-account-select': isPhoneLayout }" style="width: 220px">
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
          <el-button class="trade-surface-button" :icon="Refresh" @click="refreshTradingData">{{ isPhoneLayout ? '刷新' : '刷新数据' }}</el-button>
        </div>
      </template>
    </PageHero>

    <ReadModelSourceStrip
      class="trade-source-strip"
      label=""
      :status-text="tradingReadModelStatus"
      :status-type="tradingReadModelStatusType"
      :updated-at="tradingReadModelUpdatedAt"
      :updated-prefix="tradingReadModelUpdatedPrefix"
      :tags="tradingReadModelTags"
      :compact="isPhoneLayout"
    />

    <section class="market-pulse-summary">
      <el-card class="glass-card market-pulse-hero">
        <div v-if="selectedMarketInsight" class="pulse-summary-shell">
          <div class="pulse-summary-copy">
            <span class="empty-kicker">市场脉冲</span>
            <div class="pulse-summary-headline">
              <div>
                <strong>{{ selectedMarketInsight.headline || selectedMarketInsight.marketLabel }}</strong>
                <p>{{ selectedMarketInsight.summary || '长桥市场脉冲正在同步。' }}</p>
              </div>
              <div class="pulse-summary-score">
                <span>市场分数</span>
                <strong>{{ formatRatio(selectedMarketInsight.marketScore, false) }}</strong>
              </div>
            </div>
            <div class="pulse-summary-metrics">
              <article class="pulse-mini-card">
                <span>当前市场</span>
                <strong>{{ selectedMarketInsight.marketLabel || detectMarketLabel(orderForm.symbol) }}</strong>
              </article>
              <article class="pulse-mini-card">
                <span>状态</span>
                <strong>{{ selectedMarketInsight.statusText || '待同步' }}</strong>
              </article>
              <article class="pulse-mini-card">
                <span>量化信号</span>
                <strong>{{ latestQuantSignal ? `${latestQuantSignal.side} ${latestQuantSignal.symbol}` : '暂无新信号' }}</strong>
              </article>
            </div>
          </div>
          <div class="pulse-benchmarks pulse-benchmarks--compact">
            <div
              v-for="benchmark in selectedMarketInsight.benchmarks || []"
              :key="benchmark.symbol"
              class="pulse-benchmark"
            >
              <div class="benchmark-head">
                <strong>{{ benchmark.name }}</strong>
                <span>{{ formatMarketPrice(benchmark.price) }}</span>
              </div>
              <div class="benchmark-meta">{{ benchmark.symbol }}</div>
              <div class="benchmark-change" :class="benchmark.changePercent >= 0 ? 'up' : 'down'">
                {{ formatPercentValue(benchmark.changePercent) }}
              </div>
            </div>
          </div>
        </div>
        <div v-else class="board-empty-state">
          <strong>等待市场脉冲快照</strong>
          <span>交易台页眉下方优先展示脉冲摘要，快照到达后会自动补齐。</span>
        </div>
      </el-card>
    </section>

    <section v-if="isPhoneLayout" class="mobile-command-jumps">
      <button type="button" class="mobile-command-jump" @click="scrollToTradeSection('trade-order')">快速下单</button>
      <button type="button" class="mobile-command-jump" @click="scrollToTradeSection('trade-context')">账户上下文</button>
      <button type="button" class="mobile-command-jump" @click="scrollToTradeSection('trade-quote')">行情盘口</button>
      <button type="button" class="mobile-command-jump" @click="scrollToTradeSection('trade-positions')">持仓卡片</button>
      <button type="button" class="mobile-command-jump" @click="scrollToTradeSection('trade-orders')">近期订单</button>
    </section>

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeTradeSection"
      class="mobile-trade-rail"
      label="交易台分段"
      :items="tradeMobileSections"
    />

    <div class="trading-container">
      <div v-if="!isPhoneLayout || activeTradeSection === 'order'" id="trade-order" class="order-panel">
        <el-card class="glass-card">
          <template #header>
            <SectionCardHeader
              title="快速下单"
              :badge="orderForm.action === 'buy' ? '买入执行' : '卖出执行'"
            />
          </template>

          <el-form :model="orderForm" label-position="top">
            <el-form-item label="股票代码">
              <el-input
                v-model="orderForm.symbol"
                placeholder="输入股票代码，例如 AAPL.US / 700.HK / 510300.SH"
                @keyup.enter="searchSymbol"
              >
                <template #append>
                  <el-button class="trade-surface-button trade-search-button" :loading="quoteLoading" @click="searchSymbol">搜索</el-button>
                </template>
              </el-input>
            </el-form-item>

            <div v-if="quickSymbols.length" class="symbol-shortcuts">
              <button
                v-for="symbol in quickSymbols"
                :key="symbol"
                type="button"
                class="shortcut-chip"
                @click="fillSymbol(symbol)"
              >
                {{ symbol }}
              </button>
            </div>

            <el-form-item label="操作">
              <el-radio-group v-model="orderForm.action" size="large" class="trade-toggle-group">
                <el-radio-button value="buy">买入</el-radio-button>
                <el-radio-button value="sell">卖出</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="价格类型">
              <el-radio-group v-model="orderForm.orderType" class="trade-toggle-group">
                <el-radio-button value="market">市价</el-radio-button>
                <el-radio-button value="limit">限价</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="orderForm.orderType === 'limit'" label="价格">
              <el-input-number
                v-model="orderForm.price"
                :precision="2"
                :step="0.01"
                :min="0"
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item label="数量">
              <el-input-number
                v-model="orderForm.quantity"
                :min="1"
                :step="1"
                style="width: 100%"
              />
            </el-form-item>

            <div class="quantity-presets">
              <el-button class="trade-surface-button" size="small" @click="applyQuantityPreset(10)">10</el-button>
              <el-button class="trade-surface-button" size="small" @click="applyQuantityPreset(50)">50</el-button>
              <el-button class="trade-surface-button" size="small" @click="applyQuantityPreset(100)">100</el-button>
              <el-button class="trade-surface-button" size="small" @click="applyQuantityPreset(200)">200</el-button>
              <el-button
                v-if="orderForm.action === 'sell'"
                class="trade-surface-button"
                size="small"
                type="warning"
                plain
                @click="fillAvailablePosition"
              >
                全部卖出
              </el-button>
            </div>

            <el-form-item>
              <div class="order-summary">
                <div class="summary-item">
                  <span>预估金额</span>
                  <strong class="amount">{{ formatCurrency(estimatedAmount) }}</strong>
                </div>
                <div class="summary-item">
                  <span>{{ orderForm.action === 'buy' ? '占可用资金' : '占持仓比例' }}</span>
                  <strong>{{ formatRatio(estimatedExposure) }}</strong>
                </div>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button
                class="trade-submit-button"
                size="large"
                style="width: 100%"
                :type="orderForm.action === 'buy' ? 'success' : 'danger'"
                :disabled="!canTradeLive || submittingOrder"
                :loading="submittingOrder"
                @click="submitOrder"
              >
                {{ orderButtonText }}
              </el-button>
            </el-form-item>
          </el-form>

          <section class="trade-safety-panel" :class="`is-${tradeSafetyTone}`">
            <div class="trade-safety-head">
              <span class="feedback-kicker">交易安全提示</span>
              <el-tag size="small" :type="tradeSafetyTagType">{{ tradeSafetyTagText }}</el-tag>
            </div>
            <strong>{{ tradeSafetyHeadline }}</strong>
            <p>{{ tradeSafetyMessage }}</p>
          </section>

          <div class="order-intelligence-grid">
            <article class="order-intelligence-card emphasis">
              <span>当前委托</span>
              <strong>{{ orderIntentTitle }}</strong>
            </article>
            <article class="order-intelligence-card">
              <span>参考价格</span>
              <strong>{{ orderReferenceSummary }}</strong>
            </article>
            <article v-if="selectedPosition" class="order-intelligence-card">
              <span>关联持仓</span>
              <strong>{{ selectedPosition.symbol }} · {{ selectedPosition.quantity }} 股</strong>
            </article>
            <article v-else class="order-intelligence-card">
              <span>仓位提示</span>
              <strong>{{ orderForm.action === 'buy' ? '将新增头寸' : '尚未匹配持仓' }}</strong>
            </article>
          </div>

          <section v-if="lastOrderFeedback" class="order-feedback-panel" :class="lastOrderFeedback.kind">
            <div class="order-feedback-head">
              <div>
                <span class="feedback-kicker">{{ lastOrderFeedback.kind === 'success' ? '执行回执' : '执行拦截' }}</span>
                <strong>{{ lastOrderFeedback.title }}</strong>
              </div>
              <el-tag size="small" :type="lastOrderFeedback.kind === 'success' ? 'success' : 'danger'">
                {{ lastOrderFeedback.kind === 'success' ? '已处理' : '需关注' }}
              </el-tag>
            </div>
            <p>{{ lastOrderFeedback.message }}</p>
            <div class="feedback-meta-grid">
              <div class="feedback-meta-item">
                <span>参考价</span>
                <strong>{{ formatReferencePrice(lastOrderFeedback.meta?.referencePrice) }}</strong>
              </div>
              <div class="feedback-meta-item">
                <span>来源</span>
                <strong>{{ formatReferencePriceSource(lastOrderFeedback.meta?.referencePriceSource) }}</strong>
              </div>
              <div class="feedback-meta-item">
                <span>快照时间</span>
                <strong>{{ formatFeedbackTime(lastOrderFeedback.meta?.referencePriceSnapshotAt) }}</strong>
              </div>
              <div class="feedback-meta-item">
                <span>执行状态</span>
                <strong>{{ lastOrderFeedback.meta?.degraded ? '备用报价' : '实时路径' }}</strong>
              </div>
            </div>
          </section>
        </el-card>

        <el-card
          id="trade-context"
          v-if="!isPhoneLayout || activeTradeSection === 'context'"
          class="glass-card"
          style="margin-top: 16px"
        >
          <template #header>
            <SectionCardHeader
              title="执行上下文"
              :badge="latestQuantSignal ? '有量化信号' : '暂无新信号'"
              :badge-type="latestQuantSignal ? 'warning' : 'info'"
            />
          </template>
          <div class="execution-context">
            <div class="context-item">
              <span class="label">当前市场</span>
              <strong>{{ selectedMarketInsight?.marketLabel || detectMarketLabel(orderForm.symbol) }}</strong>
            </div>
            <div class="context-item">
              <span class="label">市场状态</span>
              <strong>{{ selectedMarketInsight?.statusText || '待加载' }}</strong>
            </div>
            <div class="context-item full">
              <span class="label">市场摘要</span>
              <strong>{{ selectedMarketInsight?.summary || '待匹配' }}</strong>
            </div>
            <div class="context-item full">
              <span class="label">最新量化建议</span>
              <strong v-if="latestQuantSignal">
                {{ latestQuantSignal.side }} {{ latestQuantSignal.symbol }}
                · 置信度 {{ latestQuantSignal.confidence || 0 }}%
                · {{ latestQuantSignal.reason || '量化模型综合判断' }}
              </strong>
              <strong v-else>暂无信号</strong>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="!isPhoneLayout || activeTradeSection === 'context'"
          class="glass-card"
          style="margin-top: 16px"
        >
          <template #header>
            <SectionCardHeader title="账户信息" />
          </template>
          <div class="account-info">
            <div class="info-item">
              <span class="label">可用资金</span>
              <span class="value">{{ formatCurrency(accountInfo.cash) }}</span>
            </div>
            <div class="info-item">
              <span class="label">持仓市值</span>
              <span class="value">{{ formatCurrency(accountInfo.marketValue) }}</span>
            </div>
            <div class="info-item">
              <span class="label">总资产</span>
              <span class="value">{{ formatCurrency(accountInfo.totalAssets) }}</span>
            </div>
            <div class="info-item">
              <span class="label">今日订单数</span>
              <span class="value">{{ recentOrders.length }}</span>
            </div>
            <div class="info-item">
              <span class="label">量化状态</span>
              <span class="value">{{ quantStatus.enabled ? '已启用' : '未启用' }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <div class="market-panel">
        <el-card
          v-if="(!isPhoneLayout || activeTradeSection === 'quote') && !orderForm.symbol"
          id="trade-quote"
          class="glass-card market-empty-card"
        >
          <div class="market-empty-copy">
            <span class="empty-kicker">行情</span>
            <h3>输入标的查看盘口</h3>
            <div class="empty-chip-row" v-if="quickSymbols.length">
              <button
                v-for="symbol in quickSymbols"
                :key="`empty-${symbol}`"
                type="button"
                class="shortcut-chip"
                @click="fillSymbol(symbol)"
              >
                {{ symbol }}
              </button>
            </div>
            <div class="empty-context-grid">
              <div class="empty-context-item">
                <span>当前市场</span>
                <strong>{{ selectedMarketInsight?.marketLabel || detectMarketLabel(orderForm.symbol) }}</strong>
              </div>
              <div class="empty-context-item">
                <span>量化状态</span>
                <strong>{{ quantStatus.enabled ? '已启用' : '未启用' }}</strong>
              </div>
              <div class="empty-context-item wide">
                <span>市场摘要</span>
                <strong>{{ selectedMarketInsight?.summary || '待匹配' }}</strong>
              </div>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="(!isPhoneLayout || activeTradeSection === 'quote') && orderForm.symbol"
          id="trade-quote"
          v-loading="quoteLoading"
          class="glass-card market-quote-card"
        >
          <template #header>
            <SectionCardHeader
              :title="`${currentQuoteDisplayName} (${displaySymbol})`"
            >
              <template #actions>
                <div class="quote-header-tags">
                  <el-tag size="small" :type="currentQuoteReady ? getSessionTagType(currentQuote?.session) : 'info'">
                    {{ currentQuoteReady ? getSessionLabel(currentQuote?.session) : '等待行情' }}
                  </el-tag>
                  <el-tag size="small" :type="hasLivePushQuote ? 'success' : 'warning'">
                    {{ currentQuoteSourceLabel }}
                  </el-tag>
                  <el-tag v-if="quoteDataStatusTag" size="small" type="info">
                    {{ quoteDataStatusTag }}
                  </el-tag>
                  <el-tag v-if="quoteFetchStatusTag" size="small" :type="quoteFetchStatusTagType">
                    {{ quoteFetchStatusTag }}
                  </el-tag>
                  <el-tag v-if="currentQuoteReady" :type="Number(currentQuote?.change ?? 0) >= 0 ? 'success' : 'danger'">
                    {{ formatPercentValue(currentQuote?.changePercent) }}
                  </el-tag>
                </div>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="currentQuoteReady" class="quote-info">
            <div class="price-main">
              <span class="current-price" :class="Number(currentQuote?.change ?? 0) >= 0 ? 'up' : 'down'">
                {{ formatMarketPrice(currentQuote?.price) }}
              </span>
              <span class="sub-change" :class="Number(currentQuote?.change ?? 0) >= 0 ? 'up' : 'down'">
                {{ formatSignedCurrency(currentQuote?.change) }}
              </span>
            </div>
            <div v-if="isPhoneLayout" class="mobile-quote-strip">
              <article class="mobile-quote-pill">
                <span>状态</span>
                <strong>{{ currentQuoteSourceLabel }}</strong>
              </article>
              <article class="mobile-quote-pill">
                <span>委托参考</span>
                <strong>{{ orderReferenceSummary }}</strong>
              </article>
              <article class="mobile-quote-pill">
                <span>预估金额</span>
                <strong>{{ formatCurrency(estimatedAmount) }}</strong>
              </article>
            </div>
            <div class="quote-details">
              <div class="detail-item">
                <span class="label">昨收</span>
                <span class="value">{{ formatQuoteDetailPrice(currentQuote?.prevClose) }}</span>
              </div>
              <div class="detail-item">
                <span class="label">今开</span>
                <span class="value">{{ formatQuoteDetailPrice(currentQuote?.open) }}</span>
              </div>
              <div class="detail-item">
                <span class="label">最高</span>
                <span class="value">{{ formatQuoteDetailPrice(currentQuote?.high) }}</span>
              </div>
              <div class="detail-item">
                <span class="label">最低</span>
                <span class="value">{{ formatQuoteDetailPrice(currentQuote?.low) }}</span>
              </div>
              <div class="detail-item">
                <span class="label">成交量</span>
                <span class="value">{{ formatVolume(currentQuote?.volume) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="board-empty-state board-empty-state--quote">
            <strong>{{ displaySymbol }} 等待行情</strong>
            <span>{{ marketBoardWaitingText }}</span>
          </div>
        </el-card>

        <el-card
          v-if="(!isPhoneLayout || activeTradeSection === 'quote') && orderForm.symbol"
          v-loading="quoteLoading"
          class="glass-card market-board-card"
          style="margin-top: 16px"
        >
          <template #header>
            <SectionCardHeader
              title="实时盘口与逐笔"
              :badge="marketBoardBadge"
              :badge-type="hasLivePushDepth || hasLivePushTrades ? 'success' : 'warning'"
            />
          </template>
          <div class="board-status-strip">
            <article class="board-status-card">
              <span>盘口来源</span>
              <strong>{{ depthSourceLabel }}</strong>
            </article>
            <article class="board-status-card">
              <span>成交来源</span>
              <strong>{{ tradesSourceLabel }}</strong>
            </article>
            <article class="board-status-card">
              <span>买一 / 卖一</span>
              <strong>{{ bestBidAskSummary }}</strong>
            </article>
            <article class="board-status-card">
              <span>最近成交</span>
              <strong>{{ `${recentTape.length} 条` }}</strong>
            </article>
          </div>
          <div class="quote-stream-grid quote-stream-grid--compact">
            <div class="depth-panel compact-board-panel">
              <strong>盘口</strong>
              <div v-if="depthBids.length || depthAsks.length" class="depth-grid">
                <div class="depth-side">
                  <span class="depth-title">卖盘</span>
                  <div v-for="(item, index) in depthAsks.slice().reverse()" :key="`ask-${index}`" class="depth-row">
                    <span>{{ depthAsks.length - index }}</span>
                    <strong class="down">{{ formatMarketPrice(item.price) }}</strong>
                    <span>{{ formatVolume(item.volume) }}</span>
                  </div>
                </div>
                <div class="depth-side">
                  <span class="depth-title">买盘</span>
                  <div v-for="(item, index) in depthBids" :key="`bid-${index}`" class="depth-row">
                    <span>{{ index + 1 }}</span>
                    <strong class="up">{{ formatMarketPrice(item.price) }}</strong>
                    <span>{{ formatVolume(item.volume) }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="board-empty-state">
                <strong>五档盘口等待中</strong>
                <span>{{ marketBoardWaitingText }}</span>
              </div>
            </div>
            <div class="trade-panel compact-board-panel">
              <strong>最近成交</strong>
              <div v-if="recentTape.length" class="trade-tape">
                <div v-for="trade in recentTape" :key="trade.id" class="trade-tape-row">
                  <div>
                    <strong :class="trade.sideClass">{{ formatMarketPrice(trade.price) }}</strong>
                    <span>{{ trade.sideLabel }}</span>
                  </div>
                  <div>
                    <strong>{{ formatVolume(trade.volume) }}</strong>
                    <span>{{ formatDate(trade.timestamp) }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="board-empty-state">
                <strong>逐笔成交等待中</strong>
                <span>{{ marketBoardWaitingText }}</span>
              </div>
            </div>
          </div>
        </el-card>

        <el-card v-if="(!isPhoneLayout || activeTradeSection === 'quote') && orderForm.symbol" class="glass-card" style="margin-top: 16px">
          <template #header>
            <SectionCardHeader title="公告 / 资讯 / 讨论">
              <template #actions>
                <div class="card-actions">
                  <el-tag size="small" type="info">{{ orderForm.symbol }}</el-tag>
                  <el-button type="primary" link :loading="contentRefreshing" @click="refreshSymbolContent">
                    回源刷新
                  </el-button>
                </div>
              </template>
            </SectionCardHeader>
          </template>
          <ReadModelSourceStrip
            class="content-source-strip"
            label="内容状态"
            :detail="tradingContentDetail"
            :status-text="tradingContentStatus"
            :status-type="contentCacheReady ? 'success' : 'warning'"
            :updated-at="contentUpdatedAtDisplay"
            :tags="tradingContentTags"
            compact
          />
          <div class="content-stream-grid">
            <section class="content-column">
              <strong>公告</strong>
              <div v-if="announcementItems.length" class="content-list">
                <article v-for="item in announcementItems.slice(0, 3)" :key="item.id" class="content-card-item">
                  <span>{{ formatDate(item.publishedAt) }}</span>
                  <h4>{{ item.title }}</h4>
                  <p>{{ item.summary }}</p>
                  <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">查看原文</a>
                </article>
              </div>
              <el-empty v-else description="暂无公告" />
            </section>
            <section class="content-column">
              <strong>资讯</strong>
              <div v-if="newsItems.length" class="content-list">
                <article v-for="item in newsItems.slice(0, 3)" :key="item.id" class="content-card-item">
                  <span>{{ formatDate(item.publishedAt) }}</span>
                  <h4>{{ item.title }}</h4>
                  <p>{{ item.summary }}</p>
                  <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">查看原文</a>
                </article>
              </div>
              <el-empty v-else description="暂无资讯" />
            </section>
            <section class="content-column">
              <strong>讨论</strong>
              <div v-if="topicItems.length" class="content-list">
                <article v-for="item in topicItems.slice(0, 3)" :key="item.id" class="content-card-item">
                  <span>{{ formatDate(item.publishedAt) }}</span>
                  <h4>{{ item.title }}</h4>
                  <p>{{ item.summary }}</p>
                  <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">查看原文</a>
                </article>
              </div>
              <el-empty v-else description="暂无讨论" />
            </section>
          </div>
        </el-card>

        <el-card v-if="!isPhoneLayout || activeTradeSection === 'positions'" id="trade-positions" class="glass-card" style="margin-top: 16px">
          <template #header>
            <SectionCardHeader title="当前持仓">
              <template #actions>
                <el-button type="primary" link @click="refreshTradingData">
                  <el-icon><Refresh /></el-icon> 刷新
                </el-button>
              </template>
            </SectionCardHeader>
          </template>
          <el-table v-if="!isPhoneLayout" :data="positions" style="width: 100%">
            <template #empty>
              <div class="table-empty-polish">
                <strong>当前账户还没有持仓</strong>
              </div>
            </template>
            <el-table-column prop="symbol" label="代码" width="110" />
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="quantity" label="数量" width="100" />
            <el-table-column prop="avgPrice" label="成本价" width="120">
              <template #default="{ row }">
                {{ formatMarketPrice(row.avgPrice) }}
              </template>
            </el-table-column>
            <el-table-column prop="currentPrice" label="现价" width="120">
              <template #default="{ row }">
                {{ formatMarketPrice(row.currentPrice) }}
              </template>
            </el-table-column>
            <el-table-column prop="pnl" label="盈亏" width="160">
              <template #default="{ row }">
                <span :class="row.pnl >= 0 ? 'up' : 'down'">
                  {{ formatSignedCurrency(row.pnl) }}
                  ({{ formatPercentValue(row.pnlPercent) }})
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button type="success" size="small" @click="quickBuy(row)">买入</el-button>
                <el-button type="danger" size="small" @click="quickSell(row)">卖出</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-else-if="positions.length" class="mobile-position-list">
            <article v-for="row in positions" :key="row.symbol" class="mobile-position-card">
              <div class="mobile-position-head">
                <div>
                  <strong>{{ row.symbol }}</strong>
                  <span>{{ row.name }}</span>
                </div>
                <span :class="row.pnl >= 0 ? 'up' : 'down'">
                  {{ formatSignedCurrency(row.pnl) }}
                </span>
              </div>
              <div class="mobile-position-meta">
                <span>持仓 {{ row.quantity }} 股</span>
                <span>成本 {{ formatMarketPrice(row.avgPrice) }}</span>
                <span>现价 {{ formatMarketPrice(row.currentPrice) }}</span>
              </div>
              <div class="mobile-position-actions">
                <el-button type="success" size="small" @click="quickBuy(row)">买入</el-button>
                <el-button type="danger" size="small" @click="quickSell(row)">卖出</el-button>
              </div>
            </article>
          </div>
          <el-empty v-else description="当前账户还没有持仓" />
        </el-card>

        <el-card v-if="!isPhoneLayout || activeTradeSection === 'orders'" id="trade-orders" class="glass-card" style="margin-top: 16px">
          <template #header>
            <SectionCardHeader
              title="近期订单"
              :badge="`${recentOrders.length} 条`"
            />
          </template>
          <el-table v-if="!isPhoneLayout" :data="recentOrders" style="width: 100%" empty-text="今日暂无订单">
            <template #empty>
              <div class="table-empty-polish compact">
                <strong>今日还没有新的订单</strong>
              </div>
            </template>
            <el-table-column prop="symbol" label="代码" width="120" />
            <el-table-column prop="action" label="方向" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.action === 'buy' ? 'success' : 'danger'">
                  {{ row.action === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="90" />
            <el-table-column prop="price" label="价格" width="120">
              <template #default="{ row }">
                {{ formatOrderPrice(row) }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="createTime" label="时间" min-width="180">
              <template #default="{ row }">
                {{ formatDate(row.createTime) }}
              </template>
            </el-table-column>
          </el-table>
          <div v-else-if="recentOrders.length" class="mobile-order-list">
            <article v-for="row in recentOrders" :key="`${row.symbol}-${row.createTime}`" class="mobile-order-card">
              <div class="mobile-position-head">
                <div>
                  <strong>{{ row.symbol }}</strong>
                  <span>{{ formatDate(row.createTime) }}</span>
                </div>
                <el-tag size="small" :type="row.action === 'buy' ? 'success' : 'danger'">
                  {{ row.action === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </div>
              <div class="mobile-position-meta">
                <span>{{ row.quantity }} 股</span>
                <span>价格 {{ formatOrderPrice(row) }}</span>
                <span>状态 {{ row.status }}</span>
              </div>
            </article>
          </div>
          <el-empty v-else description="今日暂无订单" />
        </el-card>
      </div>
    </div>

    <section v-if="isPhoneLayout" class="mobile-submit-dock">
      <div class="mobile-submit-copy">
        <span>{{ orderIntentTitle }}</span>
        <strong>{{ formatCurrency(estimatedAmount) }}</strong>
        <small>{{ orderReferenceSummary }}</small>
      </div>
      <el-button
        class="trade-submit-button"
        size="large"
        :type="orderForm.action === 'buy' ? 'success' : 'danger'"
        :disabled="!canTradeLive || submittingOrder"
        :loading="submittingOrder"
        @click="submitOrder"
      >
        {{ orderButtonText }}
      </el-button>
    </section>

    <el-drawer
      v-model="mobileConfirmVisible"
      class="trade-confirm-drawer"
      :with-header="false"
      size="92%"
      append-to-body
    >
      <div class="trade-confirm-sheet">
        <span class="feedback-kicker">下单确认</span>
        <h3>{{ orderIntentTitle }}</h3>
        <div class="feedback-meta-grid">
          <div class="feedback-meta-item">
            <span>股票</span>
            <strong>{{ (orderForm.symbol || '--').toUpperCase() }}</strong>
          </div>
          <div class="feedback-meta-item">
            <span>数量</span>
            <strong>{{ Number(orderForm.quantity || 0) }} 股</strong>
          </div>
          <div class="feedback-meta-item">
            <span>价格类型</span>
            <strong>{{ orderForm.orderType === 'limit' ? '限价' : '市价' }}</strong>
          </div>
          <div class="feedback-meta-item">
            <span>参考价格</span>
            <strong>{{ orderReferenceSummary }}</strong>
          </div>
        </div>
        <div class="trade-confirm-actions">
          <el-button @click="mobileConfirmVisible = false">再检查一下</el-button>
          <el-button
            class="trade-submit-button"
            :type="orderForm.action === 'buy' ? 'success' : 'danger'"
            :loading="submittingOrder"
            @click="confirmSubmitOrder"
          >
            {{ orderForm.action === 'buy' ? '确认买入' : '确认卖出' }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getQuantStatus } from '../api/analysis.js'
import { getDashboardMarketInsights, getLongbridgeAnnouncements, getLongbridgeNews, getLongbridgeSnapshot, getLongbridgeTopics, getSymbolOverview } from '../api/market.js'
import { buyStock, getBrokerAccounts, getProjectedOrders, getTradeSnapshotState, sellStock } from '../api/trade.js'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { getAccess, getCurrentUser } from '../utils/auth.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { useLongbridgeMarketStream, useOrderStream, useStockQuotes } from '../composables/useWebSocket.js'
import { sanitizeNarrativeText } from '../utils/contentSanitizer.js'
import { formatCurrency as formatCurrencyValue, formatOrderPrice, formatPercent as formatPercentDisplay } from '../utils/formatters.js'
import { buildContentCacheReadModelSummary, buildTradingReadModelSummary } from '../utils/readModelSource.js'

const route = useRoute()
const { isPhoneLayout } = useAdaptiveLayout()
const currentUser = getCurrentUser() || {}
const activeTradeSection = ref('order')
const selectedAccount = ref(null)
const accounts = ref([])
const positionSnapshots = ref([])
const projectedOrders = ref([])
const currentQuote = ref(null)
const quotePullFallback = ref(null)
const depthPullFallback = ref({})
const tradesPullFallback = ref([])
const quoteFetchStatus = ref('idle')
const depthFetchStatus = ref('idle')
const tradesFetchStatus = ref('idle')
const quoteLoading = ref(false)
const boardLoading = ref(false)
const marketInsights = ref([])
const quantStatus = ref({ enabled: false, autoExecute: false, signals: [] })
const tradeSnapshotMeta = ref({
  snapshotAt: '',
  dataSource: 'snapshot',
  sources: {},
  realtimeOverlay: [],
  positionCount: 0,
  orderCount: 0
})
const orderProjectionMeta = ref({
  snapshotAt: '',
  dataSource: 'order-projection',
  warnings: [],
  sources: {},
  query: {},
  realtimeOverlay: []
})
const announcementItems = ref([])
const newsItems = ref([])
const topicItems = ref([])
const contentMeta = ref({ dataSource: 'content-cache-empty', updatedAt: '', totalCount: 0 })
const contentRefreshing = ref(false)
const submittingOrder = ref(false)
const mobileConfirmVisible = ref(false)
const lastOrderFeedback = ref(null)
const AUTO_REFRESH_INTERVAL = 15000
let refreshTimer = null
let activeSymbolSearchId = 0

const orderForm = ref({
  symbol: '',
  action: 'buy',
  orderType: 'market',
  price: 0,
  quantity: 100
})

const accountSnapshot = ref({
  cash: 0,
  marketValue: 0,
  totalAssets: 0
})

const tradeMobileSections = computed(() => ([
  { value: 'order', label: '下单', note: orderForm.value.symbol ? orderForm.value.symbol : '快速委托' },
  { value: 'context', label: '账户', note: canTradeLive.value ? '执行上下文' : '观察模式' },
  { value: 'quote', label: '行情', note: currentQuote.value?.symbol || '盘口资讯' },
  { value: 'positions', label: '持仓', note: `${positions.value.length} 条` },
  { value: 'orders', label: '订单', note: `${recentOrders.value.length} 条` }
]))

const positionSymbols = computed(() => (
  positionSnapshots.value.map((item) => String(item.symbol || '').trim().toUpperCase()).filter(Boolean)
))

const { quotes: positionQuoteMap, isConnected: positionQuotesConnected } = useStockQuotes(positionSymbols, {
  userId: currentUser?.id || null
})

const positions = computed(() => {
  return positionSnapshots.value.map((item) => {
    const symbol = String(item.symbol || '').trim().toUpperCase()
    const quote = positionQuoteMap.value[symbol] || null
    if (!quote) {
      return item
    }

    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice || 0)
    const currentPrice = Number(quote.last_price ?? quote.price ?? item.currentPrice ?? 0)
    const marketValue = quantity * currentPrice
    const pnl = (currentPrice - avgPrice) * quantity
    const pnlPercent = avgPrice > 0 ? ((currentPrice - avgPrice) / avgPrice) * 100 : Number(item.pnlPercent || 0)

    return {
      ...item,
      currentPrice,
      current_price: currentPrice,
      marketValue,
      market_value: marketValue,
      pnl,
      pnlPercent,
      pnl_ratio: pnlPercent,
      change: Number(quote.change ?? (currentPrice - avgPrice)),
      changePercent: Number(quote.change_percent ?? quote.changePercent ?? pnlPercent),
      updatedAt: quote.timestamp || item.updatedAt || null
    }
  })
})

const accountInfo = computed(() => {
  const cash = Number(accountSnapshot.value.cash || 0)
  const marketValue = positions.value.length
    ? positions.value.reduce((sum, item) => sum + Number(item.marketValue || 0), 0)
    : Number(accountSnapshot.value.marketValue || 0)
  return {
    cash,
    marketValue,
    totalAssets: cash + marketValue
  }
})

const selectedPosition = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  if (!symbol) {
    return null
  }
  return positions.value.find((row) => String(row.symbol || '').toUpperCase() === symbol) || null
})

const estimatedAmount = computed(() => {
  const price = orderForm.value.orderType === 'market'
    ? Number(currentQuote.value?.price || selectedPosition.value?.currentPrice || 0)
    : Number(orderForm.value.price || 0)
  return price * Number(orderForm.value.quantity || 0)
})

const estimatedExposure = computed(() => {
  if (orderForm.value.action === 'sell') {
    const quantity = Number(selectedPosition.value?.quantity || 0)
    if (quantity <= 0) {
      return 0
    }
    return (Number(orderForm.value.quantity || 0) / quantity) * 100
  }

  const cash = Number(accountInfo.value.cash || 0)
  if (cash <= 0) {
    return 0
  }
  return (estimatedAmount.value / cash) * 100
})

const latestQuantSignal = computed(() => {
  const signals = Array.isArray(quantStatus.value?.signals) ? quantStatus.value.signals : []
  return signals[0] || null
})
const canTradeLive = computed(() => Boolean(getAccess()?.canTradeLive ?? accounts.value.length))
const selectedAccountName = computed(() => accounts.value.find((account) => account.id === selectedAccount.value)?.name || '未选择账户')
const selectedAccountRecord = computed(() => accounts.value.find((account) => account.id === selectedAccount.value) || null)
const selectedAccountTradingMode = computed(() => String(selectedAccountRecord.value?.tradingMode || selectedAccountRecord.value?.trading_mode || '').trim().toLowerCase())
const isPaperTradingAccount = computed(() => Boolean(
  selectedAccountRecord.value?.isPaper ??
  selectedAccountRecord.value?.is_paper ??
  selectedAccountTradingMode.value === 'paper'
))
const tradeSafetyTone = computed(() => {
  if (!selectedAccount.value) return 'warning'
  if (isPaperTradingAccount.value) return 'info'
  return canTradeLive.value ? 'danger' : 'warning'
})
const tradeSafetyTagType = computed(() => (
  tradeSafetyTone.value === 'danger' ? 'danger' : tradeSafetyTone.value === 'info' ? 'info' : 'warning'
))
const tradeSafetyTagText = computed(() => {
  if (!selectedAccount.value) return '未选择账户'
  return selectedAccountRecord.value?.accountModeLabel || selectedAccountRecord.value?.account_mode_label || (isPaperTradingAccount.value ? '模拟账户' : '交易账户')
})
const tradeSafetyHeadline = computed(() => {
  if (!selectedAccount.value) return '选择账户后再提交委托'
  if (isPaperTradingAccount.value) return '当前为模拟/演练环境'
  if (!canTradeLive.value) return '当前用户未开通真实交易'
  return '当前委托将进入真实交易链路'
})
const tradeSafetyMessage = computed(() => {
  if (!selectedAccount.value) return '请先确认券商账户、交易环境和标的代码，避免在错误账户上下单。'
  return selectedAccountRecord.value?.safetyMessage
    || selectedAccountRecord.value?.safety_message
    || (isPaperTradingAccount.value
      ? '当前账户为模拟环境，订单与订单状态仅用于演练。'
      : '当前账户为可交易环境，请再次确认价格、数量、交易时段和市场来源。')
})

const selectedMarketInsight = computed(() => {
  const targetMarket = detectMarket(currentQuote.value?.symbol || orderForm.value.symbol)
  const matched = marketInsights.value.find((item) => item.market === targetMarket)
  return matched || marketInsights.value[0] || null
})
const streamSymbols = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  return symbol ? [symbol] : []
})
const {
  quotes: liveQuoteMap,
  depth: liveDepthMap,
  trades: liveTradesMap,
  isConnected: quoteStreamConnected
} = useLongbridgeMarketStream(streamSymbols, {
  userId: currentUser?.id || null,
  subTypes: ['quote', 'depth', 'trade'],
  tradeCount: 18
})
const liveQuote = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  return symbol ? liveQuoteMap.value[symbol] || null : null
})
const liveDepth = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  return symbol ? liveDepthMap.value[symbol] || null : null
})
const liveTrades = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  return symbol ? liveTradesMap.value[symbol] || [] : []
})
const displaySymbol = computed(() => String(orderForm.value.symbol || '').trim().toUpperCase())
const hasLivePushQuote = computed(() => Boolean(liveQuote.value?.last_price !== undefined && liveQuote.value?.last_price !== null))
const hasLivePushDepth = computed(() => {
  const bidRows = liveDepth.value?.bids || liveDepth.value?.bid || []
  const askRows = liveDepth.value?.asks || liveDepth.value?.ask || []
  return (Array.isArray(bidRows) && bidRows.length > 0) || (Array.isArray(askRows) && askRows.length > 0)
})
const hasLivePushTrades = computed(() => Array.isArray(liveTrades.value) && liveTrades.value.length > 0)
const currentQuoteReady = computed(() => Boolean(currentQuote.value?.quoteReady))
const currentQuoteDisplayName = computed(() => currentQuote.value?.name || displaySymbol.value || '待选标的')
const currentQuoteSourceLabel = computed(() => {
  if (hasLivePushQuote.value) return 'Longbridge Push'
  const sourceKey = String(currentQuote.value?.quoteSource || '').toLowerCase()
  if (sourceKey.includes('longbridge-cli')) return 'Longbridge CLI'
  if (sourceKey.includes('quote-snapshot')) return '行情快照'
  if (sourceKey.includes('daily-history')) return '日线快照'
  if (sourceKey.includes('symbol-overview')) return '标的概览'
  if (currentQuoteReady.value) return 'Longbridge Pull'
  return '等待行情'
})
const quoteDataStatusTag = computed(() => {
  const status = String(currentQuote.value?.dataStatus || currentQuote.value?.data_status || '').trim().toLowerCase()
  if (!status) return ''
  if (status === 'stale') return '快照待更新'
  if (status === 'zero') return '报价为 0'
  if (status === 'empty') return '暂无成交'
  return ''
})
const quoteFetchStatusTag = computed(() => {
  if (quoteFetchStatus.value === 'degraded') return 'Quote 降级'
  if (quoteFetchStatus.value === 'failed') return 'Quote 失败'
  return ''
})
const quoteFetchStatusTagType = computed(() => (
  quoteFetchStatus.value === 'failed' ? 'danger' : 'warning'
))
const depthSourceLabel = computed(() => {
  if (hasLivePushDepth.value) return 'Longbridge Push'
  if (depthFetchStatus.value === 'failed') return '深度拉取失败'
  const bidRows = depthPullFallback.value?.bids || depthPullFallback.value?.bid || []
  const askRows = depthPullFallback.value?.asks || depthPullFallback.value?.ask || []
  return (Array.isArray(bidRows) && bidRows.length) || (Array.isArray(askRows) && askRows.length)
    ? 'Longbridge CLI/Pull'
    : '等待深度'
})
const tradesSourceLabel = computed(() => {
  if (hasLivePushTrades.value) return 'Longbridge Push'
  if (tradesFetchStatus.value === 'failed') return '逐笔拉取失败'
  return tradesPullFallback.value.length ? 'Longbridge CLI/Pull' : '等待逐笔'
})
const marketBoardBadge = computed(() => {
  if (depthFetchStatus.value === 'failed' || tradesFetchStatus.value === 'failed') return '接口降级'
  if (hasLivePushDepth.value || hasLivePushTrades.value) return '实时推送'
  if (depthBids.value.length || depthAsks.value.length || recentTape.value.length) return 'CLI 补位'
  return '刷新中'
})
const bestBidAskSummary = computed(() => {
  if (!depthBids.value.length && !depthAsks.value.length) {
    return '--'
  }
  const bid = depthBids.value[0]?.price ? formatMarketPrice(depthBids.value[0].price) : '--'
  const ask = depthAsks.value[0]?.price ? formatMarketPrice(depthAsks.value[0].price) : '--'
  return `${bid} / ${ask}`
})
const marketBoardWaitingText = computed(() => {
  if (depthFetchStatus.value === 'failed' || tradesFetchStatus.value === 'failed') {
    return '长桥行情拉取失败，仅展示当前可用数据，可点击刷新重试。'
  }
  if (quoteLoading.value || boardLoading.value) {
    return '等待长桥CLI数据/刷新中，收到推送或拉取补位后会自动更新。'
  }
  return '等待长桥CLI数据/刷新中，可点击刷新或保持推送连接。'
})
const toTimestampMs = (value) => {
  if (!value) return 0
  const parsed = Date.parse(String(value))
  return Number.isFinite(parsed) ? parsed : 0
}

const recentOrderStatusFilter = computed(() => '')
const {
  orders: streamedRecentOrders,
  dataSource: streamedOrderSource,
  snapshotAt: streamedOrdersSnapshotAt,
  meta: streamedOrderMeta,
  lastReceivedAt: orderStreamReceivedAt,
  subscriptionAccountId: orderStreamAccountId,
  subscriptionStatus: orderStreamStatus
} = useOrderStream(selectedAccount, recentOrderStatusFilter, { limit: 20 })

const hasRecentOrderStreamCoverage = computed(() => {
  if (!orderStreamReceivedAt.value) {
    return false
  }
  const currentAccountId = selectedAccount.value ? Number(selectedAccount.value) : null
  const streamAccountId = orderStreamAccountId.value !== null && orderStreamAccountId.value !== undefined
    ? Number(orderStreamAccountId.value)
    : null
  return currentAccountId === streamAccountId && String(orderStreamStatus.value || '') === ''
})

const recentOrders = computed(() => {
  const rows = hasRecentOrderStreamCoverage.value ? streamedRecentOrders.value : projectedOrders.value
  return Array.isArray(rows) ? rows.slice(0, 6) : []
})
const activeOrderProjectionMeta = computed(() => {
  if (hasRecentOrderStreamCoverage.value) {
    return streamedOrderMeta.value && typeof streamedOrderMeta.value === 'object'
      ? streamedOrderMeta.value
      : {}
  }
  return orderProjectionMeta.value
})
const orderRealtimeOverlayLabel = computed(() => {
  const overlays = Array.isArray(activeOrderProjectionMeta.value?.realtimeOverlay) ? activeOrderProjectionMeta.value.realtimeOverlay : []
  return overlays.includes('order-stream') ? '订单推送' : ''
})

const hasLiveTradingOverlay = computed(() => Boolean(
  (quoteStreamConnected.value && streamSymbols.value.length) ||
  hasRecentOrderStreamCoverage.value ||
  (positionQuotesConnected.value && positionSymbols.value.length)
))

const quickSymbols = computed(() => {
  const symbolSet = new Set()
  const currentSymbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  if (currentSymbol) {
    symbolSet.add(currentSymbol)
  }
  if (latestQuantSignal.value?.symbol) {
    symbolSet.add(String(latestQuantSignal.value.symbol).trim().toUpperCase())
  }
  positions.value.slice(0, 5).forEach((item) => {
    if (item?.symbol) {
      symbolSet.add(String(item.symbol).trim().toUpperCase())
    }
  })
  return Array.from(symbolSet).filter(Boolean).slice(0, 6)
})

const tradeHeroChips = computed(() => ([
  { text: tradingReadModelStatus.value, tone: tradingReadModelStatusType.value === 'success' ? 'healthy' : tradingReadModelStatusType.value },
  { text: canTradeLive.value ? '真实交易已启用' : '观察模式', tone: canTradeLive.value ? 'healthy' : 'warning' },
  { text: quoteStreamConnected.value ? '行情在线' : '行情快照', tone: quoteStreamConnected.value ? 'healthy' : 'warning' },
  { text: hasRecentOrderStreamCoverage.value ? '订单在线' : '订单快照', tone: hasRecentOrderStreamCoverage.value ? 'healthy' : 'warning' }
]))
const orderButtonText = computed(() => {
  if (submittingOrder.value) {
    return orderForm.value.action === 'buy' ? '买入提交中...' : '卖出提交中...'
  }
  if (isPhoneLayout.value) {
    return orderForm.value.action === 'buy' ? '下单确认' : '确认卖出'
  }
  return orderForm.value.action === 'buy' ? '提交买入' : '提交卖出'
})
const orderIntentTitle = computed(() => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase() || '未选择标的'
  return `${orderForm.value.action === 'buy' ? '买入' : '卖出'} ${symbol}`
})
const orderIntentDescription = computed(() => {
  const orderTypeLabel = orderForm.value.orderType === 'limit' ? '限价委托' : '市价委托'
  const quantity = Number(orderForm.value.quantity || 0)
  const exposureLabel = orderForm.value.action === 'buy'
    ? `约占可用资金 ${formatRatio(estimatedExposure.value)}`
    : `约占持仓 ${formatRatio(estimatedExposure.value)}`
  return `${orderTypeLabel} · ${quantity} 股 · ${exposureLabel}`
})
const orderReferencePrice = computed(() => {
  if (orderForm.value.orderType === 'limit' && Number(orderForm.value.price || 0) > 0) {
    return Number(orderForm.value.price || 0)
  }
  return Number(currentQuote.value?.price || selectedPosition.value?.currentPrice || 0)
})
const orderReferenceSummary = computed(() => formatReferencePrice(orderReferencePrice.value))
const tradingReadModelSummary = computed(() => buildTradingReadModelSummary({
  hasAccount: Boolean(selectedAccount.value),
  accountLabel: selectedAccountName.value !== '未选择账户' ? selectedAccountName.value : '',
  tradeMeta: tradeSnapshotMeta.value,
  orderMeta: activeOrderProjectionMeta.value,
  hasLiveOverlay: hasLiveTradingOverlay.value,
  hasRecentOrderStreamCoverage: hasRecentOrderStreamCoverage.value,
  quoteStreamConnected: quoteStreamConnected.value,
  positionQuotesConnected: positionQuotesConnected.value,
  streamSymbolCount: streamSymbols.value.length,
  positionSymbolCount: positionSymbols.value.length,
  recentOrderCount: recentOrders.value.length
}))
const tradingReadModelStatus = computed(() => tradingReadModelSummary.value.statusText)
const tradingReadModelStatusType = computed(() => tradingReadModelSummary.value.statusType)
const tradingReadModelUpdatedAt = computed(() => (
  tradingReadModelSummary.value.updatedAt ? formatDate(tradingReadModelSummary.value.updatedAt) : ''
))
const tradingReadModelUpdatedPrefix = computed(() => tradingReadModelSummary.value.updatedPrefix)
const tradingReadModelTags = computed(() => {
  const tags = [...(tradingReadModelSummary.value.tags || [])]
  if (hasRecentOrderStreamCoverage.value) {
    const replacement = streamedOrderSource.value === 'live-backfill'
      ? '订单状态回填中'
      : `${orderRealtimeOverlayLabel.value || '订单状态'} 实时推进`
    const targetIndex = tags.findIndex((item) => String(item?.text || '').includes('订单状态实时推进'))
    if (targetIndex >= 0) {
      tags[targetIndex] = { ...tags[targetIndex], text: replacement }
    }
  }
  return tags
})

const contentCacheReady = computed(() => Number(contentMeta.value?.totalCount || 0) > 0)
const tradingContentSummary = computed(() => buildContentCacheReadModelSummary(
  contentMeta.value,
  {
    symbol: orderForm.value.symbol,
    sourceLabel: 'symbol_content_cache',
    refreshing: contentRefreshing.value
  }
))
const tradingContentStatus = computed(() => tradingContentSummary.value.statusText)
const contentUpdatedAtDisplay = computed(() => (
  tradingContentSummary.value.updatedAt ? formatDate(tradingContentSummary.value.updatedAt) : ''
))
const tradingContentDetail = computed(() => tradingContentSummary.value.detail)
const tradingContentTags = computed(() => ([
  ...(tradingContentSummary.value.tags || []),
  { type: contentRefreshing.value ? 'warning' : 'info', text: contentRefreshing.value ? '回源刷新中' : '内容缓存' }
]))

const clearSymbolContent = () => {
  announcementItems.value = []
  newsItems.value = []
  topicItems.value = []
  contentMeta.value = { dataSource: 'content-cache-empty', updatedAt: '', totalCount: 0 }
}

const pickFirstDefinedValue = (...values) => {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') {
      return value
    }
  }
  return undefined
}

const pickNumericValue = (values = [], { positiveOnly = false } = {}) => {
  for (const value of values) {
    if (value === null || value === undefined || value === '') {
      continue
    }
    const number = Number(value)
    if (!Number.isFinite(number)) {
      continue
    }
    if (positiveOnly && number <= 0) {
      continue
    }
    return number
  }
  return undefined
}

const buildOverviewQuotePayload = (overview = {}, symbol = '', fallbackPosition = null) => {
  const quoteSnapshot = overview?.quoteSnapshot || {}
  const dailySnapshot = overview?.snapshots?.daily || {}
  const quotePrice = pickNumericValue([
    quoteSnapshot?.price,
    quoteSnapshot?.last_price,
    dailySnapshot?.closePrice,
    dailySnapshot?.close_price
  ], { positiveOnly: true })
  const prevClose = pickNumericValue([
    quoteSnapshot?.prevClose,
    quoteSnapshot?.prev_close,
    dailySnapshot?.prevClose,
    dailySnapshot?.prev_close
  ], { positiveOnly: true })
  const changePercent = pickNumericValue([
    quoteSnapshot?.changePercent,
    quoteSnapshot?.change_percent,
    dailySnapshot?.changePercent,
    dailySnapshot?.change_percent
  ])
  const change = pickNumericValue([
    quoteSnapshot?.change,
    dailySnapshot?.change,
    Number.isFinite(prevClose) && Number.isFinite(quotePrice) ? quotePrice - prevClose : undefined
  ])
  const hasQuoteSnapshotPrice = pickNumericValue([
    quoteSnapshot?.price,
    quoteSnapshot?.last_price
  ], { positiveOnly: true }) !== undefined
  const hasDailySnapshotPrice = pickNumericValue([
    dailySnapshot?.closePrice,
    dailySnapshot?.close_price
  ], { positiveOnly: true }) !== undefined

  return {
    symbol,
    name: overview?.fundamentals?.name || overview?.name || fallbackPosition?.name || symbol,
    price: quotePrice,
    last_price: quotePrice,
    prev_close: prevClose,
    prevClose: prevClose,
    change_percent: changePercent,
    changePercent: changePercent,
    change,
    volume: pickNumericValue([quoteSnapshot?.volume, dailySnapshot?.volume]),
    open: pickNumericValue([quoteSnapshot?.open, dailySnapshot?.openPrice, dailySnapshot?.open_price], { positiveOnly: true }),
    high: pickNumericValue([quoteSnapshot?.high, dailySnapshot?.highPrice, dailySnapshot?.high_price], { positiveOnly: true }),
    low: pickNumericValue([quoteSnapshot?.low, dailySnapshot?.lowPrice, dailySnapshot?.low_price], { positiveOnly: true }),
    session: quoteSnapshot?.session || '',
    timestamp: pickFirstDefinedValue(
      quoteSnapshot?.snapshotAt,
      quoteSnapshot?.snapshot_at,
      quoteSnapshot?.updatedAt,
      dailySnapshot?.snapshotDate
    ) || '',
    source: hasQuoteSnapshotPrice
      ? 'quote-snapshot'
      : hasDailySnapshotPrice
        ? 'daily-history'
        : 'symbol-overview'
  }
}

const applyOverviewPayload = (overview = {}, symbol = '', fallbackPosition = null) => {
  const nextQuote = normalizeQuote(buildOverviewQuotePayload(overview, symbol, fallbackPosition))
  currentQuote.value = nextQuote
  applyContentBundle(overview?.contentCache || {}, 'content-cache')
  return nextQuote
}

const normalizeSnapshotQuotePayload = (payload = [], symbol = '') => {
  if (Array.isArray(payload)) {
    return payload.find((item) => String(item?.symbol || '').trim().toUpperCase() === symbol) || payload[0] || {}
  }
  return payload && typeof payload === 'object' ? payload : {}
}

const normalizeDepthRows = (rows = []) => {
  const items = Array.isArray(rows) ? rows : []
  return items.slice(0, 5).map((item, index) => ({
    id: `${index}-${item?.price ?? index}`,
    price: Number(item?.price ?? item?.price_value ?? 0),
    volume: Number(item?.volume ?? item?.quantity ?? item?.size ?? 0)
  }))
}

const depthSnapshot = computed(() => {
  if (hasLivePushDepth.value) {
    return liveDepth.value || {}
  }
  return depthPullFallback.value || {}
})

const depthBids = computed(() => normalizeDepthRows(depthSnapshot.value?.bids || depthSnapshot.value?.bid || []))
const depthAsks = computed(() => normalizeDepthRows(depthSnapshot.value?.asks || depthSnapshot.value?.ask || []))

const recentTape = computed(() => {
  const tradeRows = hasLivePushTrades.value ? liveTrades.value : tradesPullFallback.value
  return (Array.isArray(tradeRows) ? tradeRows : []).slice(0, 10).map((item, index) => {
    const direction = String(item?.trade_direction || item?.direction || '').toLowerCase()
    const isBuy = direction.includes('buy') || direction.includes('up')
    const isSell = direction.includes('sell') || direction.includes('down')
    return {
      id: item?.trade_id || item?.id || `${orderForm.value.symbol}-${index}`,
      price: Number(item?.price ?? item?.last_done ?? 0),
      volume: Number(item?.volume ?? item?.quantity ?? item?.trade_volume ?? 0),
      timestamp: item?.timestamp || item?.trade_time || item?.time || '',
      sideLabel: isBuy ? '主动买' : isSell ? '主动卖' : '成交',
      sideClass: isBuy ? 'up' : isSell ? 'down' : ''
    }
  })
})

const normalizeContentItems = (items = [], type = 'news') => {
  return (Array.isArray(items) ? items : []).map((item, index) => ({
    id: item?.id || `${type}-${index}`,
    title: sanitizeNarrativeText(item?.title || item?.file_name || orderForm.value.symbol, orderForm.value.symbol || '--'),
    summary: sanitizeNarrativeText(
      item?.description || item?.content || item?.title,
      `${orderForm.value.symbol || '当前标的'} 已同步最新${type === 'announcements' ? '公告' : type === 'topics' ? '讨论' : '资讯'}。`
    ),
    publishedAt: item?.published_at || item?.publish_time || item?.time || '',
    url: item?.url || item?.file_urls?.[0] || '',
    fetchedAt: item?.cache_fetched_at || item?.fetched_at || '',
    sourceLabel: `${String(item?.data_source || '').includes('content-cache') ? '缓存 · ' : ''}${type === 'announcements' ? '长桥公告' : type === 'topics' ? '长桥讨论' : '长桥资讯'}`
  }))
}

const applyContentBundle = (bundle = {}, fallbackSource = 'content-cache') => {
  const announcementRows = Array.isArray(bundle?.announcements?.items) ? bundle.announcements.items : []
  const newsRows = Array.isArray(bundle?.news?.items) ? bundle.news.items : []
  const topicRows = Array.isArray(bundle?.topics?.items) ? bundle.topics.items : []

  announcementItems.value = normalizeContentItems(announcementRows, 'announcements')
  newsItems.value = normalizeContentItems(newsRows, 'news')
  topicItems.value = normalizeContentItems(topicRows, 'topics')
  contentMeta.value = {
    dataSource: bundle?.dataSource || fallbackSource,
    updatedAt: bundle?.updatedAt
      || bundle?.announcements?.updatedAt
      || bundle?.news?.updatedAt
      || bundle?.topics?.updatedAt
      || '',
    totalCount: Number(bundle?.totalCount || (announcementRows.length + newsRows.length + topicRows.length))
  }
}

const loadSymbolOverview = async (symbol, { fallbackPosition = null, applyQuote = true } = {}) => {
  const normalizedSymbol = String(symbol || '').trim().toUpperCase()
  if (!normalizedSymbol) {
    clearSymbolContent()
    return {}
  }

  const overviewRes = await getSymbolOverview(normalizedSymbol)
  const overviewData = overviewRes?.data || {}
  if (applyQuote) {
    applyOverviewPayload(overviewData, normalizedSymbol, fallbackPosition)
  } else {
    applyContentBundle(overviewData?.contentCache || {}, 'content-cache')
  }
  return overviewData
}

const refreshContentFeeds = async (symbol) => {
  const normalizedSymbol = String(symbol || '').trim().toUpperCase()
  if (!normalizedSymbol) {
    announcementItems.value = []
    newsItems.value = []
    topicItems.value = []
    contentMeta.value = { dataSource: 'content-cache-empty', updatedAt: '', totalCount: 0 }
    return
  }

  const [announcementRes, newsRes, topicRes] = await Promise.allSettled([
    getLongbridgeAnnouncements(normalizedSymbol),
    getLongbridgeNews(normalizedSymbol),
    getLongbridgeTopics(normalizedSymbol)
  ])

  const sourceCandidates = [
    announcementRes.status === 'fulfilled' ? announcementRes.value?.data?.dataSource : '',
    newsRes.status === 'fulfilled' ? newsRes.value?.data?.dataSource : '',
    topicRes.status === 'fulfilled' ? topicRes.value?.data?.dataSource : ''
  ].filter(Boolean)
  const updatedCandidates = [
    ...(announcementRes.status === 'fulfilled' ? (announcementRes.value?.data?.payload || []) : []),
    ...(newsRes.status === 'fulfilled' ? (newsRes.value?.data?.payload || []) : []),
    ...(topicRes.status === 'fulfilled' ? (topicRes.value?.data?.payload || []) : [])
  ].map((item) => item?.cache_fetched_at || item?.fetched_at || '').filter(Boolean).sort()

  announcementItems.value = announcementRes.status === 'fulfilled'
    ? normalizeContentItems(announcementRes.value?.data?.payload || announcementRes.value?.data || [], 'announcements')
    : []
  newsItems.value = newsRes.status === 'fulfilled'
    ? normalizeContentItems(newsRes.value?.data?.payload || newsRes.value?.data || [], 'news')
    : []
  topicItems.value = topicRes.status === 'fulfilled'
    ? normalizeContentItems(topicRes.value?.data?.payload || topicRes.value?.data || [], 'topics')
    : []

  contentMeta.value = {
    dataSource: sourceCandidates.find((item) => String(item).includes('content-cache'))
      || sourceCandidates[0]
      || 'content-cache-empty',
    updatedAt: updatedCandidates[updatedCandidates.length - 1] || '',
    totalCount: announcementItems.value.length + newsItems.value.length + topicItems.value.length
  }
}

const loadSymbolFeeds = async (symbol, { refreshContent = false } = {}) => {
  const normalizedSymbol = String(symbol || '').trim().toUpperCase()
  if (!normalizedSymbol) {
    clearSymbolContent()
    return
  }

  try {
    await loadSymbolOverview(normalizedSymbol)
  } catch (error) {
    console.error('加载内容缓存失败:', error)
    applyContentBundle({}, 'content-cache-empty')
  }

  if (refreshContent || !contentCacheReady.value) {
    await refreshContentFeeds(normalizedSymbol)
  }
}

const refreshSymbolContent = async () => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  if (!symbol) {
    return
  }
  contentRefreshing.value = true
  try {
    await loadSymbolFeeds(symbol, { refreshContent: true })
  } finally {
    contentRefreshing.value = false
  }
}

const loadAccounts = async () => {
  try {
    const res = await getBrokerAccounts()
    accounts.value = res.data || []
    if (accounts.value.length > 0 && !selectedAccount.value) {
      const defaultAccount = accounts.value.find((account) => account.isDefault || account.is_default)
      selectedAccount.value = defaultAccount?.id || accounts.value[0].id
    }
  } catch (error) {
    console.error('加载账户失败:', error)
  }
}

const loadTradeSnapshotBase = async () => {
  if (!selectedAccount.value) {
    positionSnapshots.value = []
    accountSnapshot.value = {
      cash: 0,
      marketValue: 0,
      totalAssets: 0
    }
    tradeSnapshotMeta.value = {
      snapshotAt: '',
      dataSource: 'snapshot',
      sources: {},
      realtimeOverlay: [],
      positionCount: 0,
      orderCount: 0
    }
    return
  }

  try {
    const res = await getTradeSnapshotState(selectedAccount.value)
    const state = res.data || {}
    positionSnapshots.value = Array.isArray(state.positions) ? state.positions : []
    accountSnapshot.value = {
      cash: Number(state.accountInfo?.cash || 0),
      marketValue: Number(state.accountInfo?.market_value || state.accountInfo?.marketValue || 0),
      totalAssets: Number(state.accountInfo?.total_equity || state.accountInfo?.totalAssets || 0)
    }
    tradeSnapshotMeta.value = {
      snapshotAt: state.snapshotAt || '',
      dataSource: state.dataSource || 'snapshot',
      ...(state.meta && typeof state.meta === 'object' ? state.meta : {})
    }
  } catch (error) {
    console.error('加载交易快照失败:', error)
  }
}

const loadProjectedRecentOrders = async () => {
  if (!selectedAccount.value) {
    projectedOrders.value = []
    orderProjectionMeta.value = {
      snapshotAt: '',
      dataSource: 'order-projection',
      warnings: [],
      sources: {},
      query: {},
      realtimeOverlay: []
    }
    return
  }

  try {
    const res = await getProjectedOrders({
      account_id: selectedAccount.value,
      limit: 20
    })
    projectedOrders.value = Array.isArray(res.data?.list) ? res.data.list : []
    orderProjectionMeta.value = {
      snapshotAt: res.data?.snapshotAt || '',
      dataSource: res.data?.dataSource || 'order-projection',
      warnings: Array.isArray(res.data?.warnings) ? res.data.warnings : [],
      ...(res.data?.meta && typeof res.data.meta === 'object' ? res.data.meta : {})
    }
  } catch (error) {
    console.error('加载订单快照失败:', error)
  }
}

const loadContextPanels = async () => {
  const results = await Promise.allSettled([
    getDashboardMarketInsights(),
    getQuantStatus()
  ])

  const [marketResult, quantResult] = results

  if (marketResult.status === 'fulfilled') {
    marketInsights.value = Array.isArray(marketResult.value?.data) ? marketResult.value.data : []
  }

  if (quantResult.status === 'fulfilled') {
    quantStatus.value = quantResult.value?.data || { enabled: false, autoExecute: false, signals: [] }
  }
}

const normalizeQuote = (raw = {}) => {
  const symbol = String(raw.symbol || orderForm.value.symbol || '').trim().toUpperCase()
  const priceValue = raw.price ?? raw.last_price
  const prevCloseValue = raw.prevClose ?? raw.prev_close
  const changePercentValue = raw.changePercent ?? raw.change_percent
  const price = priceValue === null || priceValue === undefined || priceValue === '' ? null : Number(priceValue)
  const prevClose = prevCloseValue === null || prevCloseValue === undefined || prevCloseValue === '' ? null : Number(prevCloseValue)
  const changePercent = changePercentValue === null || changePercentValue === undefined || changePercentValue === '' ? null : Number(changePercentValue)
  const directChange = raw.change
  const change = directChange === null || directChange === undefined || directChange === ''
    ? (Number.isFinite(prevClose) && Number.isFinite(price) ? price - prevClose : null)
    : Number(directChange)
  const hasQuoteBase = Boolean(
    (Number.isFinite(price) && price > 0) ||
    (Number.isFinite(prevClose) && prevClose > 0) ||
    raw.timestamp ||
    raw.snapshotAt ||
    raw.quoteSnapshotAt
  )
  const hasAnyQuoteValue = Boolean(
    Number.isFinite(price) ||
    Number.isFinite(prevClose) ||
    raw.timestamp ||
    raw.snapshotAt ||
    raw.quoteSnapshotAt
  )
  const dataStatus = raw.dataStatus || raw.data_status || (
    hasQuoteBase ? 'ready' : hasAnyQuoteValue ? 'zero' : 'empty'
  )
  return {
    ...raw,
    symbol,
    name: raw.name || symbol,
    price,
    change,
    changePercent,
    volume: raw.volume === null || raw.volume === undefined || raw.volume === '' ? null : Number(raw.volume),
    open: raw.open === null || raw.open === undefined || raw.open === '' ? null : Number(raw.open),
    high: raw.high === null || raw.high === undefined || raw.high === '' ? null : Number(raw.high),
    low: raw.low === null || raw.low === undefined || raw.low === '' ? null : Number(raw.low),
    prevClose,
    session: raw.session || '',
    quoteSource: raw.quoteSource || raw.quote_source || raw.source || '',
    quote_source: raw.quoteSource || raw.quote_source || raw.source || '',
    quoteReady: raw.quoteReady ?? raw.quote_ready ?? hasQuoteBase,
    timestamp: raw.timestamp || raw.snapshotAt || raw.quoteSnapshotAt || '',
    dataStatus
  }
}

const getSessionLabel = (session) => {
  const sessionMap = {
    'pre-market': '盘前',
    'pre_market': '盘前',
    'premarket': '盘前',
    'regular': '盘中',
    'trading': '盘中',
    'normal': '盘中',
    'after-hours': '盘后',
    'after_hours': '盘后',
    'afterhours': '盘后',
    'post-market': '盘后',
    'post_market': '盘后',
    'night': '夜盘',
    'night-session': '夜盘',
    'night_session': '夜盘',
    'closed': '休市',
    'halted': '停牌',
    'suspended': '停牌'
  }
  const key = String(session || '').toLowerCase().replace(/[\s_-]/g, '')
  for (const [k, v] of Object.entries(sessionMap)) {
    if (k.replace(/[\s_-]/g, '') === key) {
      return v
    }
  }
  if (key.includes('pre') || key.includes('before')) return '盘前'
  if (key.includes('after') || key.includes('post')) return '盘后'
  if (key.includes('night')) return '夜盘'
  if (key.includes('regular') || key.includes('trading')) return '盘中'
  if (key.includes('close') || key.includes('halt')) return '休市'
  return '盘中'
}

const getSessionTagType = (session) => {
  const key = String(session || '').toLowerCase()
  if (key.includes('pre') || key.includes('before')) return 'warning'
  if (key.includes('after') || key.includes('post')) return 'info'
  if (key.includes('night')) return ''
  if (key.includes('close') || key.includes('halt')) return 'danger'
  return 'success'
}

const searchSymbol = async () => {
  const symbol = displaySymbol.value
  const searchId = ++activeSymbolSearchId
  if (!symbol) {
    currentQuote.value = null
    quotePullFallback.value = null
    depthPullFallback.value = {}
    tradesPullFallback.value = []
    quoteFetchStatus.value = 'idle'
    depthFetchStatus.value = 'idle'
    tradesFetchStatus.value = 'idle'
    clearSymbolContent()
    quoteLoading.value = false
    boardLoading.value = false
    contentRefreshing.value = false
    return
  }

  orderForm.value.symbol = symbol
  const fallbackPosition = positions.value.find((row) => String(row.symbol || '').trim().toUpperCase() === symbol) || null
  currentQuote.value = fallbackPosition ? normalizeQuote({
    symbol,
    name: fallbackPosition?.name || symbol
  }) : null
  quotePullFallback.value = null
  depthPullFallback.value = {}
  tradesPullFallback.value = []
  quoteFetchStatus.value = 'loading'
  depthFetchStatus.value = 'loading'
  tradesFetchStatus.value = 'loading'
  clearSymbolContent()
  quoteLoading.value = true
  boardLoading.value = true
  contentRefreshing.value = false
  try {
    let quoteSurfaceReleased = false
    const releaseQuoteSurface = () => {
      if (quoteSurfaceReleased || searchId !== activeSymbolSearchId) {
        return
      }
      quoteSurfaceReleased = true
      if (orderForm.value.orderType === 'limit' && Number(currentQuote.value?.price || 0) > 0) {
        orderForm.value.price = Number(currentQuote.value.price)
      }
      if (isPhoneLayout.value) {
        activeTradeSection.value = 'quote'
      }
      quoteLoading.value = false
    }

    const overviewTask = loadSymbolOverview(symbol, { fallbackPosition, applyQuote: false })
      .then((overviewData) => {
        if (searchId !== activeSymbolSearchId) {
          return { ok: false, stale: true }
        }
        const overviewQuote = normalizeQuote(buildOverviewQuotePayload(overviewData, symbol, fallbackPosition))
        const liveQuoteReady = Boolean(
          quotePullFallback.value &&
          String(quotePullFallback.value.symbol || '').trim().toUpperCase() === symbol &&
          quotePullFallback.value.quoteReady
        )
        if (!liveQuoteReady) {
          currentQuote.value = overviewQuote
          releaseQuoteSurface()
        }
        return { ok: true, overviewData, quote: overviewQuote }
      })
      .catch((error) => {
        console.warn('加载标的概览失败:', error)
        return { ok: false, error }
      })

    const snapshotTask = getLongbridgeSnapshot(symbol, { count: 18 })
      .then((snapshotRes) => {
        if (searchId !== activeSymbolSearchId) {
          return { ok: false, stale: true }
        }
        const snapshot = snapshotRes?.data?.payload || snapshotRes?.data || {}
        const quotePayload = normalizeSnapshotQuotePayload(snapshot.quote, symbol)
        const normalizedQuote = normalizeQuote({
          ...quotePayload,
          symbol,
          name: currentQuote.value?.name || fallbackPosition?.name || symbol,
          source: quotePayload?.quoteSource || quotePayload?.quote_source || snapshot?.sources?.quote || 'longbridge-cli',
          dataStatus: quotePayload && Object.keys(quotePayload).length ? undefined : 'empty'
        })
        quotePullFallback.value = normalizedQuote
        currentQuote.value = normalizedQuote
        quoteFetchStatus.value = 'success'
        depthFetchStatus.value = 'success'
        tradesFetchStatus.value = 'success'
        depthPullFallback.value = snapshot?.depth || {}
        tradesPullFallback.value = Array.isArray(snapshot?.trades) ? snapshot.trades : []
        releaseQuoteSurface()
        return { ok: true }
      })
      .catch((error) => {
        console.warn('加载实时行情快照失败:', error)
        return { ok: false, error }
      })

    const overviewState = await overviewTask
    const contentTask = overviewState.ok && !contentCacheReady.value
      ? (async () => {
          contentRefreshing.value = true
          try {
            await refreshContentFeeds(symbol)
          } finally {
            if (searchId === activeSymbolSearchId) {
              contentRefreshing.value = false
            }
          }
        })()
      : Promise.resolve()
    const quoteState = await snapshotTask

    if (searchId !== activeSymbolSearchId) {
      return
    }

    if (!quoteState.ok) {
      depthFetchStatus.value = 'failed'
      tradesFetchStatus.value = 'failed'
    }

    quoteFetchStatus.value = quoteState.ok
      ? 'success'
      : overviewState.ok && currentQuoteReady.value
        ? 'degraded'
        : 'failed'

    if (!overviewState.ok && !quoteState.ok) {
      currentQuote.value = fallbackPosition
        ? normalizeQuote({ symbol, name: fallbackPosition.name || symbol })
        : normalizeQuote({ symbol, name: symbol })
      throw overviewState.error || quoteState.error
    }

    releaseQuoteSurface()
    await Promise.allSettled([contentTask])
  } catch (error) {
    if (searchId !== activeSymbolSearchId) {
      return
    }
    console.error('搜索股票失败:', error)
    ElMessage.error('获取行情失败，请检查股票代码')
  } finally {
    if (searchId !== activeSymbolSearchId) {
      return
    }
    quoteLoading.value = false
    boardLoading.value = false
  }
}

const fillSymbol = async (symbol) => {
  const nextSymbol = String(symbol || '').trim().toUpperCase()
  if (!nextSymbol) {
    return
  }
  orderForm.value.symbol = nextSymbol
  lastOrderFeedback.value = null
  await searchSymbol()
}

const extractOrderError = (error) => {
  const payload = error?.data || error?.response?.data || {}
  const payloadData = payload?.data && typeof payload.data === 'object' ? payload.data : {}
  return {
    status: Number(error?.response?.status || 0),
    message: payload?.error || error?.message || '未知错误',
    meta: payloadData
  }
}

const submitOrderRequest = async () => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  if (!canTradeLive.value) {
    ElMessage.warning('当前用户未绑定可用券商账户，暂不可直接下单')
    return
  }

  if (!selectedAccount.value || !symbol) {
    ElMessage.warning('请先选择账户并输入股票代码')
    return
  }

  submittingOrder.value = true
  try {
    const data = {
      symbol,
      quantity: Number(orderForm.value.quantity || 0),
      price: orderForm.value.orderType === 'limit' ? Number(orderForm.value.price || 0) : null,
      account_id: selectedAccount.value
    }

    let response
    if (orderForm.value.action === 'buy') {
      response = await buyStock(data)
      ElMessage.success('买入订单已提交')
    } else {
      response = await sellStock(data)
      ElMessage.success('卖出订单已提交')
    }

    lastOrderFeedback.value = {
      kind: 'success',
      title: orderForm.value.action === 'buy' ? '买入委托已提交' : '卖出委托已提交',
      message: response?.message || '委托已提交，订单区会继续刷新状态。',
      meta: {
        referencePrice: response?.referencePrice,
        referencePriceSource: response?.referencePriceSource,
        referencePriceSnapshotAt: response?.referencePriceSnapshotAt,
        degraded: response?.degraded
      }
    }
    mobileConfirmVisible.value = false
    activeTradeSection.value = 'orders'
    await refreshTradingData()
  } catch (error) {
    const parsed = extractOrderError(error)
    lastOrderFeedback.value = {
      kind: 'error',
      title: parsed.status === 422 ? '风控拒绝本次委托' : '订单提交失败',
      message: parsed.message,
      meta: parsed.meta
    }
    ElMessage.error(parsed.message)
  } finally {
    submittingOrder.value = false
  }
}

const submitOrder = async () => {
  const symbol = String(orderForm.value.symbol || '').trim().toUpperCase()
  if (!canTradeLive.value) {
    ElMessage.warning('当前用户未绑定可用券商账户，暂不可直接下单')
    return
  }

  if (!selectedAccount.value || !symbol) {
    ElMessage.warning('请先选择账户并输入股票代码')
    return
  }

  if (isPhoneLayout.value) {
    mobileConfirmVisible.value = true
    return
  }
  await submitOrderRequest()
}

const confirmSubmitOrder = async () => {
  await submitOrderRequest()
}

const quickBuy = async (row) => {
  orderForm.value.symbol = row.symbol
  orderForm.value.action = 'buy'
  orderForm.value.quantity = 100
  orderForm.value.orderType = 'market'
  await searchSymbol()
  activeTradeSection.value = 'order'
}

const quickSell = async (row) => {
  orderForm.value.symbol = row.symbol
  orderForm.value.action = 'sell'
  orderForm.value.quantity = Number(row.quantity || 0)
  orderForm.value.orderType = 'market'
  await searchSymbol()
  activeTradeSection.value = 'order'
}

const applyQuantityPreset = (quantity) => {
  orderForm.value.quantity = Number(quantity || 0)
}

const fillAvailablePosition = () => {
  if (!selectedPosition.value) {
    ElMessage.warning('当前代码没有匹配到持仓')
    return
  }
  orderForm.value.quantity = Number(selectedPosition.value.quantity || 0)
}

const refreshTradingData = async () => {
  await Promise.allSettled([
    loadTradeSnapshotBase(),
    loadProjectedRecentOrders(),
    loadContextPanels(),
    orderForm.value.symbol ? searchSymbol() : Promise.resolve()
  ])
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!selectedAccount.value) {
    return
  }

  refreshTimer = window.setInterval(() => {
    refreshTradingData()
  }, AUTO_REFRESH_INTERVAL)
}

const detectMarket = (symbol) => {
  const target = String(symbol || '').trim().toUpperCase()
  if (!target) {
    return 'US'
  }
  if (target.endsWith('.HK') || /^\d{5}$/.test(target)) {
    return 'HK'
  }
  if (target.endsWith('.SH') || target.endsWith('.SZ') || /^\d{6}$/.test(target)) {
    return 'CN'
  }
  return 'US'
}

const detectMarketLabel = (symbol) => {
  const market = detectMarket(symbol)
  return {
    US: '美股',
    CN: 'A股',
    HK: '港股'
  }[market]
}

const formatCurrency = (value) => formatCurrencyValue(value, { currency: '$' })
const formatMarketPrice = (value) => formatCurrencyValue(value, { currency: '$', fallback: '--' })
const formatSignedCurrency = (value) => formatCurrencyValue(value, { currency: '$', signed: true, absolute: true, fallback: '--' })
const formatPercentValue = (value) => formatPercentDisplay(value)

const formatRatio = (value, appendPercent = true) => {
  const amount = Number(value || 0)
  if (appendPercent) {
    return `${amount.toFixed(2)}%`
  }
  return amount.toFixed(2)
}

const formatVolume = (value) => {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  const amount = Number(value)
  if (!Number.isFinite(amount)) {
    return '--'
  }
  if (amount === 0) {
    return '0'
  }
  if (amount >= 100000000) {
    return `${(amount / 100000000).toFixed(2)}亿`
  }
  if (amount >= 1000000) {
    return `${(amount / 1000000).toFixed(2)}M`
  }
  if (amount >= 1000) {
    return `${(amount / 1000).toFixed(2)}K`
  }
  return amount.toFixed(0)
}

const formatDate = (value) => {
  if (!value) {
    return '--'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }
  return date.toLocaleString('zh-CN')
}

const formatReferencePrice = (value) => {
  const amount = Number(value || 0)
  return amount > 0 ? formatMarketPrice(amount) : '--'
}

const formatQuoteDetailPrice = (value) => {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  const amount = Number(value)
  if (!Number.isFinite(amount)) {
    return '--'
  }
  if (amount === 0) {
    return '0.00'
  }
  return formatMarketPrice(amount)
}

const formatReferencePriceSource = (value) => {
  const key = String(value || '').toLowerCase()
  if (key === 'request') return '手动输入'
  if (key === 'broker') return '实时行情'
  if (key === 'quote_snapshot') return '快照兜底'
  if (key === 'snapshot') return '快照'
  return key ? key : '--'
}

const formatFeedbackTime = (value) => {
  return value ? formatDate(value) : '实时或未记录'
}

const scrollToTradeSection = (id) => {
  if (isPhoneLayout.value) {
    const nextSection = ({
      'trade-order': 'order',
      'trade-context': 'context',
      'trade-quote': 'quote',
      'trade-positions': 'positions',
      'trade-orders': 'orders'
    })[id]
    if (nextSection) {
      activeTradeSection.value = nextSection
    }
    document.querySelector('.content')?.scrollTo({
      top: 0,
      behavior: 'smooth'
    })
    return
  }
  if (typeof document === 'undefined') {
    return
  }
  document.getElementById(id)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start'
  })
}

const syncRoutePreset = async () => {
  const nextAction = String(route.query.action || '').trim().toLowerCase()
  if (nextAction === 'buy' || nextAction === 'sell') {
    orderForm.value.action = nextAction
  }

  const nextSymbol = String(route.query.symbol || '').trim().toUpperCase()
  if (nextSymbol && nextSymbol !== String(orderForm.value.symbol || '').trim().toUpperCase()) {
    orderForm.value.symbol = nextSymbol
    await searchSymbol()
  }
}

onMounted(() => {
  loadAccounts()
})

watch(liveQuote, (quote) => {
  if (!quote) {
    return
  }
  const quoteTimestamp = quote.timestamp || quote.pushReceivedAt || quote.updatedAt || ''
  const fallbackTimestamp = currentQuote.value?.timestamp || currentQuote.value?.updatedAt || quotePullFallback.value?.timestamp || ''
  if (toTimestampMs(quoteTimestamp) && toTimestampMs(fallbackTimestamp) > toTimestampMs(quoteTimestamp)) {
    return
  }

  const lastPrice = Number(quote.last_price ?? quote.last_done ?? quote.price ?? 0)
  const prevClose = Number(quote.prev_close ?? quote.prevClose ?? currentQuote.value?.prevClose ?? 0)
  const changePercent = Number(quote.change_percent ?? quote.change_rate ?? quote.changePercent ?? 0)
  const change = prevClose > 0 ? lastPrice - prevClose : 0

  const mergedQuote = normalizeQuote({
    ...(quotePullFallback.value || {}),
    ...currentQuote.value,
    symbol: orderForm.value.symbol,
    price: lastPrice,
    last_price: lastPrice,
    prev_close: prevClose,
    prevClose: prevClose,
    volume: Number(quote.volume ?? currentQuote.value?.volume ?? 0),
    change_percent: changePercent,
    changePercent: changePercent,
    change: change,
    open: Number(quote.open ?? currentQuote.value?.open ?? 0),
    high: Number(quote.high ?? currentQuote.value?.high ?? 0),
    low: Number(quote.low ?? currentQuote.value?.low ?? 0),
    session: quote.session ?? currentQuote.value?.session ?? '',
    source: 'longbridge-push',
    quoteReady: true
  })
  currentQuote.value = mergedQuote
})

watch(() => [route.query.symbol, route.query.action], async () => {
  await syncRoutePreset()
}, { immediate: true })

watch(selectedAccount, async (newValue, oldValue) => {
  if (!newValue || newValue === oldValue) {
    return
  }
  await refreshTradingData()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped lang="scss">
.trading-page {
  padding: 10px;
}

.mobile-trade-command {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
  padding: 18px;
  border-radius: 28px;
  border: 1px solid var(--panel-edge);
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 16%, transparent), transparent 40%),
    var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
}

.mobile-command-copy {
  display: grid;
  gap: 6px;
}

.mobile-command-kicker {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.mobile-command-copy strong {
  color: var(--text-emphasis);
  font-size: 24px;
  line-height: 1.1;
}

.mobile-command-copy p,
.mobile-command-metric small {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mobile-command-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.mobile-command-metric {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
}

.mobile-command-metric span {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mobile-command-metric strong {
  color: var(--text-primary);
  font-size: 18px;
}

.mobile-command-controls,
.mobile-command-jumps {
  display: grid;
  gap: 10px;
}

.mobile-command-controls {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
}

.mobile-account-select {
  width: 100%;
}

.mobile-command-jumps {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mobile-command-jump {
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid var(--control-border);
  border-radius: 16px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  color: var(--text-primary);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.trade-source-strip {
  margin-bottom: 12px;
}

.market-pulse-summary {
  margin-bottom: 12px;
}

.mobile-trade-rail {
  display: none;
}

.content-source-strip {
  margin-bottom: 16px;
}

.summary-card {
  padding: 18px 20px;
  border-radius: 24px;
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-soft), var(--panel-inset);

  span {
    display: block;
    color: var(--text-muted);
    font-size: 12px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  strong {
    display: block;
    margin-top: 10px;
    color: var(--text-primary);
    font-size: 24px;
  }

  p {
    margin: 10px 0 0;
    color: var(--text-secondary);
    line-height: 1.7;
  }
}

.status-card.warning {
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.92), rgba(255, 251, 235, 0.96));
  border-color: rgba(245, 158, 11, 0.22);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.trade-surface-button {
  --el-button-bg-color: color-mix(in srgb, var(--surface-soft) 90%, transparent);
  --el-button-border-color: var(--control-border);
  --el-button-text-color: var(--text-primary);
  --el-button-hover-bg-color: color-mix(in srgb, var(--surface-strong) 88%, transparent);
  --el-button-hover-border-color: var(--border-strong);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-active-bg-color: color-mix(in srgb, var(--surface-strong) 94%, transparent);
  --el-button-active-text-color: var(--text-primary);
}

.trade-search-button,
.trade-submit-button {
  --el-button-text-color: var(--text-primary);
  --el-button-hover-text-color: var(--text-primary);
}

.trade-submit-button {
  --el-button-bg-color: color-mix(in srgb, var(--surface-strong) 82%, var(--accent) 18%);
  --el-button-border-color: color-mix(in srgb, var(--border-strong) 72%, var(--accent));
  --el-button-hover-bg-color: color-mix(in srgb, var(--surface-strong) 68%, var(--accent) 32%);
  --el-button-hover-border-color: color-mix(in srgb, var(--border-strong) 48%, var(--accent));
  --el-button-active-bg-color: color-mix(in srgb, var(--surface-strong) 62%, var(--accent) 38%);
  --el-button-active-border-color: color-mix(in srgb, var(--border-strong) 36%, var(--accent));
}

.trading-page :deep(.el-input-group__append .el-button) {
  --el-button-text-color: var(--text-primary);
  --el-button-bg-color: color-mix(in srgb, var(--surface-strong) 90%, transparent);
  --el-button-border-color: var(--border-strong);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-hover-bg-color: color-mix(in srgb, var(--surface-strong) 78%, var(--accent) 22%);
  --el-button-hover-border-color: var(--border-strong);
  color: var(--text-primary) !important;
  background-color: color-mix(in srgb, var(--surface-strong) 90%, transparent) !important;
  background-image: none !important;
  border-color: var(--border-strong) !important;
}

.trading-page :deep(.el-input-group__append .el-button span) {
  color: var(--text-primary) !important;
  -webkit-text-fill-color: var(--text-primary) !important;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.trading-container {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 12px;
}

.glass-card {
  background: var(--panel-surface);
  border: 1px solid var(--panel-edge);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.market-pulse-hero {
  padding: 2px;
}

.pulse-summary-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 12px;
  align-items: start;
}

.pulse-summary-copy {
  display: grid;
  gap: 12px;
}

.pulse-summary-headline {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px;
  gap: 12px;
  align-items: start;
}

.pulse-summary-headline strong {
  display: block;
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 20px;
}

.pulse-summary-headline p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.pulse-summary-score,
.pulse-mini-card,
.board-status-card {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
}

.pulse-summary-score span,
.pulse-mini-card span,
.board-status-card span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 12px;
}

.pulse-summary-score strong,
.pulse-mini-card strong,
.board-status-card strong {
  color: var(--text-primary);
}

.pulse-summary-score strong {
  color: var(--accent);
  font-size: 24px;
}

.pulse-summary-metrics,
.board-status-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.pulse-benchmarks--compact {
  align-content: start;
}

.market-empty-card {
  min-height: 160px;
}

.market-empty-copy {
  display: flex;
  flex-direction: column;
  gap: 12px;

  h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 20px;
    line-height: 1.2;
  }

  p {
    margin: 0;
    max-width: 760px;
    color: var(--text-secondary);
    line-height: 1.8;
  }
}

.empty-kicker {
  color: var(--text-muted);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.empty-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-context-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.empty-context-item {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);

  span {
    display: block;
    color: var(--text-muted);
    font-size: 12px;
    margin-bottom: 6px;
  }

  strong {
    color: var(--text-primary);
    font-size: 16px;
  }

  p {
    color: var(--text-secondary);
    line-height: 1.7;
  }

  &.wide {
    grid-column: 1 / -1;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.quote-header-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quote-stream-grid,
.content-stream-grid,
.depth-grid {
  display: grid;
  gap: 10px;
}

.quote-stream-grid,
.depth-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.quote-stream-grid--compact {
  gap: 12px;
}

.content-stream-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.depth-panel,
.trade-panel,
.content-column,
.depth-side,
.trade-tape,
.content-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.depth-side,
.trade-tape-row,
.content-card-item {
  padding: 12px;
  border-radius: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--control-border);
}

.depth-title,
.content-column > strong,
.depth-panel > strong,
.trade-panel > strong {
  color: var(--text-primary);
  font-weight: 700;
}

.depth-row,
.trade-tape-row,
.trade-tape-row > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.trade-tape-row,
.content-card-item span {
  color: var(--text-muted);
  font-size: 12px;
}

.trade-tape-row > div {
  flex-direction: column;
  align-items: flex-start;
}

.compact-board-panel > strong {
  margin-bottom: 4px;
}

.content-card-item h4 {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
}

.content-card-item p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.content-card-item a {
  color: var(--accent-strong);
  font-size: 12px;
}

.symbol-shortcuts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: -6px 0 18px;
}

.shortcut-chip {
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
  color: var(--text-secondary);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.shortcut-chip:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.order-summary {
  padding: 12px 14px;
  background: var(--surface-soft);
  border: 1px solid var(--control-border);
  border-radius: 10px;
}

.summary-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--text-secondary);

  strong {
    color: var(--text-primary);
  }
}

.summary-item + .summary-item {
  margin-top: 8px;
}

.amount {
  color: var(--accent);
}

.order-intelligence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 4px;
}

.order-intelligence-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);
  display: grid;
  gap: 6px;
}

.order-intelligence-card.emphasis {
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 14%, transparent), transparent 38%),
    var(--surface-soft);
}

.order-intelligence-card span,
.feedback-kicker,
.feedback-meta-item span,
.mobile-quote-pill span {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.order-intelligence-card strong,
.feedback-meta-item strong,
.mobile-quote-pill strong,
.trade-confirm-sheet h3 {
  color: var(--text-primary);
}

.order-intelligence-card p,
.order-feedback-panel p,
.trade-confirm-sheet p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.order-feedback-panel {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);
  display: grid;
  gap: 14px;
}

.trade-safety-panel {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  display: grid;
  gap: 8px;
}

.trade-safety-panel strong {
  color: var(--text-primary);
}

.trade-safety-panel p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.trade-safety-panel.is-danger {
  border-color: color-mix(in srgb, var(--danger) 38%, var(--control-border));
  background: color-mix(in srgb, var(--danger) 8%, var(--surface-soft));
}

.trade-safety-panel.is-info {
  border-color: color-mix(in srgb, var(--accent) 34%, var(--control-border));
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-soft));
}

.trade-safety-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.order-feedback-panel.success {
  border-color: color-mix(in srgb, var(--success) 30%, var(--control-border));
}

.order-feedback-panel.error {
  border-color: color-mix(in srgb, var(--danger) 34%, var(--control-border));
}

.order-feedback-head,
.trade-confirm-actions,
.mobile-submit-dock {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.feedback-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.feedback-meta-item {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  display: grid;
  gap: 6px;
}

.quantity-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.execution-context {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.context-item {
  padding: 12px;
  background: var(--surface-soft);
  border: 1px solid var(--control-border);
  border-radius: 10px;

  .label {
    display: block;
    margin-bottom: 6px;
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
  }

  p {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.context-item.full {
  grid-column: 1 / -1;
}

.account-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--table-divider);

  &:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .label {
    color: var(--text-secondary);
  }

  .value {
    font-weight: 600;
    color: var(--text-primary);
  }
}

.quote-info {
  .price-main {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    margin-bottom: 20px;
  }

  .current-price {
    font-size: 36px;
    font-weight: 700;
  }

  .sub-change {
    font-size: 15px;
    font-weight: 600;
  }
}

.board-empty-state {
  min-height: 120px;
  display: grid;
  gap: 8px;
  place-items: center;
  align-content: center;
  text-align: center;
  padding: 20px 16px;
  border-radius: 14px;
  border: 1px dashed var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }

  span {
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.board-empty-state--quote {
  min-height: 180px;
}

.mobile-quote-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 18px;
}

.mobile-quote-pill {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);
  display: grid;
  gap: 4px;
}

.quote-details {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.detail-item {
  text-align: center;
  padding: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--control-border);
  border-radius: 10px;

  .label {
    display: block;
    margin-bottom: 4px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .value {
    font-weight: 600;
    color: var(--text-primary);
  }
}

.pulse-benchmarks {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.pulse-benchmark {
  padding: 12px;
  border-radius: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--control-border);
}

.benchmark-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;

  strong {
    color: var(--text-primary);
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
  }
}

.benchmark-meta {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.benchmark-change {
  margin-top: 10px;
  font-size: 20px;
  font-weight: 700;
}

.table-empty-polish {
  min-height: 96px;
  display: grid;
  gap: 8px;
  place-items: center;
  text-align: center;

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }

  &.compact {
    min-height: 84px;
  }
}

.mobile-position-list,
.mobile-order-list {
  display: grid;
  gap: 12px;
}

.mobile-position-card,
.mobile-order-card {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);
}

.mobile-position-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.mobile-position-head strong {
  display: block;
  color: var(--text-primary);
}

.mobile-position-head span {
  color: var(--text-muted);
  font-size: 12px;
}

.mobile-position-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.mobile-position-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.market-panel :deep(.el-table),
.market-panel :deep(.el-table__expanded-cell) {
  background: transparent !important;
}

.market-panel :deep(.el-table th.el-table__cell) {
  background: color-mix(in srgb, var(--surface-muted) 84%, transparent) !important;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--table-divider);
}

.market-panel :deep(.el-table td.el-table__cell) {
  border-bottom: 1px solid var(--table-divider);
}

.market-panel :deep(.el-table__inner-wrapper::before) {
  background-color: transparent;
}

.trading-page :deep(.trade-toggle-group .el-radio-button__inner) {
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
  border-color: var(--control-border);
  color: var(--text-secondary);
  box-shadow: none;
}

.trading-page :deep(.trade-toggle-group .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: color-mix(in srgb, var(--accent) 18%, var(--surface-soft));
  border-color: color-mix(in srgb, var(--accent) 42%, var(--control-border));
  color: var(--text-primary);
  box-shadow: none;
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

.mobile-submit-dock {
  position: sticky;
  bottom: 12px;
  z-index: 30;
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 24px;
  border: 1px solid var(--panel-edge);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--surface-soft) 92%, transparent), color-mix(in srgb, var(--panel-surface) 96%, transparent)),
    var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.mobile-submit-copy {
  display: grid;
  gap: 4px;
}

.mobile-submit-copy span,
.mobile-submit-copy small {
  color: var(--text-secondary);
}

.mobile-submit-copy strong {
  color: var(--text-primary);
  font-size: 20px;
}

.trade-confirm-sheet {
  padding: 20px;
  border-radius: 22px;
  border: 1px solid var(--control-border);
  background: var(--surface-soft);
  display: grid;
  gap: 16px;
}

.trade-confirm-sheet h3 {
  margin: 0;
  font-size: 24px;
}

@media (max-width: 1280px) {
  .pulse-summary-shell,
  .pulse-summary-headline,
  .pulse-summary-metrics {
    grid-template-columns: 1fr;
  }

  .quote-details {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .pulse-benchmarks {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .order-intelligence-grid,
  .mobile-quote-strip {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .trading-container {
    display: flex;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .execution-context,
  .empty-context-grid,
  .board-status-strip,
  .quote-details,
  .pulse-benchmarks,
  .quote-stream-grid,
  .content-stream-grid,
  .depth-grid {
    grid-template-columns: 1fr;
  }

  .trading-page {
    padding: 10px 10px 92px;
  }

  .mobile-trade-rail {
    position: sticky;
    top: 0;
    z-index: 6;
    display: block;
    padding: 4px 0 14px;
    margin-bottom: 4px;
  }

  .header-actions :deep(.el-select) {
    width: 100%;
  }

  .mobile-command-metrics,
  .mobile-command-controls,
  .mobile-command-jumps {
    grid-template-columns: 1fr;
  }

  .feedback-meta-grid {
    grid-template-columns: 1fr;
  }

  .mobile-submit-dock {
    flex-direction: column;
    align-items: stretch;
  }

  .mobile-submit-dock .el-button {
    width: 100%;
  }
}
</style>
