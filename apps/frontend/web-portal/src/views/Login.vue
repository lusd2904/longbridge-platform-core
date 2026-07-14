<template>
  <div class="login-page">
    <div class="space-background"></div>
    <div class="glass-login-box">
      <div class="login-header">
        <h1 class="glow-title">QUANTITATIVE TRADING</h1>
        <p class="subtitle">& AI ANALYSIS CORE</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="账号 (Username)"
            size="large"
            :prefix-icon="User"
            class="cyber-input"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码 (Password)"
            size="large"
            :prefix-icon="Lock"
            class="cyber-input"
            show-password
            clearable
          />
        </el-form-item>

        <div class="form-tools">
          <el-checkbox v-model="rememberMe">保持登录</el-checkbox>
          <button
            v-if="canConfigureEndpoint"
            type="button"
            class="endpoint-toggle"
            @click="showServerConfig = !showServerConfig"
          >
            {{ showServerConfig ? '收起配置' : '网络配置' }}
          </button>
        </div>

        <transition name="fade-slide">
          <div v-if="showServerConfig" class="endpoint-panel">
            <div class="endpoint-input-row">
              <el-input
                v-model="apiBaseUrl"
                placeholder="API Base URL"
                clearable
                class="cyber-input-small"
              />
              <el-button class="cyber-btn-small" @click="saveApiEndpoint">保存</el-button>
            </div>
            
            <div class="endpoint-presets">
              <button
                v-for="preset in endpointPresets"
                :key="preset.label"
                type="button"
                class="preset-button"
                @click="applyEndpointPreset(preset.value)"
              >
                {{ preset.label }}
              </button>
            </div>
            <p v-if="endpointStatusText" class="endpoint-status" :class="endpointStatusType">
              {{ endpointStatusText }}
            </p>
          </div>
        </transition>

        <el-form-item class="submit-item">
          <el-button
            type="primary"
            size="large"
            class="login-button cyber-btn"
            :loading="loading"
            @click="handleLogin"
          >
            SYSTEM LOGIN
          </el-button>
        </el-form-item>
      </el-form>
      
      <div class="login-footer">
        <p>SECURE CONNECTION · NVIDIA AI ACCELERATED</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, TrendCharts, User } from '@element-plus/icons-vue'
import { login, setSession, setToken } from '../utils/auth.js'
import { getApiBaseUrl, isNativeClient, request, setApiBaseUrl } from '../utils/requestPure.js'

const router = useRouter()
const loginFormRef = ref(null)
const loading = ref(false)
const rememberMe = ref(false)
const apiBaseUrl = ref(getApiBaseUrl())
const canConfigureEndpoint = isNativeClient()
const showServerConfig = ref(false)
const testingEndpoint = ref(false)
const endpointStatusText = ref('')
const endpointStatusType = ref('info')

const loginForm = reactive({
  username: '',
  password: ''
})

const nativePlatformLabel = computed(() => {
  if (!canConfigureEndpoint) {
    return 'Web'
  }

  return Capacitor.getPlatform() === 'android' ? 'Android 原生壳' : 'iOS Swift 壳'
})

const endpointPresets = computed(() => [
  { label: '安卓模拟器', value: 'http://10.0.2.2:3100' },
  { label: 'iOS 模拟器', value: 'http://127.0.0.1:3100' },
  { label: '恢复默认', value: '' }
])

const currentResolvedBaseUrl = computed(() => apiBaseUrl.value || getApiBaseUrl())

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '长度在 3 到 20 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '长度在 6 到 20 个字符', trigger: 'blur' }
  ]
}

const normalizeHomePath = (value) => {
  const candidate = String(value || '').trim()
  if (!candidate || candidate === '/workspace') {
    return '/portal'
  }
  return candidate
}

const handleLogin = async () => {
  if (!loginFormRef.value) {
    return
  }

  try {
    await loginFormRef.value.validate()
    loading.value = true

    const res = await login({
      username: loginForm.username,
      password: loginForm.password
    })

    if (!res?.success) {
      ElMessage.error(res?.error || '登录失败')
      return
    }

    ElMessage.success('登录成功')
    setToken(res.data.token)
    setSession(res.data)
    localStorage.setItem('user', JSON.stringify(res.data.user || {}))

    if (rememberMe.value) {
      localStorage.setItem('remember_username', loginForm.username)
    } else {
      localStorage.removeItem('remember_username')
    }

    const homePath = normalizeHomePath(res?.data?.navigation?.homePath)
    await router.replace(homePath)
  } catch (error) {
    console.error('登录失败:', error)
    ElMessage.error(error?.response?.data?.error || error?.data?.error || '登录失败')
  } finally {
    loading.value = false
  }
}

