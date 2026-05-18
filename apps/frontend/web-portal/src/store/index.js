import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 账户状态
export const useAccountStore = defineStore('account', () => {
  const accountInfo = ref({
    total_val: '$0.00',
    daily_pnl: '+$0.00',
    pnl_ratio: '0.00%',
    cash: '$0.00',
    mkt_val: '$0.00'
  })

  const updateAccount = (data) => {
    accountInfo.value = { ...accountInfo.value, ...data }
  }

  return {
    accountInfo,
    updateAccount
  }
})

// 持仓状态
export const usePositionStore = defineStore('position', () => {
  const positions = ref([])
  const loading = ref(false)

  const setPositions = (data) => {
    positions.value = data
  }

  const setLoading = (status) => {
    loading.value = status
  }

  const totalPnl = computed(() => {
    return positions.value.reduce((sum, p) => sum + (parseFloat(p.pnl) || 0), 0)
  })

  return {
    positions,
    loading,
    setPositions,
    setLoading,
    totalPnl
  }
})

// AI分析状态
export const useAIStore = defineStore('ai', () => {
  const aiDecisions = ref([])
  const aiModels = ref([
    { name: 'Gemma', accuracy: 78.5, signals: 12 },
    { name: 'Llama', accuracy: 82.3, signals: 15 },
    { name: 'DeepSeek', accuracy: 85.7, signals: 10 }
  ])

  const setAIDecisions = (data) => {
    aiDecisions.value = data
  }

  return {
    aiDecisions,
    aiModels,
    setAIDecisions
  }
})
