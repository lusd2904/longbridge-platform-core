<template>
  <div class="settings-page">
    <PageHero
      title="系统设置"
      :chips="settingsHeroChips"
      :metrics="settingsHeroMetrics"
    >
      <template #actions>
        <el-button class="settings-secondary-button" @click="refreshLogs(false)">
          <el-icon><Refresh /></el-icon> 同步日志
        </el-button>
        <el-button type="primary" @click="saveAISettings">保存 AI 设置</el-button>
      </template>
    </PageHero>

    <MetricStrip class="settings-overview-strip" :items="settingsOverviewItems" />

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeTab"
      class="mobile-settings-rail"
      label="系统设置分段"
      :items="settingsMobileSections"
    />

    <el-tabs v-model="activeTab" type="border-card" class="settings-tabs">
      <el-tab-pane label="基础设置" name="basic" lazy>
        <div class="settings-tab-panel">
          <div class="settings-section-stack">
            <section class="settings-section-card">
              <SectionCardHeader title="基础设置" />
              <el-form :model="basicSettings" label-width="150px" class="settings-form">
                <el-form-item label="系统名称">
                  <el-input v-model="basicSettings.systemName" />
                </el-form-item>
                <el-form-item label="默认市场">
                  <el-select v-model="basicSettings.defaultMarket" style="width: 100%">
                    <el-option label="美股" value="US" />
                    <el-option label="A股" value="CN" />
                    <el-option label="港股" value="HK" />
                  </el-select>
                </el-form-item>
                <el-form-item label="默认货币">
                  <el-select v-model="basicSettings.defaultCurrency" style="width: 100%">
                    <el-option label="美元 (USD)" value="USD" />
                    <el-option label="人民币 (CNY)" value="CNY" />
                    <el-option label="港币 (HKD)" value="HKD" />
                  </el-select>
                </el-form-item>
                <el-form-item label="语言">
                  <el-select v-model="basicSettings.language" style="width: 100%">
                    <el-option label="简体中文" value="zh-CN" />
                    <el-option label="繁体中文" value="zh-TW" />
                    <el-option label="English" value="en" />
                  </el-select>
                </el-form-item>
                <el-form-item label="时区">
                  <el-select v-model="basicSettings.timezone" style="width: 100%">
                    <el-option label="北京时间 (UTC+8)" value="Asia/Shanghai" />
                    <el-option label="纽约时间 (UTC-5)" value="America/New_York" />
                    <el-option label="伦敦时间 (UTC+0)" value="Europe/London" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveBasicSettings">保存基础设置</el-button>
                </el-form-item>
              </el-form>
            </section>

            <section class="settings-section-card">
              <SectionCardHeader
                title="通知偏好"
                :badge="notificationSettings.enabled ? '已开启' : '已关闭'"
                :badge-type="notificationSettings.enabled ? 'success' : 'info'"
              />
              <el-form :model="notificationSettings" label-width="150px" class="settings-form">
                <el-form-item label="启用通知">
                  <el-switch v-model="notificationSettings.enabled" />
                </el-form-item>
                <el-form-item label="交易通知">
                  <el-checkbox-group v-model="notificationSettings.tradeNotifications">
                    <el-checkbox value="order_filled">订单成交</el-checkbox>
                    <el-checkbox value="order_cancelled">订单取消</el-checkbox>
                    <el-checkbox value="stop_loss_triggered">止损触发</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="风控通知">
                  <el-checkbox-group v-model="notificationSettings.riskNotifications">
                    <el-checkbox value="risk_alert">风险预警</el-checkbox>
                    <el-checkbox value="drawdown_warning">回撤警告</el-checkbox>
                    <el-checkbox value="position_limit">仓位限制</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="通知方式">
                  <el-checkbox-group v-model="notificationSettings.channels">
                    <el-checkbox value="email">邮件</el-checkbox>
                    <el-checkbox value="sms">短信</el-checkbox>
                    <el-checkbox value="push">推送</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveNotificationSettings">保存通知设置</el-button>
                </el-form-item>
              </el-form>
            </section>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="AI设置" name="ai" lazy>
        <div class="settings-tab-panel">
          <SectionCardHeader
            title="AI 设置"
            :badge="modelCatalogBadge"
            badge-type="success"
          >
            <template #actions>
              <el-button class="settings-secondary-button" @click="handleTestAIConnection">测试连接</el-button>
            </template>
          </SectionCardHeader>

          <el-alert
            class="ai-runtime-alert"
            type="info"
            :closable="false"
            show-icon
            :title="aiRuntimeSummaryTitle"
            :description="aiRuntimeSummaryDescription"
          />

          <div class="ai-layout">
            <el-form :model="aiSettings" label-width="160px" class="settings-form ai-form">
            <el-form-item label="服务商">
              <el-select v-model="aiSettings.provider" style="width: 100%">
                <el-option label="Sub2API / OpenAI 兼容" value="nvidia" />
                <el-option label="混合路由" value="hybrid" />
                <el-option label="本地 Ollama" value="ollama" />
              </el-select>
            </el-form-item>
            <el-form-item label="回退服务商">
              <el-select v-model="aiSettings.fallbackProvider" style="width: 100%">
                <el-option label="本地 Ollama" value="ollama" />
                <el-option label="Sub2API / OpenAI 兼容" value="nvidia" />
                <el-option label="不启用回退" value="" />
              </el-select>
            </el-form-item>
            <el-form-item label="API Base URL">
              <el-input v-model="aiSettings.baseUrl" placeholder="https://lucen.cc/v1" />
            </el-form-item>
            <el-form-item v-if="aiSettings.provider === 'ollama' || aiSettings.provider === 'hybrid'" label="本地模型地址">
              <el-input v-model="aiSettings.localUrl" placeholder="http://127.0.0.1:11434/api/generate" />
            </el-form-item>
            <el-form-item v-if="aiSettings.provider === 'ollama' || aiSettings.provider === 'hybrid'" label="本地默认模型">
              <el-input v-model="aiSettings.localModel" placeholder="gemma3:12b" />
            </el-form-item>
            <el-form-item label="默认模型">
              <el-select v-model="aiSettings.model" filterable style="width: 100%">
                <el-option
                  v-for="model in selectableModelOptions"
                  :key="model.id"
                  :label="`${model.alias} · ${model.id}`"
                  :value="model.id"
                  :disabled="model.available === false"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="脉冲扫描模型">
              <el-select v-model="aiSettings.scanPulseModel" filterable style="width: 100%">
                <el-option v-for="model in fastModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="风险扫描模型">
              <el-select v-model="aiSettings.scanRiskModel" filterable style="width: 100%">
                <el-option v-for="model in fastModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="逐股趋势扫描模型">
              <el-select v-model="aiSettings.trendBatchModel" filterable style="width: 100%">
                <el-option v-for="model in selectableModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="终审扫描模型">
              <el-select v-model="aiSettings.scanFinalModel" filterable style="width: 100%">
                <el-option v-for="model in selectableModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="扫描质量档位">
              <el-select v-model="aiSettings.scanReasoningEffort" style="width: 100%">
                <el-option label="最高质量" value="high" />
                <el-option label="标准质量" value="medium" />
                <el-option label="低延迟" value="low" />
              </el-select>
            </el-form-item>
            <el-form-item label="推荐快评模型">
              <el-select v-model="aiSettings.recommendBriefModel" filterable style="width: 100%">
                <el-option v-for="model in fastModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="推荐总结模型">
              <el-select v-model="aiSettings.recommendSummaryModel" filterable style="width: 100%">
                <el-option v-for="model in selectableModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="视觉模型">
              <el-select v-model="aiSettings.visionModel" filterable style="width: 100%">
                <el-option v-for="model in visionModelOptions" :key="model.id" :label="modelLabel(model)" :value="model.id" :disabled="model.available === false" />
              </el-select>
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="aiSettings.apiKey" placeholder="使用当前 sub2api / OpenAI 兼容密钥" show-password />
            </el-form-item>
            <el-form-item v-if="aiSettings.provider === 'ollama' || aiSettings.provider === 'hybrid'" label="本地超时时间">
              <el-input-number v-model="aiSettings.localTimeout" :min="10" :step="5" style="width: 220px" />
              <span class="inline-tip">单位：秒，本地模型用于低时延扫描和云端失败兜底</span>
            </el-form-item>
            <el-form-item label="最大输出长度">
              <el-slider v-model="aiSettings.maxTokens" :min="100" :max="2400" :step="100" show-input />
            </el-form-item>
            <el-form-item label="温度参数">
              <el-slider v-model="aiSettings.temperature" :min="0" :max="1" :step="0.1" show-input />
            </el-form-item>
            <el-form-item label="推荐刷新间隔">
              <el-input-number v-model="aiSettings.recommendationRefreshInterval" :min="900" :step="300" style="width: 220px" />
              <span class="inline-tip">单位：秒，后台定时任务将按此周期刷新推荐</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveAISettings">保存设置</el-button>
              <el-button class="settings-secondary-button" @click="handleTestAIConnection">测试连接</el-button>
            </el-form-item>
            </el-form>

            <div class="model-catalog">
              <div class="catalog-head">
                <h3>模型清单</h3>
                <span>{{ modelCatalogSummary }}</span>
              </div>
              <div class="provider-plan">
                <div v-for="(item, key) in providerPlan" :key="key" class="provider-plan-card">
                  <strong>{{ providerNames[key] || key }}</strong>
                  <span>主通道：{{ providerText(item.primary) }}</span>
                  <small>回退：{{ item.fallbacks?.length ? item.fallbacks.map(providerText).join(' / ') : '无' }}</small>
                </div>
              </div>
              <div class="catalog-grid">
                <article v-for="model in displayModelOptions" :key="model.id" class="model-card">
                  <div class="model-top">
                  <strong>{{ model.alias }}</strong>
                  <div class="model-tags">
                      <el-tag size="small">{{ modelLatencyText(model.latency) }}</el-tag>
                      <el-tag size="small" :type="model.available === false ? 'info' : 'success'">
                        {{ model.available === false ? '当前不可直连' : '可用' }}
                      </el-tag>
                    </div>
                  </div>
                  <p>{{ model.id }}</p>
                  <small v-if="model.availabilityNote" class="availability-note">{{ model.availabilityNote }}</small>
                  <div class="model-meta">
                    <span>{{ model.provider }}</span>
                    <span v-for="tag in model.best_for || []" :key="tag">{{ tag }}</span>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="日志/数据管理" name="operations" lazy>
        <div class="settings-tab-panel">
          <section class="settings-section-card">
            <SectionCardHeader title="系统日志" :badge="`${filteredLogs.length} 条`">
              <template #actions>
                <el-button class="settings-secondary-button" @click="refreshLogs">
                  <el-icon><Refresh /></el-icon> 刷新日志
                </el-button>
              </template>
            </SectionCardHeader>
            <div class="logs-header">
              <el-radio-group v-model="logLevel" size="small" @change="refreshLogs(false)">
                <el-radio-button value="all">全部</el-radio-button>
                <el-radio-button value="info">信息</el-radio-button>
                <el-radio-button value="warning">警告</el-radio-button>
                <el-radio-button value="error">错误</el-radio-button>
              </el-radio-group>
            </div>
            <div class="logs-content">
              <div v-for="log in filteredLogs" :key="log.id" class="log-item" :class="log.level">
                <span class="log-time">{{ log.time }}</span>
                <el-tag :type="getLogType(log.level)" size="small">{{ log.level }}</el-tag>
                <el-tag size="small" effect="plain">{{ log.module || 'system' }}</el-tag>
                <span class="log-message">{{ log.message }}</span>
              </div>
            </div>
          </section>

          <section class="settings-section-card">
            <SectionCardHeader title="数据管理" />

            <div class="data-grid">
              <section class="data-section">
                <h4>数据备份</h4>
                <div class="section-actions">
                  <el-button type="primary" @click="backupData">
                    <el-icon><Download /></el-icon> 立即备份
                  </el-button>
                  <el-button class="settings-secondary-button" @click="scheduleBackup">设置自动备份</el-button>
                </div>
              </section>

              <section class="data-section">
                <h4>数据恢复</h4>
                <el-upload
                  action="/api/upload"
                  :auto-upload="false"
                  :on-change="handleBackupFile"
                  accept=".json,.sql"
                >
                  <el-button type="primary">
                    <el-icon><Upload /></el-icon> 选择备份文件
                  </el-button>
                </el-upload>
              </section>

              <section class="data-section">
                <h4>数据清理</h4>
                <el-form :inline="true">
                  <el-form-item label="清理范围">
                    <el-select v-model="cleanupRange" placeholder="选择范围">
                      <el-option label="30天前" value="30" />
                      <el-option label="90天前" value="90" />
                      <el-option label="1年前" value="365" />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button type="danger" @click="cleanupData">清理数据</el-button>
                  </el-form-item>
                </el-form>
              </section>
            </div>

            <section v-if="showTradeOutboxAdmin" class="outbox-admin-panel">
              <SectionCardHeader
                title="Trade Outbox 治理"
                :badge="tradeOutboxStatusText"
                :badge-type="tradeOutboxStatusTone === 'success' ? 'success' : 'info'"
              >
                <template #actions>
                  <div class="section-actions">
                    <el-button class="settings-secondary-button" :loading="tradeOutboxLoading" @click="refreshTradeOutbox()">
                      <el-icon><Refresh /></el-icon> 刷新
                    </el-button>
                    <el-button type="warning" :loading="tradeOutboxActionLoading" @click="runTradeOutboxRepair">
                      运行修复
                    </el-button>
                  </div>
                </template>
              </SectionCardHeader>

              <el-alert
                v-if="tradeOutboxAvailabilityMessage"
                class="outbox-alert"
                type="info"
                :closable="false"
                show-icon
                :title="tradeOutboxAvailabilityMessage"
              />

              <div class="outbox-stats">
                <article v-for="item in tradeOutboxCards" :key="item.label" class="outbox-stat-card">
                  <span class="stat-label">{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                  <small>{{ item.hint }}</small>
                </article>
              </div>

              <div class="outbox-toolbar">
                <div class="outbox-toolbar-group">
                  <el-select v-model="tradeOutboxFilter.status" :disabled="!tradeOutboxCanOperate" style="width: 160px">
                    <el-option label="全部状态" value="" />
                    <el-option label="待投递" value="pending" />
                    <el-option label="投递失败" value="failed" />
                    <el-option label="已发布" value="published" />
                    <el-option label="死信" value="dead_letter" />
                  </el-select>
                  <el-input
                    v-model="tradeOutboxFilter.sagaId"
                    :disabled="!tradeOutboxSupportsEventData"
                    clearable
                    placeholder="按 Saga ID 过滤"
                    style="width: 260px"
                  />
                  <el-input
                    v-model="tradeOutboxFilter.eventType"
                    :disabled="!tradeOutboxSupportsEventData"
                    clearable
                    placeholder="按事件类型过滤"
                    style="width: 240px"
                  />
                  <el-input-number v-model="tradeOutboxFilter.limit" :disabled="!tradeOutboxCanOperate" :min="10" :max="200" :step="10" style="width: 140px" />
                  <el-switch v-model="tradeOutboxFilter.includePayload" :disabled="!tradeOutboxSupportsEventData" />
                  <span class="inline-tip">显示 payload</span>
                </div>
                <div class="outbox-toolbar-group">
                  <el-button type="primary" :disabled="!tradeOutboxCanOperate" :loading="tradeOutboxLoading" @click="refreshTradeOutbox()">
                    应用筛选
                  </el-button>
                </div>
              </div>

              <div class="outbox-panels">
                <section class="outbox-panel">
                  <div class="outbox-panel-head">
                    <div>
                      <h5>事件列表</h5>
                      <p>
                        {{ tradeOutboxSupportsEventData ? `${tradeOutboxEvents.length} 条记录` : '当前环境未开放事件明细接口' }}
                      </p>
                    </div>
                    <div class="outbox-table-actions">
                      <el-button
                        type="warning"
                        plain
                        size="small"
                        :disabled="!tradeOutboxSupportsEventData || !selectedReplayableEventIds.length || tradeOutboxActionLoading"
                        @click="requeueSelectedTradeOutboxEvents"
                      >
                        重放所选事件
                      </el-button>
                      <el-button
                        type="danger"
                        plain
                        size="small"
                        :disabled="!tradeOutboxSupportsEventData || !selectedDeadLetterEventIds.length || tradeOutboxActionLoading"
                        @click="purgeSelectedTradeDeadLetters"
                      >
                        清理所选死信
                      </el-button>
                    </div>
                  </div>

                  <el-table
                    :data="tradeOutboxEvents"
                    v-loading="tradeOutboxLoading"
                    style="width: 100%"
                    max-height="420"
                    empty-text="当前环境未返回事件列表"
                    @selection-change="handleTradeOutboxEventSelectionChange"
                  >
                    <el-table-column v-if="tradeOutboxSupportsEventData" type="selection" width="48" />
                    <el-table-column prop="eventId" label="事件 ID" min-width="180" show-overflow-tooltip />
                    <el-table-column prop="sagaId" label="Saga ID" min-width="180" show-overflow-tooltip />
                    <el-table-column prop="eventType" label="事件类型" min-width="180" show-overflow-tooltip />
                    <el-table-column prop="publishStatus" label="状态" width="110">
                      <template #default="{ row }">
                        <el-tag size="small" :type="getOutboxStatusTagType(row.publishStatus)">
                          {{ getOutboxStatusText(row.publishStatus) }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="retryCount" label="重试" width="80" />
                    <el-table-column prop="deadLetterAt" label="死信时间" width="170" />
                    <el-table-column prop="createdAt" label="创建时间" width="170" />
                    <el-table-column v-if="tradeOutboxFilter.includePayload" label="Payload" min-width="260">
                      <template #default="{ row }">
                        <code class="payload-preview">{{ formatOutboxPayload(row.payload) }}</code>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="180" fixed="right">
                      <template #default="{ row }">
                        <el-button
                          v-if="tradeOutboxSupportsEventData && ['failed', 'dead_letter'].includes(row.publishStatus)"
                          type="warning"
                          size="small"
                          link
                          @click="requeueTradeOutboxEvent(row)"
                        >
                          重放
                        </el-button>
                        <el-button
                          v-if="tradeOutboxSupportsEventData && row.publishStatus === 'dead_letter'"
                          type="danger"
                          size="small"
                          link
                          @click="purgeTradeDeadLetterRow(row)"
                        >
                          清理
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </section>

                <section class="outbox-panel">
                  <div class="outbox-panel-head">
                    <div>
                      <h5>Saga 聚合</h5>
                      <p>
                        {{ tradeOutboxSupportsSagaData ? `${tradeOutboxSagas.length} 条 Saga` : '当前环境未开放 Saga 聚合接口' }}
                      </p>
                    </div>
                    <div class="outbox-table-actions">
                      <el-button
                        type="warning"
                        plain
                        size="small"
                        :disabled="!tradeOutboxSupportsSagaData || !selectedTradeOutboxSagaIds.length || tradeOutboxActionLoading"
                        @click="requeueSelectedTradeOutboxSagas"
                      >
                        按 Saga 重放
                      </el-button>
                      <el-button
                        type="danger"
                        plain
                        size="small"
                        :disabled="!tradeOutboxSupportsSagaData || !selectedDeadLetterSagaIds.length || tradeOutboxActionLoading"
                        @click="purgeSelectedTradeDeadLettersBySaga"
                      >
                        按 Saga 清理死信
                      </el-button>
                    </div>
                  </div>

                  <el-table
                    :data="tradeOutboxSagas"
                    v-loading="tradeOutboxLoading"
                    style="width: 100%"
                    max-height="420"
                    empty-text="当前环境未返回 Saga 聚合数据"
                    @selection-change="handleTradeOutboxSagaSelectionChange"
                  >
                    <el-table-column v-if="tradeOutboxSupportsSagaData" type="selection" width="48" />
                    <el-table-column prop="sagaId" label="Saga ID" min-width="220" show-overflow-tooltip />
                    <el-table-column prop="eventCount" label="事件数" width="90" />
                    <el-table-column prop="publishedCount" label="已发布" width="90" />
                    <el-table-column prop="failedCount" label="失败" width="80" />
                    <el-table-column prop="deadLetterCount" label="死信" width="80" />
                    <el-table-column prop="lastCreatedAt" label="最近创建" width="170" />
                    <el-table-column label="操作" width="180" fixed="right">
                      <template #default="{ row }">
                        <el-button
                          v-if="tradeOutboxSupportsEventData"
                          type="primary"
                          size="small"
                          link
                          @click="inspectSagaEvents(row)"
                        >
                          查看事件
                        </el-button>
                        <el-button
                          v-if="tradeOutboxSupportsSagaData && (row.deadLetterCount > 0 || row.failedCount > 0)"
                          type="warning"
                          size="small"
                          link
                          @click="requeueTradeOutboxSaga(row)"
                        >
                          重放
                        </el-button>
                        <el-button
                          v-if="tradeOutboxSupportsSagaData && row.deadLetterCount > 0"
                          type="danger"
                          size="small"
                          link
                          @click="purgeTradeDeadLettersForSaga(row)"
                        >
                          清理
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </section>
              </div>
            </section>
          </section>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh, Upload } from '@element-plus/icons-vue'
import { getAIModels, testAIConnection as testAIConnectionRequest } from '../api/analysis.js'
import { getSystemLogs, getSystemSettings, updateSystemSettings } from '../api/platform.js'
import {
  getTradeOutboxEvents,
  getTradeOutboxHealth,
  getTradeOutboxSagas,
  purgeTradeDeadLetters,
  purgeTradeDeadLettersBySaga,
  repairTradeOutbox,
  requeueTradeOutboxEvents,
  requeueTradeOutboxSagas
} from '../api/trade.js'
import { getConfig, updateConfig } from '../api/user.js'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { getAccess, isAdmin } from '../utils/auth.js'
import { getStoredSystemName } from '../utils/api.js'
import {
  resolveTradeOutboxAdminPayload,
  supportsTradeOutboxAdminDetails
} from '../utils/tradeOutboxAdmin.js'

const { isPhoneLayout } = useAdaptiveLayout()
const activeTab = ref('basic')
const fallbackSystemName = getStoredSystemName()

const basicSettings = ref({
  systemName: fallbackSystemName,
  defaultMarket: 'US',
  defaultCurrency: 'USD',
  language: 'zh-CN',
  timezone: 'Asia/Shanghai'
})

const OPENAI_COMPAT_BASE_URL = 'https://lucen.cc/v1'
const DEFAULT_AI_SETTINGS = {
  provider: 'nvidia',
  fallbackProvider: '',
  baseUrl: OPENAI_COMPAT_BASE_URL,
  localUrl: 'http://127.0.0.1:11434/api/generate',
  localModel: 'gemma3:12b',
  model: 'gpt-5.5',
  scanPulseModel: 'gpt-5.4',
  scanRiskModel: 'gpt-5.4',
  trendBatchModel: 'gpt-5.4',
  scanFinalModel: 'gpt-5.5',
  scanReasoningEffort: 'high',
  recommendBriefModel: 'gpt-5.4',
  recommendSummaryModel: 'gpt-5.5',
  visionModel: 'gpt-5.4',
  apiKey: '',
  localTimeout: 45,
  maxTokens: 600,
  temperature: 0.2,
  recommendationRefreshInterval: 1800
}

const aiSettings = ref({
  ...DEFAULT_AI_SETTINGS
})

const modelOptions = ref([])
const defaultModelPlan = ref({})
const providerInfo = ref('nvidia')
const providerPlan = ref({})
const notificationSettings = ref({
  enabled: true,
  tradeNotifications: ['order_filled', 'stop_loss_triggered'],
  riskNotifications: ['risk_alert', 'drawdown_warning'],
  channels: ['email', 'push']
})

const cleanupRange = ref('90')
const logLevel = ref('all')
const logs = ref([])
const tradeOutboxLoading = ref(false)
const tradeOutboxActionLoading = ref(false)
const tradeOutboxSummary = ref({
  status: 'unknown',
  eventStream: {},
  outbox: {},
  kafka: {}
})
const tradeOutboxEvents = ref([])
const tradeOutboxSagas = ref([])
const selectedTradeOutboxEvents = ref([])
const selectedTradeOutboxSagas = ref([])
const tradeOutboxFilter = ref({
  status: '',
  sagaId: '',
  eventType: '',
  limit: 20,
  includePayload: false
})
const tradeOutboxMode = ref('full')
const tradeOutboxAvailabilityMessage = ref('')
const tradeOutboxAvailability = ref({
  health: false,
  events: false,
  sagas: false
})

const marketLabelMap = {
  US: '美股',
  CN: 'A股',
  HK: '港股'
}

const currencyLabelMap = {
  USD: '美元',
  CNY: '人民币',
  HKD: '港币'
}

const languageLabelMap = {
  'zh-CN': '简体中文',
  'zh-TW': '繁体中文',
  en: 'English'
}

const filteredLogs = computed(() => {
  if (logLevel.value === 'all') return logs.value
  return logs.value.filter((log) => log.level === logLevel.value)
})

const showTradeOutboxAdmin = computed(() => Boolean(getAccess()?.canManageTasks) || isAdmin())
const tradeOutboxStatusText = computed(() => {
  if (!showTradeOutboxAdmin.value) {
    return '标准设置'
  }
  if (tradeOutboxMode.value === 'health-only') {
    return '治理只读'
  }
  if (tradeOutboxMode.value === 'partial') {
    return '治理降级'
  }
  return '治理可用'
})
const tradeOutboxStatusTone = computed(() => {
  if (!showTradeOutboxAdmin.value) {
    return 'info'
  }
  if (tradeOutboxMode.value === 'full') {
    return 'success'
  }
  if (tradeOutboxMode.value === 'partial') {
    return 'warning'
  }
  return 'info'
})
const settingsHeroChips = computed(() => ([
  {
    text: marketLabelMap[basicSettings.value.defaultMarket] || basicSettings.value.defaultMarket || '--',
    tone: 'info'
  },
  {
    text: notificationSettings.value.enabled ? '通知已开启' : '通知已关闭',
    tone: notificationSettings.value.enabled ? 'success' : 'warning'
  },
  {
    text: tradeOutboxStatusText.value,
    tone: tradeOutboxStatusTone.value
  }
]))
const settingsHeroMetrics = computed(() => ([
  {
    label: '系统名称',
    value: basicSettings.value.systemName || fallbackSystemName,
    note: `${languageLabelMap[basicSettings.value.language] || basicSettings.value.language} · ${currencyLabelMap[basicSettings.value.defaultCurrency] || basicSettings.value.defaultCurrency}`
  },
  {
    label: 'AI 路由',
    value: providerLabel.value,
    note: aiSettings.value.model || '待选择默认模型'
  },
  {
    label: '通知通道',
    value: `${notificationSettings.value.channels.length} 个`,
    note: notificationSettings.value.enabled ? '交易与风控提醒已启用' : '当前不会主动推送'
  },
  {
    label: '运行日志',
    value: `${filteredLogs.value.length} 条`,
    note: logLevel.value === 'all' ? '当前过滤：全部级别' : `当前过滤：${logLevel.value}`
  }
]))
const settingsOverviewItems = computed(() => ([
  {
    label: '默认市场',
    value: marketLabelMap[basicSettings.value.defaultMarket] || basicSettings.value.defaultMarket || '--',
    note: basicSettings.value.timezone || '未设置'
  },
  {
    label: '模型目录',
    value: modelCatalogCountLabel.value,
    note: modelCatalogSourceText.value
  },
  {
    label: '推荐节奏',
    value: `${Math.round(Number(aiSettings.value.recommendationRefreshInterval || 0) / 60)} 分钟`,
    note: '后台推荐刷新周期'
  },
  {
    label: 'API Base URL',
    value: aiSettings.value.baseUrl || SUB2API_BASE_URL,
    note: '当前 sub2api 本地网关'
  },
  {
    label: 'Outbox',
    value: tradeOutboxStatusText.value,
    tone: tradeOutboxStatusTone.value,
    note: showTradeOutboxAdmin.value ? (tradeOutboxAvailabilityMessage.value || '事件与 Saga 接口已接通') : '仅管理员可见'
  }
]))
const settingsMobileSections = computed(() => ([
  { value: 'basic', label: '基础', note: '系统参数' },
  { value: 'ai', label: 'AI', note: providerLabel.value },
  { value: 'operations', label: '运维', note: '日志与数据' }
]))

const outboxRuntimeStatus = computed(() => tradeOutboxSummary.value?.outbox || {})
const outboxEventStreamStatus = computed(() => tradeOutboxSummary.value?.eventStream || {})
const tradeOutboxSupportsEventData = computed(() => tradeOutboxAvailability.value.events)
const tradeOutboxSupportsSagaData = computed(() => tradeOutboxAvailability.value.sagas)
const tradeOutboxCanOperate = computed(() => tradeOutboxSupportsEventData.value || tradeOutboxSupportsSagaData.value)

const tradeOutboxCards = computed(() => ([
  {
    label: '服务状态',
    value: tradeOutboxSummary.value?.status || 'unknown',
    hint: `事件流 ${outboxEventStreamStatus.value?.status || 'unknown'}`
  },
  {
    label: '待投递',
    value: Number(outboxRuntimeStatus.value?.pendingCount || 0),
    hint: '等待 relay 投递'
  },
  {
    label: '失败事件',
    value: Number(outboxRuntimeStatus.value?.failedCount || 0),
    hint: '可继续修复或重放'
  },
  {
    label: '死信事件',
    value: Number(outboxRuntimeStatus.value?.deadLetterCount || 0),
    hint: '需人工处理或清理'
  },
  {
    label: '已发布',
    value: Number(outboxRuntimeStatus.value?.publishedCount || 0),
    hint: outboxRuntimeStatus.value?.lastPublishAt || '暂无最新发布时间'
  },
  {
    label: '最近修复',
    value: outboxRuntimeStatus.value?.lastRepairAt || '--',
    hint: 'repair_state 最近执行时间'
  }
]))

const selectedReplayableEventIds = computed(() => (
  selectedTradeOutboxEvents.value
    .filter((item) => ['failed', 'dead_letter'].includes(item.publishStatus))
    .map((item) => item.eventId)
))

const selectedDeadLetterEventIds = computed(() => (
  selectedTradeOutboxEvents.value
    .filter((item) => item.publishStatus === 'dead_letter')
    .map((item) => item.eventId)
))

const selectedTradeOutboxSagaIds = computed(() => (
  selectedTradeOutboxSagas.value
    .map((item) => item.sagaId)
    .filter(Boolean)
))

const selectedDeadLetterSagaIds = computed(() => (
  selectedTradeOutboxSagas.value
    .filter((item) => Number(item.deadLetterCount || 0) > 0)
    .map((item) => item.sagaId)
))

const cloudModelOptions = computed(() => {
  const pool = displayModelOptions.value.filter((item) => item.provider !== 'ollama')
  const available = pool.filter((item) => item.available !== false)
  return available.length ? available : pool
})

const configuredModelIds = computed(() => {
  const ids = [
    aiSettings.value.model,
    aiSettings.value.scanPulseModel,
    aiSettings.value.scanRiskModel,
    aiSettings.value.trendBatchModel,
    aiSettings.value.scanFinalModel,
    aiSettings.value.recommendBriefModel,
    aiSettings.value.recommendSummaryModel,
    aiSettings.value.visionModel,
    aiSettings.value.localModel
  ].map((item) => String(item || '').trim()).filter(Boolean)
  return [...new Set(ids)]
})

const fallbackModelOptions = computed(() => {
  return configuredModelIds.value.map((id) => ({
    id,
    alias: id,
    provider: id.includes(':') ? 'ollama' : 'sub2api',
    latency: id === 'gpt-5.5' ? 'medium' : 'fast',
    best_for: ['已配置模型'],
    available: true,
    availabilityNote: '模型目录接口未返回列表，当前展示已保存配置。',
    official: true
  }))
})

const displayModelOptions = computed(() => (
  modelOptions.value.length ? modelOptions.value : fallbackModelOptions.value
))

const modelCatalogCountLabel = computed(() => `${displayModelOptions.value.length} 个`)
const modelCatalogSourceText = computed(() => (
  modelOptions.value.length ? '云端与本地通道路由清单' : '模型目录接口为空，已回退为当前配置模型'
))
const modelCatalogBadge = computed(() => (
  modelOptions.value.length ? modelCatalogCountLabel.value : '已配置模型'
))
const modelCatalogSummary = computed(() => (
  `${modelOptions.value.length ? modelCatalogCountLabel.value : '已配置模型'} · 当前通道 ${providerLabel.value}`
))
const aiRuntimeSummaryTitle = computed(() => (
  `当前 AI 网关：${aiSettings.value.baseUrl || SUB2API_BASE_URL}`
))
const aiRuntimeSummaryDescription = computed(() => (
  `默认使用 ${aiSettings.value.model || DEFAULT_AI_SETTINGS.model}，低延迟模型优先 ${aiSettings.value.scanPulseModel || DEFAULT_AI_SETTINGS.scanPulseModel} / ${aiSettings.value.scanRiskModel || DEFAULT_AI_SETTINGS.scanRiskModel}。`
))

const fastModelOptions = computed(() => {
  return cloudModelOptions.value.filter((item) => ['fast', 'medium'].includes(item.latency))
})

const visionModelOptions = computed(() => {
  const pool = cloudModelOptions.value
  return pool.filter((item) => item.id.includes('vision') || item.id.includes('vl'))
})

const selectableModelOptions = computed(() => {
  return cloudModelOptions.value
})

const providerLabel = computed(() => ({
  nvidia: 'Sub2API / OpenAI 兼容',
  ollama: 'Ollama',
  hybrid: 'Hybrid Router',
  openai: 'OpenAI Compatible'
}[aiSettings.value.provider || providerInfo.value] || aiSettings.value.provider || providerInfo.value || 'unknown'))

const providerNames = {
  pulse: '脉冲层',
  trendBatch: '逐股趋势',
  risk: '风险层',
  final: '终审层',
  recommendBrief: '快评',
  recommendSummary: '总结',
  vision: '视觉',
  general: '通用'
}

const providerText = (provider) => ({
  nvidia: 'Sub2API',
  ollama: 'Ollama',
  hybrid: 'Hybrid'
}[provider] || provider || 'unknown')

const modelLatencyText = (latency) => ({
  fast: '低延迟',
  medium: '均衡速度',
  slow: '深度模型',
  batch: '批量任务'
}[latency] || '均衡速度')

const modelLabel = (model) => `${model.alias} · ${model.id}`

const getOutboxStatusTagType = (status) => ({
  pending: 'info',
  failed: 'warning',
  dead_letter: 'danger',
  published: 'success'
}[status] || 'info')

const getOutboxStatusText = (status) => ({
  pending: '待投递',
  failed: '失败',
  dead_letter: '死信',
  published: '已发布'
}[status] || status || '--')

const formatOutboxPayload = (payload) => {
  if (!payload) {
    return '--'
  }
  try {
    const text = typeof payload === 'string' ? payload : JSON.stringify(payload)
    return text.length > 220 ? `${text.slice(0, 220)}...` : text
  } catch {
    return String(payload)
  }
}

const firstModelId = (items) => items?.[0]?.id || ''

const ensureModelSelection = (currentValue, items, fallbackValue) => {
  const ids = new Set((items || []).map((item) => item.id))
  if (currentValue && ids.has(currentValue)) {
    return currentValue
  }
  if (fallbackValue && ids.has(fallbackValue)) {
    return fallbackValue
  }
  return firstModelId(items) || currentValue || fallbackValue || ''
}

const syncModelSelections = () => {
  aiSettings.value.model = ensureModelSelection(
    aiSettings.value.model,
    selectableModelOptions.value,
    defaultModelPlan.value.general?.id
  )
  aiSettings.value.scanPulseModel = ensureModelSelection(
    aiSettings.value.scanPulseModel,
    fastModelOptions.value,
    defaultModelPlan.value.pulse?.id
  )
  aiSettings.value.scanRiskModel = ensureModelSelection(
    aiSettings.value.scanRiskModel,
    fastModelOptions.value,
    defaultModelPlan.value.risk?.id
  )
  aiSettings.value.trendBatchModel = ensureModelSelection(
    aiSettings.value.trendBatchModel,
    selectableModelOptions.value,
    defaultModelPlan.value.trendBatch?.id
  )
  aiSettings.value.scanFinalModel = ensureModelSelection(
    aiSettings.value.scanFinalModel,
    selectableModelOptions.value,
    defaultModelPlan.value.final?.id
  )
  aiSettings.value.recommendBriefModel = ensureModelSelection(
    aiSettings.value.recommendBriefModel,
    fastModelOptions.value,
    defaultModelPlan.value.recommendBrief?.id
  )
  aiSettings.value.recommendSummaryModel = ensureModelSelection(
    aiSettings.value.recommendSummaryModel,
    selectableModelOptions.value,
    defaultModelPlan.value.recommendSummary?.id
  )
  aiSettings.value.visionModel = ensureModelSelection(
    aiSettings.value.visionModel,
    visionModelOptions.value,
    defaultModelPlan.value.vision?.id
  )
}

const loadSystemSettings = async () => {
  try {
    const res = await getSystemSettings()
    const data = res?.data || {}
    basicSettings.value = {
      systemName: data.system_name || getStoredSystemName(),
      defaultMarket: data.default_market || basicSettings.value.defaultMarket,
      defaultCurrency: data.default_currency || basicSettings.value.defaultCurrency,
      language: data.language || basicSettings.value.language,
      timezone: data.timezone || basicSettings.value.timezone
    }
  } catch (error) {
    console.error('加载系统基础设置失败:', error)
  }
}

const saveBasicSettings = async () => {
  try {
    const systemName = String(basicSettings.value.systemName || '').trim() || getStoredSystemName()
    const res = await updateSystemSettings({
      settings: {
        system_name: systemName,
        default_market: basicSettings.value.defaultMarket,
        default_currency: basicSettings.value.defaultCurrency,
        language: basicSettings.value.language,
        timezone: basicSettings.value.timezone
      }
    })
    const data = res?.data || {}
    basicSettings.value = {
      ...basicSettings.value,
      systemName: data.system_name || systemName,
      defaultMarket: data.default_market || basicSettings.value.defaultMarket,
      defaultCurrency: data.default_currency || basicSettings.value.defaultCurrency,
      language: data.language || basicSettings.value.language,
      timezone: data.timezone || basicSettings.value.timezone
    }
    ElMessage.success('基础设置已保存')
  } catch (error) {
    console.error('保存基础设置失败:', error)
    ElMessage.error('保存基础设置失败')
  }
}

const loadModelCatalog = async () => {
  try {
    const res = await getAIModels()
    modelOptions.value = Array.isArray(res?.data) ? res.data : []
    providerInfo.value = res?.provider || DEFAULT_AI_SETTINGS.provider
    providerPlan.value = res?.providerPlan || {}
    const defaultPlan = res?.defaultPlan || {}
    defaultModelPlan.value = defaultPlan
  } catch (error) {
    console.error('加载模型清单失败:', error)
  }
}

const loadConfigData = async () => {
  try {
    const res = await getConfig()
    const data = res?.data || {}

    aiSettings.value = {
      ...DEFAULT_AI_SETTINGS,
      ...aiSettings.value,
      provider: data.ai_provider || DEFAULT_AI_SETTINGS.provider,
      fallbackProvider: data.ai_fallback_provider ?? DEFAULT_AI_SETTINGS.fallbackProvider,
      baseUrl: data.ai_base_url || DEFAULT_AI_SETTINGS.baseUrl,
      localUrl: data.ai_local_url || DEFAULT_AI_SETTINGS.localUrl,
      localModel: data.ai_local_model || DEFAULT_AI_SETTINGS.localModel,
      model: data.ai_model || DEFAULT_AI_SETTINGS.model,
      scanPulseModel: data.ai_model_scan_pulse || data.ai_model_scan_fast || DEFAULT_AI_SETTINGS.scanPulseModel,
      scanRiskModel: data.ai_model_scan_risk || DEFAULT_AI_SETTINGS.scanRiskModel,
      trendBatchModel: data.ai_model_trend_batch || DEFAULT_AI_SETTINGS.trendBatchModel,
      scanFinalModel: data.ai_model_scan_final || DEFAULT_AI_SETTINGS.scanFinalModel,
      scanReasoningEffort: data.ai_scan_reasoning_effort || DEFAULT_AI_SETTINGS.scanReasoningEffort,
      recommendBriefModel: data.ai_model_recommend_brief || DEFAULT_AI_SETTINGS.recommendBriefModel,
      recommendSummaryModel: data.ai_model_recommend_summary || DEFAULT_AI_SETTINGS.recommendSummaryModel,
      visionModel: data.ai_model_vision || DEFAULT_AI_SETTINGS.visionModel,
      apiKey: data.ai_api_key || '',
      localTimeout: Number(data.ai_local_timeout || DEFAULT_AI_SETTINGS.localTimeout),
      maxTokens: Number(data.num_predict || DEFAULT_AI_SETTINGS.maxTokens),
      temperature: Number(data.temperature ?? DEFAULT_AI_SETTINGS.temperature),
      recommendationRefreshInterval: Number(data.recommendation_refresh_interval || DEFAULT_AI_SETTINGS.recommendationRefreshInterval)
    }
    if ((res?.migration?.changedCount || 0) > 0) {
      ElMessage.info(`已自动迁移 ${res.migration.changedCount} 项旧模型配置`)
    }
  } catch (error) {
    console.error('加载系统配置失败:', error)
  }
}

const saveAISettings = async () => {
  try {
    const normalizedBaseUrl = (aiSettings.value.baseUrl || '').replace(/\/$/, '')
    const cloudChatUrl = normalizedBaseUrl ? `${normalizedBaseUrl}/chat/completions` : ''
    const primaryUrl = aiSettings.value.provider === 'ollama'
      ? aiSettings.value.localUrl
      : (cloudChatUrl || aiSettings.value.localUrl)

    await updateConfig({
      configs: {
        ai_provider: aiSettings.value.provider,
        ai_fallback_provider: aiSettings.value.fallbackProvider,
        ai_base_url: aiSettings.value.baseUrl,
        ai_url: primaryUrl,
        ai_api_style: 'openai-chat-completions',
        ai_local_url: aiSettings.value.localUrl,
        ai_local_model: aiSettings.value.localModel,
        ai_model: aiSettings.value.model,
        ai_model_scan_pulse: aiSettings.value.scanPulseModel,
        ai_model_scan_fast: aiSettings.value.scanPulseModel,
        ai_model_scan_risk: aiSettings.value.scanRiskModel,
        ai_model_trend_batch: aiSettings.value.trendBatchModel,
        ai_model_scan_final: aiSettings.value.scanFinalModel,
        ai_scan_reasoning_effort: aiSettings.value.scanReasoningEffort,
        ai_model_recommend_brief: aiSettings.value.recommendBriefModel,
        ai_model_recommend_summary: aiSettings.value.recommendSummaryModel,
        ai_model_vision: aiSettings.value.visionModel,
        ai_api_key: aiSettings.value.apiKey,
        num_predict: aiSettings.value.maxTokens,
        ai_local_timeout: aiSettings.value.localTimeout,
        temperature: aiSettings.value.temperature,
        recommendation_refresh_interval: aiSettings.value.recommendationRefreshInterval
      }
    })

    aiSettings.value = {
      ...aiSettings.value,
      baseUrl: normalizedBaseUrl || DEFAULT_AI_SETTINGS.baseUrl,
      fallbackProvider: aiSettings.value.fallbackProvider || ''
    }
    await Promise.all([
      loadConfigData(),
      loadModelCatalog()
    ])
    syncModelSelections()
    ElMessage.success('AI 路由配置已保存')
  } catch (error) {
    console.error('保存 AI 配置失败:', error)
    ElMessage.error('保存 AI 配置失败')
  }
}

const buildAIConnectionPayload = () => ({
  configs: {
    ai_provider: aiSettings.value.provider,
    ai_fallback_provider: aiSettings.value.fallbackProvider,
    ai_base_url: (aiSettings.value.baseUrl || '').trim(),
    ai_local_url: (aiSettings.value.localUrl || '').trim(),
    ai_local_model: (aiSettings.value.localModel || '').trim(),
    ai_model: (aiSettings.value.model || '').trim(),
    ai_api_key: (aiSettings.value.apiKey || '').trim()
  }
})

const validateAIConnectionForm = () => {
  const usingCloud = aiSettings.value.provider === 'nvidia' || aiSettings.value.provider === 'hybrid'
  const usingLocal = aiSettings.value.provider === 'ollama' || aiSettings.value.provider === 'hybrid'

  if (usingCloud && (!aiSettings.value.baseUrl || !aiSettings.value.model)) {
    ElMessage.warning('请先补全 Base URL 和默认模型')
    return false
  }

  if (usingLocal && (!aiSettings.value.localUrl || !aiSettings.value.localModel)) {
    ElMessage.warning('请先补全本地 Ollama 地址和模型')
    return false
  }

  return true
}

const handleTestAIConnection = async () => {
  if (!validateAIConnectionForm()) {
    return
  }

  try {
    const res = await testAIConnectionRequest(buildAIConnectionPayload())
    const info = res?.data || {}
    ElMessage.success(`连接成功：${info.model || '模型'} @ ${info.endpoint || 'endpoint'}`)
  } catch (error) {
    console.error('AI 连接测试失败:', error)
    ElMessage.error(error?.data?.error || error?.data?.message || error?.message || 'AI 连接测试失败')
  }
}

const saveNotificationSettings = () => {
  ElMessage.success('通知设置已保存')
}

const backupData = () => {
  ElMessage.success('数据备份已开始')
}

const scheduleBackup = () => {
  ElMessage.success('自动备份已设置')
}

const handleBackupFile = (file) => {
  ElMessage.success(`已选择文件: ${file.name}`)
}

const cleanupData = () => {
  ElMessage.warning(`将清理 ${cleanupRange.value} 天前的数据，是否确认？`)
}

const handleTradeOutboxEventSelectionChange = (rows) => {
  selectedTradeOutboxEvents.value = Array.isArray(rows) ? rows : []
}

const handleTradeOutboxSagaSelectionChange = (rows) => {
  selectedTradeOutboxSagas.value = Array.isArray(rows) ? rows : []
}

const loadTradeOutboxAdmin = async ({ showToast = false } = {}) => {
  if (!showTradeOutboxAdmin.value) {
    return
  }

  tradeOutboxLoading.value = true
  try {
    const eventParams = {
      limit: tradeOutboxFilter.value.limit,
      include_payload: tradeOutboxFilter.value.includePayload
    }
    if (tradeOutboxFilter.value.status) {
      eventParams.status = [tradeOutboxFilter.value.status]
    }
    if (tradeOutboxFilter.value.sagaId) {
      eventParams.saga_id = tradeOutboxFilter.value.sagaId
    }
    if (tradeOutboxFilter.value.eventType) {
      eventParams.event_type = tradeOutboxFilter.value.eventType
    }

    const sagaParams = {
      limit: Math.max(tradeOutboxFilter.value.limit, 20)
    }
    if (tradeOutboxFilter.value.status) {
      sagaParams.status = [tradeOutboxFilter.value.status]
    }

    const healthData = await getTradeOutboxHealth()
    const healthResult = {
      status: 'fulfilled',
      value: healthData
    }

    let eventsResult
    let sagasResult

    if (supportsTradeOutboxAdminDetails(healthData)) {
      ;[eventsResult, sagasResult] = await Promise.allSettled([
        getTradeOutboxEvents(eventParams),
        getTradeOutboxSagas(sagaParams)
      ])
    } else {
      const legacyReason = {
        response: { status: 404 },
        message: 'Legacy trade-service does not expose outbox admin detail endpoints'
      }
      eventsResult = {
        status: 'rejected',
        reason: legacyReason
      }
      sagasResult = {
        status: 'rejected',
        reason: legacyReason
      }
    }

    const resolved = resolveTradeOutboxAdminPayload({
      healthResult,
      eventsResult,
      sagasResult
    })

    tradeOutboxMode.value = resolved.mode
    tradeOutboxAvailability.value = resolved.availability
    tradeOutboxAvailabilityMessage.value = resolved.message
    tradeOutboxSummary.value = resolved.summary
    tradeOutboxEvents.value = resolved.events
    tradeOutboxSagas.value = resolved.sagas
    selectedTradeOutboxEvents.value = []
    selectedTradeOutboxSagas.value = []

    if (resolved.error) {
      throw resolved.error
    }

    if (showToast) {
      if (resolved.message) {
        ElMessage.info(`Trade outbox 已降级展示：${resolved.message}`)
      } else {
        ElMessage.success('Trade outbox 状态已刷新')
      }
    }
  } catch (error) {
    console.error('加载 trade outbox 治理数据失败:', error)
    ElMessage.error('加载 trade outbox 治理数据失败')
  } finally {
    tradeOutboxLoading.value = false
  }
}

const refreshTradeOutbox = () => loadTradeOutboxAdmin({ showToast: true })

const runTradeOutboxRepair = async () => {
  tradeOutboxActionLoading.value = true
  try {
    const res = await repairTradeOutbox()
    const repair = res?.data?.repair || {}
    ElMessage.success(`修复完成：死信归档 ${repair.deadLettered || 0}，重排 ${repair.rescheduled || 0}`)
    await loadTradeOutboxAdmin()
  } catch (error) {
    console.error('修复 trade outbox 失败:', error)
    ElMessage.error('修复 trade outbox 失败')
  } finally {
    tradeOutboxActionLoading.value = false
  }
}

const executeTradeOutboxAction = async ({
  title,
  action,
  successMessage
}) => {
  await ElMessageBox.confirm(title, '请确认', {
    type: 'warning',
    confirmButtonText: '确认',
    cancelButtonText: '取消'
  })

  tradeOutboxActionLoading.value = true
  try {
    await action()
    ElMessage.success(successMessage)
    await loadTradeOutboxAdmin()
  } catch (error) {
    if (error !== 'cancel' && error?.message !== 'cancel') {
      console.error(successMessage, error)
    }
  } finally {
    tradeOutboxActionLoading.value = false
  }
}

const requeueSelectedTradeOutboxEvents = async () => {
  if (!tradeOutboxSupportsEventData.value) {
    ElMessage.info('当前环境未开放事件列表接口')
    return
  }
  if (!selectedReplayableEventIds.value.length) {
    ElMessage.warning('请先选择可重放的事件')
    return
  }
  await executeTradeOutboxAction({
    title: `确认重放 ${selectedReplayableEventIds.value.length} 条事件吗？`,
    action: () => requeueTradeOutboxEvents(selectedReplayableEventIds.value),
    successMessage: '所选事件已进入重放队列'
  })
}

const purgeSelectedTradeDeadLetters = async () => {
  if (!tradeOutboxSupportsEventData.value) {
    ElMessage.info('当前环境未开放事件列表接口')
    return
  }
  if (!selectedDeadLetterEventIds.value.length) {
    ElMessage.warning('请先选择死信事件')
    return
  }
  await executeTradeOutboxAction({
    title: `确认清理 ${selectedDeadLetterEventIds.value.length} 条死信事件吗？`,
    action: () => purgeTradeDeadLetters(selectedDeadLetterEventIds.value),
    successMessage: '所选死信事件已清理'
  })
}

const requeueSelectedTradeOutboxSagas = async () => {
  if (!tradeOutboxSupportsSagaData.value) {
    ElMessage.info('当前环境未开放 Saga 聚合接口')
    return
  }
  if (!selectedTradeOutboxSagaIds.value.length) {
    ElMessage.warning('请先选择 Saga')
    return
  }
  await executeTradeOutboxAction({
    title: `确认按 Saga 重放 ${selectedTradeOutboxSagaIds.value.length} 组事件吗？`,
    action: () => requeueTradeOutboxSagas(selectedTradeOutboxSagaIds.value),
    successMessage: '所选 Saga 事件已进入重放队列'
  })
}

const purgeSelectedTradeDeadLettersBySaga = async () => {
  if (!tradeOutboxSupportsSagaData.value) {
    ElMessage.info('当前环境未开放 Saga 聚合接口')
    return
  }
  if (!selectedDeadLetterSagaIds.value.length) {
    ElMessage.warning('请先选择带死信的 Saga')
    return
  }
  await executeTradeOutboxAction({
    title: `确认按 Saga 清理 ${selectedDeadLetterSagaIds.value.length} 组死信事件吗？`,
    action: () => purgeTradeDeadLettersBySaga(selectedDeadLetterSagaIds.value),
    successMessage: '所选 Saga 死信事件已清理'
  })
}

const requeueTradeOutboxEvent = async (row) => {
  if (!tradeOutboxSupportsEventData.value) {
    ElMessage.info('当前环境未开放事件列表接口')
    return
  }
  await executeTradeOutboxAction({
    title: `确认重放事件 ${row.eventId} 吗？`,
    action: () => requeueTradeOutboxEvents([row.eventId]),
    successMessage: '事件已进入重放队列'
  })
}

const purgeTradeDeadLetterRow = async (row) => {
  if (!tradeOutboxSupportsEventData.value) {
    ElMessage.info('当前环境未开放事件列表接口')
    return
  }
  await executeTradeOutboxAction({
    title: `确认清理死信事件 ${row.eventId} 吗？`,
    action: () => purgeTradeDeadLetters([row.eventId]),
    successMessage: '死信事件已清理'
  })
}

const requeueTradeOutboxSaga = async (row) => {
  if (!tradeOutboxSupportsSagaData.value) {
    ElMessage.info('当前环境未开放 Saga 聚合接口')
    return
  }
  await executeTradeOutboxAction({
    title: `确认重放 Saga ${row.sagaId} 的事件吗？`,
    action: () => requeueTradeOutboxSagas([row.sagaId]),
    successMessage: 'Saga 事件已进入重放队列'
  })
}

const purgeTradeDeadLettersForSaga = async (row) => {
  if (!tradeOutboxSupportsSagaData.value) {
    ElMessage.info('当前环境未开放 Saga 聚合接口')
    return
  }
  await executeTradeOutboxAction({
    title: `确认清理 Saga ${row.sagaId} 的死信事件吗？`,
    action: () => purgeTradeDeadLettersBySaga([row.sagaId]),
    successMessage: 'Saga 死信事件已清理'
  })
}

const inspectSagaEvents = (row) => {
  if (!tradeOutboxSupportsEventData.value) {
    ElMessage.info('当前环境未开放事件列表接口')
    return
  }
  tradeOutboxFilter.value.sagaId = row.sagaId || ''
  if (!tradeOutboxFilter.value.status) {
    tradeOutboxFilter.value.status = 'published'
  }
  loadTradeOutboxAdmin({ showToast: true })
}

const refreshLogs = (showToast = true) => {
  return getSystemLogs({
    level: logLevel.value,
    limit: 120
  }).then((res) => {
    logs.value = Array.isArray(res?.data) ? res.data : []
    if (showToast) {
      ElMessage.success('日志已刷新')
    }
  }).catch((error) => {
    console.error('加载系统日志失败:', error)
    ElMessage.error('加载系统日志失败')
  })
}

const getLogType = (level) => {
  const types = { info: 'info', warning: 'warning', error: 'danger' }
  return types[level] || 'info'
}

onMounted(async () => {
  await loadModelCatalog()
  await loadConfigData()
  syncModelSelections()
  await Promise.all([
    loadSystemSettings(),
    refreshLogs(false),
    loadTradeOutboxAdmin()
  ])
})
</script>

<style scoped lang="scss">
.settings-page {
  display: grid;
  gap: 10px;
  padding: 6px;
}

.settings-overview-strip {
  margin-bottom: 2px;
}

.mobile-settings-rail {
  display: none;
}

.settings-tab-panel {
  display: grid;
  gap: 10px;
}

.settings-section-stack {
  display: grid;
  gap: 10px;
}

.settings-section-card {
  display: grid;
  gap: 10px;
}

.settings-tabs {
  border: 1px solid var(--panel-edge);
  border-radius: 10px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 24%, transparent), transparent 18%),
    color-mix(in srgb, var(--surface-emphasis) 88%, transparent);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  overflow: hidden;
  backdrop-filter: var(--panel-backdrop);

  :deep(.el-tabs__header) {
    margin: 0;
    border-bottom: 1px solid var(--panel-edge);
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 88%, transparent), color-mix(in srgb, var(--surface-muted) 56%, transparent));
  }

  :deep(.el-tabs__item) {
    color: var(--text-muted);
  }

  :deep(.el-tabs__item.is-active) {
    color: var(--accent);
    background: color-mix(in srgb, var(--surface-emphasis) 92%, transparent);
  }

  :deep(.el-tabs__item:hover) {
    color: var(--text-primary);
  }

  :deep(.el-tabs__content) {
    padding: 10px;
    background: transparent;
  }
}

