<template>
  <div class="login-page">
    <div class="top-bar">
      <ThemeSwitcher />
    </div>
    <!-- 科技感线条代码雨背景 -->
    <CyberBackground />
    
    <div class="glass-login-box glass-panel">
      <div class="login-header">
        <h1 class="glow-title">长桥量化交易平台</h1>
        <p class="subtitle">专业级智能量化交易系统</p>
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
            系统登录
          </el-button>
        </el-form-item>
      </el-form>
      
      <div class="login-footer">
        <p>安全连接 · 智能引擎驱动</p>
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
import ThemeSwitcher from '../components/layout/ThemeSwitcher.vue'
import CyberBackground from '../components/layout/CyberBackground.vue'

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
  return '/portal'
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
  font-family: 'Inter', 'Orbitron', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: transparent;
}

.top-bar {
  position: absolute;
  top: 24px;
  right: 24px;
  z-index: 10;
}

/* Glass Login Box */
.glass-login-box {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 440px;
  padding: 50px 40px;
  display: flex;
  flex-direction: column;
  transition: transform 0.3s ease;
}

.glass-login-box:hover {
  transform: translateY(-5px);
  border-color: color-mix(in srgb, var(--accent) 30%, transparent) !important;
  box-shadow: 0 10px 50px color-mix(in srgb, var(--accent) 10%, transparent) !important;
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.glow-title {
  font-size: 2.2rem;
  margin: 0 0 10px 0;
  font-weight: 800;
  color: var(--text-emphasis);
  letter-spacing: 2px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-secondary);
  letter-spacing: 6px;
  text-transform: uppercase;
  margin: 0;
}

.login-form {
  width: 100%;
}

/* Inputs */
:deep(.cyber-input .el-input__wrapper) {
  background-color: var(--surface-soft) !important;
  box-shadow: none !important;
  border-bottom: 2px solid var(--border-soft) !important;
  border-radius: 6px 6px 0 0;
  padding: 6px 12px;
  transition: all 0.3s ease;
}

:deep(.cyber-input .el-input__wrapper.is-focus) {
  border-bottom: 2px solid var(--accent) !important;
  background-color: color-mix(in srgb, var(--accent) 5%, var(--surface-soft)) !important;
}

:deep(.cyber-input .el-input__inner) {
  color: var(--text-primary);
  font-size: 1rem;
  letter-spacing: 1px;
}

.form-tools {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  font-size: 0.9rem;
}

:deep(.el-checkbox__label) {
  color: var(--text-secondary);
  transition: color 0.3s ease;
}

:deep(.el-checkbox__input.is-checked + .el-checkbox__label) {
  color: var(--accent);
}

:deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: var(--accent);
  border-color: var(--accent);
}

.endpoint-toggle {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font-size: 0.85rem;
  transition: all 0.3s ease;
}

.endpoint-toggle:hover {
  color: var(--accent-strong);
}

.endpoint-panel {
  background: var(--surface-soft);
  border-radius: 12px;
  padding: 15px;
  margin-bottom: 25px;
  border: 1px solid var(--border-soft);
}

.endpoint-input-row {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.preset-button {
  background: var(--surface-soft);
  border: 1px solid var(--border-soft);
  color: var(--text-primary);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  margin-right: 8px;
  transition: all 0.3s ease;
}

.preset-button:hover {
  background: color-mix(in srgb, var(--accent) 15%, var(--surface-soft));
  border-color: var(--accent);
  color: var(--text-emphasis);
}

/* Submit Button */
.login-button.cyber-btn {
  width: 100%;
  background: var(--accent);
  border: none;
  height: 50px;
  font-weight: 700;
  font-size: 1rem;
  letter-spacing: 4px;
  color: #fff;
  border-radius: 25px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 10px 20px color-mix(in srgb, var(--accent) 25%, transparent);
}

.login-button.cyber-btn:hover {
  background: var(--accent-strong);
  transform: translateY(-2px);
}

.login-button.cyber-btn:active {
  transform: translateY(1px);
}

/* Footer */
.login-footer {
  margin-top: 30px;
  text-align: center;
  font-size: 0.7rem;
  color: var(--text-muted);
  letter-spacing: 2px;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-15px);
}
</style>
