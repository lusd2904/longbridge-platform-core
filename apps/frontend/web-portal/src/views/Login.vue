<template>
  <div class="login-page">
    <div class="login-shell">
      <section class="hero-panel">
        <div class="brand-lockup">
          <div class="brand-mark">
            <el-icon size="28"><TrendCharts /></el-icon>
          </div>
          <span class="brand-title">Refactor V2</span>
        </div>

        <div class="motion-stage" aria-hidden="true">
          <div class="stage-grid"></div>
          <div class="stage-aura"></div>
          <div class="stage-ring ring-one"></div>
          <div class="stage-ring ring-two"></div>
          <div class="stage-ring ring-three"></div>
          <div class="stage-sweep"></div>
          <div class="stage-core"></div>
          <div class="stage-orbit orbit-one"></div>
          <div class="stage-orbit orbit-two"></div>
          <span class="stage-node node-one"></span>
          <span class="stage-node node-two"></span>
          <span class="stage-node node-three"></span>
          <span class="stage-node node-four"></span>
          <span class="stage-beam beam-one"></span>
          <span class="stage-beam beam-two"></span>
        </div>
      </section>

      <section class="form-panel">
        <div class="form-head">
          <span class="form-kicker">Secure Login</span>
          <h1>Refactor V2</h1>
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
              placeholder="用户名"
              size="large"
              :prefix-icon="User"
              clearable
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              clearable
            />
          </el-form-item>

          <div class="form-tools">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
            <button
              v-if="canConfigureEndpoint"
              type="button"
              class="endpoint-button"
              @click="showServerConfig = !showServerConfig"
            >
              {{ showServerConfig ? '收起服务地址' : '服务地址' }}
            </button>
          </div>

          <transition name="fade-slide">
            <div v-if="showServerConfig" class="endpoint-panel">
              <div class="endpoint-input-row">
                <el-input
                  v-model="apiBaseUrl"
                  placeholder="https://your-domain.com"
                  clearable
                />
                <el-button plain @click="saveApiEndpoint">保存</el-button>
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

              <div class="endpoint-meta">
                <span>{{ nativePlatformLabel }}</span>
                <span class="endpoint-meta-url">{{ currentResolvedBaseUrl || '使用默认服务地址' }}</span>
              </div>

              <button
                type="button"
                class="endpoint-test"
                :disabled="testingEndpoint"
                @click="testApiConnection"
              >
                {{ testingEndpoint ? '连接测试中...' : '连接测试' }}
              </button>

              <p
                v-if="endpointStatusText"
                class="endpoint-status"
                :class="endpointStatusType"
              >
                {{ endpointStatusText }}
              </p>
            </div>
          </transition>

          <el-form-item class="submit-item">
            <el-button
              type="primary"
              size="large"
              class="login-button"
              :loading="loading"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>
      </section>
    </div>

    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>
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
    return '/dashboard'
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
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  background:
    radial-gradient(circle at 18% 18%, rgba(120, 230, 255, 0.2), transparent 24%),
    radial-gradient(circle at 84% 18%, rgba(255, 182, 135, 0.16), transparent 20%),
    radial-gradient(circle at 80% 82%, rgba(104, 142, 255, 0.2), transparent 22%),
    linear-gradient(145deg, #07101e 0%, #0b1730 46%, #060e1b 100%);
}

.login-shell {
  position: relative;
  z-index: 2;
  width: min(1120px, 100%);
  margin: auto 0;
  min-height: 680px;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) 400px;
  border-radius: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
  box-shadow: 0 30px 80px rgba(2, 10, 24, 0.46);
  backdrop-filter: blur(30px) saturate(150%);
  overflow: hidden;
}

.hero-panel,
.form-panel {
  position: relative;
}

.hero-panel {
  padding: 42px 42px 36px;
  display: flex;
  flex-direction: column;
  gap: 28px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background:
    linear-gradient(180deg, rgba(9, 21, 42, 0.72), rgba(7, 16, 32, 0.3)),
    radial-gradient(circle at center, rgba(255, 255, 255, 0.02), transparent 58%);
}

.brand-lockup {
  display: inline-flex;
  align-items: center;
  gap: 16px;
}

.brand-mark {
  width: 60px;
  height: 60px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  color: #07131f;
  background: linear-gradient(135deg, #ffb870 0%, #ffd89e 100%);
  box-shadow: 0 18px 38px rgba(255, 184, 112, 0.28);
}

.brand-title {
  font-family: var(--font-heading);
  font-size: clamp(30px, 4vw, 54px);
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #f8fbff;
}

.motion-stage {
  position: relative;
  flex: 1;
  min-height: 480px;
  border-radius: 28px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    linear-gradient(180deg, rgba(7, 16, 31, 0.62), rgba(6, 13, 26, 0.28)),
    radial-gradient(circle at center, rgba(122, 230, 255, 0.06), transparent 58%);
}

.stage-grid,
.stage-aura,
.stage-sweep,
.stage-core,
.stage-orbit,
.stage-ring,
.stage-node,
.stage-beam {
  position: absolute;
}

.stage-grid {
  inset: 0;
  background:
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at center, black 44%, transparent 100%);
  opacity: 0.35;
}