.settings-form {
  width: 100%;
  max-width: none;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 94%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);

  :deep(.el-form-item) {
    margin-bottom: 10px;
  }

  :deep(.el-form-item__label) {
    font-size: 12px;
    line-height: 30px;
  }

  :deep(.el-form-item:last-child) {
    margin-bottom: 0;
  }

  :deep(.el-select-dropdown__item.is-disabled) {
    color: color-mix(in srgb, var(--text-primary) 44%, transparent);
  }
}

.settings-secondary-button {
  --el-button-bg-color: color-mix(in srgb, var(--surface-soft) 86%, var(--surface-emphasis) 14%);
  --el-button-border-color: color-mix(in srgb, var(--accent) 42%, var(--border-soft) 58%);
  --el-button-text-color: var(--text-primary);
  --el-button-hover-bg-color: color-mix(in srgb, var(--accent) 18%, var(--surface-soft) 82%);
  --el-button-hover-border-color: color-mix(in srgb, var(--accent) 58%, var(--border-soft) 42%);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-active-bg-color: color-mix(in srgb, var(--accent) 24%, var(--surface-soft) 76%);
  --el-button-active-border-color: color-mix(in srgb, var(--accent) 64%, var(--border-soft) 36%);
  --el-button-active-text-color: var(--text-primary);
  --el-button-disabled-bg-color: color-mix(in srgb, var(--surface-muted) 94%, transparent);
  --el-button-disabled-border-color: color-mix(in srgb, var(--border-soft) 88%, transparent);
  --el-button-disabled-text-color: color-mix(in srgb, var(--text-primary) 48%, transparent);
  font-weight: 600;
  background: var(--el-button-bg-color);
  border-color: var(--el-button-border-color);
  color: var(--el-button-text-color);
}