const saveApiEndpoint = () => {
  try {
    const saved = setApiBaseUrl(apiBaseUrl.value)
    apiBaseUrl.value = saved
    endpointStatusText.value = saved ? `当前地址 ${saved}` : '已恢复默认服务地址'
    endpointStatusType.value = 'info'
    ElMessage.success(saved ? '服务地址已保存' : '已恢复默认地址')
  } catch (error) {
    console.error('保存服务地址失败:', error)
    ElMessage.error('保存服务地址失败')
  }
}

const applyEndpointPreset = (value) => {
  apiBaseUrl.value = value
  saveApiEndpoint()
}

const testApiConnection = async () => {
  try {
    testingEndpoint.value = true
    endpointStatusText.value = ''

    await request.post('/svc/user/api/v1/auth/login', {
      username: '__probe__',
      password: '__probe__'
    })

    endpointStatusType.value = 'success'
    endpointStatusText.value = '服务已连通，可以直接登录。'
  } catch (error) {
    const status = Number(error?.response?.status || 0)
    if (status >= 400 && status < 500) {
      endpointStatusType.value = 'success'
      endpointStatusText.value = `服务已连通，当前返回 ${status}。`
      return
    }

    endpointStatusType.value = 'danger'
    endpointStatusText.value = error?.data?.error || error?.message || '连接测试失败'
  } finally {
    testingEndpoint.value = false
  }
}

const savedUsername = localStorage.getItem('remember_username')
if (savedUsername) {
  loginForm.username = savedUsername
  rememberMe.value = true
}
</script>

<style scoped lang="scss">
.login-page {
  width: 100vw;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background-color: #0f172a;
}

.space-background {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(circle at 50% 50%, #1e3a8a 0%, #020617 100%);
  z-index: 1;
}

.space-background::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

.glass-login-box {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 420px;
  padding: 40px;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 20px 50px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.05);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.glow-title {
  font-size: 1.8rem;
  margin: 0 0 5px 0;
  color: #fff;
  letter-spacing: 2px;
  font-weight: 700;
  text-shadow: 0 0 10px rgba(96, 165, 250, 0.8);
}

.subtitle {
  font-size: 0.85rem;
  color: #94a3b8;
  letter-spacing: 4px;
  margin: 0;
}

.login-form {
  width: 100%;
}

:deep(.cyber-input .el-input__wrapper) {
  background-color: rgba(0, 0, 0, 0.3) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
  border-radius: 8px;
  padding: 2px 10px;
}

:deep(.cyber-input .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #3b82f6 inset !important;
  background-color: rgba(59, 130, 246, 0.05) !important;
}

:deep(.cyber-input .el-input__inner) {
  color: #e2e8f0;
  font-family: monospace;
}

.form-tools {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  font-size: 0.85rem;
}

:deep(.el-checkbox__label) {
  color: #94a3b8;
}

.endpoint-toggle {
  background: none;
  border: none;
  color: #60a5fa;
  cursor: pointer;
  padding: 0;
  font-size: 0.85rem;
  transition: color 0.3s;
}

.endpoint-toggle:hover {
  color: #93c5fd;
  text-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
}

.endpoint-panel {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 20px;
  border: 1px solid rgba(255,255,255,0.05);
}

.endpoint-input-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.preset-button {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  color: #cbd5e1;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  margin-right: 8px;
  transition: all 0.2s;
}

.preset-button:hover {
  background: rgba(59,130,246,0.2);
  border-color: #3b82f6;
  color: #fff;
}

.login-button.cyber-btn {
  width: 100%;
  background: linear-gradient(90deg, #059669, #10b981);
  border: none;
  height: 44px;
  font-weight: 600;
  letter-spacing: 2px;
  font-family: monospace;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
}

.login-button.cyber-btn:hover {
  background: linear-gradient(90deg, #10b981, #34d399);
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.6);
  transform: translateY(-1px);
}

.login-footer {
  margin-top: 25px;
  text-align: center;
  font-size: 0.7rem;
  color: #475569;
  letter-spacing: 1px;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