.stage-aura {
  inset: 10%;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(129, 231, 255, 0.22), rgba(129, 231, 255, 0.04) 42%, transparent 72%);
  filter: blur(12px);
  animation: pulse-aura 5.6s ease-in-out infinite;
}

.stage-ring {
  top: 50%;
  left: 50%;
  border-radius: 50%;
  border: 1px solid rgba(140, 224, 255, 0.18);
  transform: translate(-50%, -50%);
  box-shadow: 0 0 30px rgba(123, 224, 255, 0.08);
}

.ring-one {
  width: 210px;
  height: 210px;
  animation: pulse-ring 5s ease-in-out infinite;
}

.ring-two {
  width: 310px;
  height: 310px;
  animation: pulse-ring 5s ease-in-out infinite 1s;
}

.ring-three {
  width: 430px;
  height: 430px;
  animation: pulse-ring 5s ease-in-out infinite 2s;
}

.stage-sweep {
  top: 50%;
  left: 50%;
  width: 520px;
  height: 520px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: conic-gradient(from 0deg, transparent 0deg 310deg, rgba(124, 228, 255, 0.34) 332deg, transparent 360deg);
  filter: blur(1px);
  mix-blend-mode: screen;
  animation: rotate-sweep 8s linear infinite;
}

.stage-core {
  top: 50%;
  left: 50%;
  width: 112px;
  height: 112px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background:
    radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.95), rgba(147, 232, 255, 0.82) 28%, rgba(60, 123, 255, 0.32) 70%, transparent 100%);
  box-shadow:
    0 0 48px rgba(110, 212, 255, 0.48),
    inset 0 0 22px rgba(255, 255, 255, 0.58);
  animation: core-glow 4.2s ease-in-out infinite;
}

.stage-orbit {
  top: 50%;
  left: 50%;
  width: 360px;
  height: 360px;
  margin: -180px 0 0 -180px;
  border-radius: 50%;
  border: 1px dashed rgba(255, 255, 255, 0.12);
}

.orbit-one {
  animation: orbit-spin 12s linear infinite;
}

.orbit-two {
  width: 470px;
  height: 470px;
  margin: -235px 0 0 -235px;
  opacity: 0.7;
  transform: rotate(62deg);
  animation: rotate-reverse 16s linear infinite;
}

.stage-node {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, #9cf1ff 0%, #6b88ff 100%);
  box-shadow: 0 0 18px rgba(123, 221, 255, 0.78);
}

.node-one {
  top: 19%;
  left: 61%;
  animation: float-node 4.6s ease-in-out infinite;
}

.node-two {
  top: 66%;
  left: 27%;
  animation: float-node 5.2s ease-in-out infinite 1s;
}

.node-three {
  top: 73%;
  left: 71%;
  animation: float-node 5s ease-in-out infinite 0.7s;
}

.node-four {
  top: 31%;
  left: 22%;
  animation: float-node 4.8s ease-in-out infinite 1.4s;
}

.stage-beam {
  top: 50%;
  width: 1px;
  height: 220px;
  transform: translateY(-50%);
  background: linear-gradient(180deg, transparent, rgba(255, 255, 255, 0.6), transparent);
  opacity: 0.22;
}

.beam-one {
  left: 22%;
  animation: beam-shift 4.4s ease-in-out infinite;
}

.beam-two {
  right: 18%;
  animation: beam-shift 5s ease-in-out infinite 1.1s;
}

.form-panel {
  padding: 56px 38px 38px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: linear-gradient(180deg, rgba(10, 18, 34, 0.88), rgba(8, 14, 28, 0.7));
}

.form-head {
  margin-bottom: 28px;
}

.form-kicker {
  display: inline-block;
  margin-bottom: 10px;
  font-size: 12px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: rgba(198, 215, 246, 0.58);
}

.form-head h1 {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 30px;
  color: #f7fbff;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 52px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.login-form :deep(.el-input__inner) {
  color: #f5fbff;
}

.login-form :deep(.el-input__inner::placeholder) {
  color: rgba(199, 214, 241, 0.5);
}

.login-form :deep(.el-input__prefix-inner),
.login-form :deep(.el-input__suffix-inner) {
  color: rgba(217, 232, 255, 0.62);
}

.login-form :deep(.el-checkbox__label) {
  color: rgba(224, 235, 252, 0.82);
}

.form-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 2px 0 20px;
}

.endpoint-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: rgba(135, 219, 255, 0.88);
  font-size: 13px;
  cursor: pointer;
}