.settings-page :deep(.el-button:not(.el-button--primary):not(.el-button--danger):not(.el-button--warning):not(.is-link)) {
  --el-button-bg-color: color-mix(in srgb, var(--surface-soft) 86%, var(--surface-emphasis) 14%);
  --el-button-border-color: color-mix(in srgb, var(--accent) 42%, var(--border-soft) 58%);
  --el-button-text-color: var(--text-primary);
  --el-button-hover-bg-color: color-mix(in srgb, var(--accent) 18%, var(--surface-soft) 82%);
  --el-button-hover-border-color: color-mix(in srgb, var(--accent) 58%, var(--border-soft) 42%);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-active-bg-color: color-mix(in srgb, var(--accent) 24%, var(--surface-soft) 76%);
  --el-button-active-border-color: color-mix(in srgb, var(--accent) 64%, var(--border-soft) 36%);
  --el-button-active-text-color: var(--text-primary);
  background: var(--el-button-bg-color);
  border-color: var(--el-button-border-color);
  color: var(--el-button-text-color);
}

.settings-form:not(.ai-form) {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  column-gap: 14px;
  align-items: start;
}

.settings-form:not(.ai-form) :deep(.el-form-item:last-child) {
  grid-column: 1 / -1;
}

.ai-layout {
  display: grid;
  grid-template-columns: minmax(520px, 1fr) minmax(260px, 0.82fr);
  gap: 10px;
}