.endpoint-panel {
  display: grid;
  gap: 10px;
  margin-bottom: 20px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.endpoint-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.endpoint-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preset-button,
.endpoint-test {
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7fbff;
  font-size: 12px;
  cursor: pointer;
}

.endpoint-test {
  justify-self: start;
}

.endpoint-meta {
  display: grid;
  gap: 4px;
  color: rgba(214, 226, 246, 0.78);
  font-size: 12px;
}

.endpoint-meta-url {
  color: rgba(135, 219, 255, 0.9);
  word-break: break-all;
}

.endpoint-status {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}

.endpoint-status.success {
  color: #7af0ae;
}

.endpoint-status.info {
  color: rgba(214, 226, 246, 0.88);
}

.endpoint-status.danger {
  color: #ffb1a1;
}

.endpoint-panel :deep(.el-button) {
  height: 40px;
  padding: 0 18px;
  border-radius: 14px;
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #f7fbff;
}

.submit-item {
  margin-bottom: 0;
}

.login-button {
  width: 100%;
  height: 52px;
  border: 0;
  border-radius: 18px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #07121f;
  background: linear-gradient(135deg, #ffb76f 0%, #ffd79a 100%);
  box-shadow: 0 18px 38px rgba(255, 184, 111, 0.24);
}

.login-button:hover {
  background: linear-gradient(135deg, #ffc482 0%, #ffe1b0 100%);
}

.ambient {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.5;
}

.ambient-one {
  top: 6%;
  left: 3%;
  width: 260px;
  height: 260px;
  background: rgba(105, 223, 255, 0.18);
}

.ambient-two {
  right: 4%;
  bottom: 8%;
  width: 320px;
  height: 320px;
  background: rgba(118, 142, 255, 0.14);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.22s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@keyframes rotate-sweep {
  from {
    transform: translate(-50%, -50%) rotate(0deg);
  }
  to {
    transform: translate(-50%, -50%) rotate(360deg);
  }
}

@keyframes rotate-reverse {
  from {
    transform: rotate(62deg);
  }
  to {
    transform: rotate(-298deg);
  }
}

@keyframes orbit-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse-ring {
  0%,
  100% {
    opacity: 0.28;
    transform: translate(-50%, -50%) scale(0.98);
  }
  50% {
    opacity: 0.76;
    transform: translate(-50%, -50%) scale(1.03);
  }
}

@keyframes core-glow {
  0%,
  100% {
    transform: translate(-50%, -50%) scale(0.96);
    box-shadow:
      0 0 48px rgba(110, 212, 255, 0.42),
      inset 0 0 20px rgba(255, 255, 255, 0.54);
  }
  50% {
    transform: translate(-50%, -50%) scale(1.04);
    box-shadow:
      0 0 68px rgba(132, 225, 255, 0.56),
      inset 0 0 28px rgba(255, 255, 255, 0.7);
  }
}

@keyframes pulse-aura {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(0.94);
  }
  50% {
    opacity: 1;
    transform: scale(1.03);
  }
}

@keyframes float-node {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -12px, 0);
  }
}

@keyframes beam-shift {
  0%,
  100% {
    opacity: 0.16;
    height: 180px;
  }
  50% {
    opacity: 0.34;
    height: 250px;
  }
}

@media (max-width: 980px) {
  .login-page {
    padding:
      max(18px, env(safe-area-inset-top, 0px))
      max(18px, env(safe-area-inset-right, 0px))
      max(18px, env(safe-area-inset-bottom, 0px))
      max(18px, env(safe-area-inset-left, 0px));
    align-items: flex-start;
  }

  .login-shell {
    width: 100%;
    min-height: auto;
    grid-template-columns: 1fr;
  }

  .hero-panel {
    min-height: 300px;
    border-right: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .motion-stage {
    min-height: 300px;
  }
}

@media (max-width: 640px) {
  .login-page {
    padding:
      max(14px, env(safe-area-inset-top, 0px))
      max(14px, env(safe-area-inset-right, 0px))
      max(14px, calc(env(safe-area-inset-bottom, 0px) + 18px))
      max(14px, env(safe-area-inset-left, 0px));
  }

  .hero-panel {
    padding: 26px 20px 20px;
    gap: 18px;
  }

  .form-panel {
    padding: 30px 20px 24px;
  }

  .form-head {
    margin-bottom: 22px;
  }

  .form-head h1 {
    font-size: 26px;
  }

  .form-tools,
  .endpoint-panel,
  .endpoint-input-row {
    align-items: stretch;
  }

  .form-tools {
    flex-direction: column;
    gap: 12px;
  }

  .endpoint-panel,
  .endpoint-input-row {
    grid-template-columns: 1fr;
  }

  .brand-mark {
    width: 52px;
    height: 52px;
    border-radius: 16px;
  }

  .motion-stage {
    min-height: 250px;
    border-radius: 22px;
  }

  .ring-one {
    width: 150px;
    height: 150px;
  }

  .ring-two {
    width: 220px;
    height: 220px;
  }

  .ring-three {
    width: 300px;
    height: 300px;
  }

  .stage-sweep {
    width: 340px;
    height: 340px;
  }

  .stage-orbit {
    width: 250px;
    height: 250px;
    margin: -125px 0 0 -125px;
  }

  .orbit-two {
    width: 320px;
    height: 320px;
    margin: -160px 0 0 -160px;
  }
}
</style>