.provider-plan {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.provider-plan-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 88%, transparent);
  border: 1px solid var(--border-color);

  strong {
    color: var(--text-primary);
  }

  span,
  small {
    color: var(--text-secondary);
  }
}

.inline-tip {
  margin-left: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.ai-runtime-alert {
  border-radius: 8px;
}

.model-catalog {
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.catalog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;

  h3 {
    margin: 0;
    color: var(--text-primary);
  }

  span {
    color: var(--text-muted);
    font-size: 13px;
  }
}

.catalog-grid {
  display: grid;
  gap: 8px;
  max-height: 620px;
  overflow: auto;
}

.model-card {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--panel-stroke);
  background: var(--surface-muted);

  p {
    margin: 8px 0 10px;
    color: var(--text-secondary);
    font-size: 12px;
    word-break: break-all;
  }
}

.model-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;

  strong {
    color: var(--text-primary);
  }
}

.model-tags {
  display: flex;
  gap: 8px;
  align-items: center;
}

.availability-note {
  display: block;
  color: var(--text-muted);
  line-height: 1.6;
}

.model-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;

  span {
    padding: 4px 8px;
    border-radius: 999px;
    background: var(--surface-soft);
    color: var(--text-muted);
    font-size: 12px;
  }
}

.data-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.data-section {
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);

  h4 {
    margin: 0 0 8px;
    color: var(--text-primary);
  }

  p {
    margin: 0 0 16px;
    color: var(--text-muted);
  }
}

.outbox-admin-panel {
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 86%, transparent), color-mix(in srgb, var(--surface-muted) 72%, transparent));
}

.outbox-alert {
  margin-bottom: 10px;
}

.outbox-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.outbox-stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--panel-stroke);
  background: color-mix(in srgb, var(--card-bg) 86%, transparent);

  .stat-label {
    color: var(--text-muted);
    font-size: 12px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  strong {
    color: var(--text-primary);
    font-size: 22px;
    line-height: 1.1;
  }

  small {
    color: var(--text-secondary);
  }
}

.outbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.outbox-toolbar-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.outbox-panels {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
  gap: 10px;
}

.outbox-panel {
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--panel-stroke);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
}

.outbox-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;

  h5 {
    margin: 0 0 6px;
    color: var(--text-primary);
    font-size: 16px;
  }

  p {
    margin: 0;
    color: var(--text-muted);
    font-size: 13px;
  }
}

.outbox-table-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.payload-preview {
  display: block;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.section-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.logs-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.logs-content {
  max-height: 520px;
  overflow-y: auto;
  background: var(--surface-soft);
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  padding: 8px;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  border-bottom: 1px solid var(--panel-stroke);

  &:last-child {
    border-bottom: none;
  }

  .log-time {
    color: var(--text-muted);
    min-width: 160px;
  }

  .log-message {
    color: var(--text-secondary);
  }

  &.info .log-message {
    color: var(--accent-strong);
  }

  &.warning .log-message {
    color: var(--warning);
  }

  &.error .log-message {
    color: var(--danger);
  }
}

@media (max-width: 1180px) {
  .mobile-settings-rail {
    display: block;
  }

  .settings-tabs :deep(.el-tabs__header) {
    display: none;
  }

  .ai-layout,
  .data-grid,
  .outbox-panels {
    grid-template-columns: 1fr;
  }

  .outbox-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .settings-page {
    gap: 7px;
    padding: 0 0 8px;
  }

  .settings-tabs :deep(.el-tabs__content) {
    padding: 7px;
  }

  .settings-form,
  .model-catalog,
  .data-section,
  .outbox-admin-panel {
    padding: 8px;
    border-radius: 8px;
  }

  .settings-form:not(.ai-form) {
    grid-template-columns: 1fr;
  }

  .settings-form {
    :deep(.el-form-item) {
      display: grid;
      grid-template-columns: 86px minmax(0, 1fr);
      align-items: center;
      margin-bottom: 7px;
    }

    :deep(.el-form-item__label) {
      width: auto !important;
      padding-right: 8px;
      justify-content: flex-end;
      line-height: 28px;
    }

    :deep(.el-form-item__content) {
      min-width: 0;
      margin-left: 0 !important;
    }
  }

  .catalog-head {
    align-items: flex-start;
    gap: 6px;
    flex-direction: column;
  }

  .model-top {
    align-items: flex-start;
    flex-direction: column;
  }

  .outbox-stats {
    grid-template-columns: 1fr;
  }

  .outbox-panel-head {
    flex-direction: column;
  }
}
</style>
