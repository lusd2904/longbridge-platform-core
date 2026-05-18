<template>
  <router-view />
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTheme } from './composables/useTheme.js'
import { getSession, getToken, setSession } from './utils/auth.js'
import { getPlatformBootstrap } from './api/platform.js'

const { applyTheme } = useTheme()
const router = useRouter()
const route = useRoute()

const shouldSurfaceSystemToast = () => {
  if (typeof window === 'undefined') {
    return true
  }
  return window.location.pathname !== '/login'
}

const handlePwaUpdate = async (event) => {
  const updateSW = event?.detail?.updateSW
  if (!updateSW) {
    return
  }

  try {
    await ElMessageBox.confirm('检测到新版本，是否立即刷新应用？', '应用更新', {
      confirmButtonText: '立即刷新',
      cancelButtonText: '稍后',
      type: 'info'
    })
    await updateSW(true)
  } catch {
    // 用户稍后处理即可
  }
}

const handleOfflineReady = () => {
  if (!shouldSurfaceSystemToast()) {
    return
  }
  ElMessage.success('离线缓存已就绪，常用页面支持更快打开')
}

const handlePwaError = () => {
  if (!shouldSurfaceSystemToast()) {
    return
  }
  ElMessage.warning('PWA 注册失败，已自动回退到普通网页模式')
}

const handleNativeExitHint = () => {
  ElMessage.info('再按一次返回键退出应用')
}

const normalizeHomePath = (value) => {
  const candidate = String(value || '').trim()
  if (!candidate || candidate === '/workspace') {
    return '/dashboard'
  }
  return candidate
}

onMounted(() => {
  applyTheme()

  router.isReady().then(() => {
    const currentPath = router.currentRoute.value.path
    const existingSession = getSession()

    if (existingSession && (currentPath === '/' || currentPath === '/workspace' || currentPath === '/dashboard')) {
      const homePath = normalizeHomePath(existingSession?.navigation?.homePath)
      router.replace(homePath).catch(() => {})
    }

    if (getToken() && !getSession()) {
      getPlatformBootstrap()
        .then((res) => {
          if (res?.data) {
            setSession(res.data)
            const readyPath = router.currentRoute.value.path
            const homePath = normalizeHomePath(res.data?.navigation?.homePath)
            if (readyPath === '/' || readyPath === '/workspace' || readyPath === '/dashboard') {
              router.replace(homePath).catch(() => {})
            }
          }
        })
        .catch(() => {})
    }
  })

  window.addEventListener('pwa-update-ready', handlePwaUpdate)
  window.addEventListener('pwa-offline-ready', handleOfflineReady)
  window.addEventListener('pwa-register-error', handlePwaError)
  window.addEventListener('native-exit-hint', handleNativeExitHint)
})

onUnmounted(() => {
  window.removeEventListener('pwa-update-ready', handlePwaUpdate)
  window.removeEventListener('pwa-offline-ready', handleOfflineReady)
  window.removeEventListener('pwa-register-error', handlePwaError)
  window.removeEventListener('native-exit-hint', handleNativeExitHint)
})
</script>

<style>
:root {
  --font-cjk:
    'PingFang SC',
    'Hiragino Sans GB',
    'Noto Sans CJK SC',
    'Microsoft YaHei',
    'Source Han Sans SC';
  --font-heading:
    'Inter',
    var(--font-cjk),
    -apple-system,
    BlinkMacSystemFont,
    'SF Pro Display',
    'Segoe UI',
    'Helvetica Neue',
    Arial,
    sans-serif;
  --font-body:
    'Inter',
    var(--font-cjk),
    -apple-system,
    BlinkMacSystemFont,
    'SF Pro Text',
    'Segoe UI',
    'Helvetica Neue',
    Arial,
    sans-serif;
  --el-font-family: var(--font-body);
  --sidebar-width: 260px;
  --radius-strong: 28px;
  --radius-soft: 20px;
  --page-grid:
    linear-gradient(135deg, rgba(255, 255, 255, 0.035), transparent 32%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 48%);
  --panel-highlight: linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.05));
  --panel-surface: var(--panel-highlight), var(--overlay-bg);
  --chrome-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0.05)), var(--overlay-bg);
  --shell-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02)), var(--workspace-shell-bg);
  --panel-backdrop: blur(24px) saturate(145%);
  --chrome-backdrop: blur(28px) saturate(150%);
  --shell-backdrop: none;
  --panel-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 8%, transparent);
  --chrome-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 9%, transparent);
  --shell-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 5%, transparent);
  --chrome-shadow: 0 12px 30px rgba(2, 10, 24, 0.24);
  --sidebar-shadow: 0 18px 44px rgba(3, 10, 24, 0.36);
  --button-primary-solid-bg: #164a72;
  --button-primary-solid-bg-hover: #1b628d;
  --button-primary-bg: linear-gradient(135deg, #164a72 0%, #0e5f83 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #1b628d 0%, #15739b 100%);
  --button-primary-text: #f9fdff;
  --button-primary-border: color-mix(in srgb, var(--accent) 34%, transparent);
  --button-primary-shadow: 0 16px 36px color-mix(in srgb, var(--accent-strong) 24%, transparent);
  --button-secondary-bg: color-mix(in srgb, var(--surface-soft) 84%, var(--surface-strong) 16%);
  --button-secondary-bg-hover: color-mix(in srgb, var(--surface-soft) 90%, var(--surface-strong) 10%);
  --button-secondary-text: var(--text-primary);
  --button-secondary-border: var(--border-soft);
  --button-link-color: color-mix(in srgb, var(--accent) 74%, var(--text-primary) 12%);
  --table-divider: color-mix(in srgb, var(--border-soft) 46%, transparent);
  --table-frame: color-mix(in srgb, var(--border-soft) 62%, transparent);
  --surface-panel: var(--panel-surface);
  --info: color-mix(in srgb, var(--accent-strong) 72%, white 16%);
  --safe-area-top: env(safe-area-inset-top, 0px);
  --safe-area-right: env(safe-area-inset-right, 0px);
  --safe-area-bottom: env(safe-area-inset-bottom, 0px);
  --safe-area-left: env(safe-area-inset-left, 0px);
}

:root,
:root[data-theme='liquid-night'] {
  --page-bg:
    radial-gradient(circle at 12% 18%, rgba(126, 231, 255, 0.22), transparent 28%),
    radial-gradient(circle at 86% 12%, rgba(255, 178, 138, 0.14), transparent 24%),
    radial-gradient(circle at 72% 82%, rgba(91, 161, 255, 0.18), transparent 26%),
    linear-gradient(180deg, #08101d 0%, #091325 38%, #06101b 100%);
  --glow-a: rgba(102, 208, 255, 0.26);
  --glow-b: rgba(255, 170, 134, 0.18);
  --surface-strong: rgba(12, 24, 46, 0.74);
  --surface-soft: rgba(255, 255, 255, 0.08);
  --surface-muted: rgba(255, 255, 255, 0.06);
  --surface-emphasis: rgba(13, 26, 49, 0.72);
  --overlay-bg: linear-gradient(160deg, rgba(14, 28, 50, 0.9), rgba(9, 18, 34, 0.8));
  --loading-mask: rgba(5, 11, 24, 0.48);
  --border-soft: rgba(255, 255, 255, 0.14);
  --border-strong: rgba(255, 255, 255, 0.2);
  --panel-stroke: rgba(255, 255, 255, 0.08);
  --shadow-strong: 0 24px 80px rgba(3, 11, 27, 0.4);
  --text-primary: #f5fbff;
  --text-secondary: rgba(226, 236, 255, 0.8);
  --text-muted: rgba(196, 213, 241, 0.58);
  --text-emphasis: #ffffff;
  --accent: #78e6ff;
  --accent-strong: #53b9ff;
  --success: #86efac;
  --danger: #ff9f9f;
  --warning: #ffd67d;
  --chart-axis: rgba(210, 225, 248, 0.7);
  --chart-grid: rgba(255, 255, 255, 0.1);
  --table-header-bg: rgba(255, 255, 255, 0.08);
  --table-row-hover: rgba(255, 255, 255, 0.05);
  --workspace-shell-bg: rgba(6, 14, 27, 0.26);
  --workspace-shell-border: rgba(255, 255, 255, 0.08);
  --panel-surface: var(--panel-highlight), var(--overlay-bg);
  --chrome-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0.05)), var(--overlay-bg);
  --shell-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02)), var(--workspace-shell-bg);
  --panel-backdrop: blur(24px) saturate(145%);
  --chrome-backdrop: blur(28px) saturate(150%);
  --shell-backdrop: blur(18px) saturate(132%);
}

:root[data-theme='neon-grid'] {
  --page-bg:
    linear-gradient(90deg, rgba(115, 255, 105, 0.08) 1px, transparent 1px),
    linear-gradient(180deg, rgba(21, 209, 255, 0.08) 1px, transparent 1px),
    radial-gradient(circle at 12% 18%, rgba(146, 255, 87, 0.18), transparent 26%),
    radial-gradient(circle at 88% 12%, rgba(72, 166, 255, 0.14), transparent 24%),
    linear-gradient(180deg, #070d1a 0%, #0b1121 42%, #060a13 100%);
  --glow-a: rgba(123, 255, 92, 0.22);
  --glow-b: rgba(55, 215, 255, 0.18);
  --surface-strong: #0d1626;
  --surface-soft: #111d31;
  --surface-muted: #0c1829;
  --surface-emphasis: #13233a;
  --overlay-bg: linear-gradient(180deg, #0e1726, #0a1422);
  --loading-mask: rgba(4, 10, 18, 0.8);
  --border-soft: rgba(111, 255, 99, 0.18);
  --border-strong: rgba(111, 255, 99, 0.3);
  --panel-stroke: rgba(69, 230, 255, 0.14);
  --shadow-strong: 0 24px 72px rgba(1, 7, 15, 0.46);
  --text-primary: #effef6;
  --text-secondary: rgba(224, 255, 240, 0.82);
  --text-muted: rgba(168, 219, 195, 0.58);
  --text-emphasis: #ffffff;
  --accent: #93ff5c;
  --accent-strong: #15d1ff;
  --success: #72f2b2;
  --danger: #ff7f96;
  --warning: #ffd16b;
  --chart-axis: rgba(206, 242, 230, 0.72);
  --chart-grid: rgba(79, 211, 255, 0.1);
  --table-header-bg: rgba(17, 29, 48, 0.98);
  --table-row-hover: rgba(23, 37, 58, 0.92);
  --panel-highlight: linear-gradient(180deg, rgba(147, 255, 92, 0.04), rgba(21, 209, 255, 0.02));
  --workspace-shell-bg: rgba(7, 14, 24, 0.9);
  --workspace-shell-border: rgba(93, 237, 219, 0.12);
  --panel-surface: linear-gradient(180deg, rgba(147, 255, 92, 0.04), transparent 18%), linear-gradient(145deg, #0f1828, #09111e);
  --chrome-surface: linear-gradient(145deg, #101a2b, #09111f);
  --shell-surface: linear-gradient(180deg, rgba(19, 33, 55, 0.94), rgba(8, 15, 25, 0.96));
  --panel-backdrop: none;
  --chrome-backdrop: none;
  --button-primary-bg: linear-gradient(135deg, #1c6d61 0%, #1696a7 48%, #7ee55b 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #21806f 0%, #1aa8ba 48%, #95f06e 100%);
  --button-primary-solid-bg: #14564f;
  --button-primary-solid-bg-hover: #1d6b60;
  --button-primary-bg: linear-gradient(135deg, #14564f 0%, #126474 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #1d6b60 0%, #19788a 100%);
  --button-primary-text: #f9fdff;
  --button-link-color: #97ff76;
}

:root[data-theme='vulcan-forge'] {
  --page-bg:
    radial-gradient(circle at 12% 18%, rgba(255, 170, 72, 0.18), transparent 26%),
    radial-gradient(circle at 86% 14%, rgba(255, 88, 70, 0.2), transparent 24%),
    radial-gradient(circle at 70% 82%, rgba(255, 210, 132, 0.1), transparent 20%),
    linear-gradient(180deg, #14100f 0%, #1a1210 44%, #0c0a0a 100%);
  --glow-a: rgba(255, 170, 72, 0.2);
  --glow-b: rgba(255, 99, 78, 0.18);
  --surface-strong: #1b1412;
  --surface-soft: #241916;
  --surface-muted: #171110;
  --surface-emphasis: #2a1e1a;
  --overlay-bg: linear-gradient(180deg, #211715, #16100f);
  --loading-mask: rgba(14, 9, 8, 0.82);
  --border-soft: rgba(255, 140, 92, 0.16);
  --border-strong: rgba(255, 140, 92, 0.28);
  --panel-stroke: rgba(255, 190, 112, 0.12);
  --shadow-strong: 0 24px 72px rgba(8, 4, 3, 0.5);
  --text-primary: #fff5ef;
  --text-secondary: rgba(255, 230, 217, 0.82);
  --text-muted: rgba(223, 177, 154, 0.56);
  --text-emphasis: #fffdf9;
  --accent: #ffcc6b;
  --accent-strong: #ff5b4d;
  --success: #7be0a2;
  --danger: #ff8a7a;
  --warning: #ffd36e;
  --chart-axis: rgba(255, 221, 205, 0.72);
  --chart-grid: rgba(255, 181, 121, 0.1);
  --table-header-bg: rgba(40, 28, 24, 0.98);
  --table-row-hover: rgba(50, 35, 29, 0.92);
  --panel-highlight: linear-gradient(180deg, rgba(255, 175, 81, 0.06), rgba(255, 91, 77, 0.03));
  --workspace-shell-bg: rgba(16, 10, 9, 0.92);
  --workspace-shell-border: rgba(255, 157, 108, 0.12);
  --panel-surface: linear-gradient(180deg, rgba(255, 175, 81, 0.05), transparent 18%), linear-gradient(145deg, #241917, #15100f);
  --chrome-surface: linear-gradient(145deg, #281b18, #15100f);
  --shell-surface: linear-gradient(180deg, rgba(39, 24, 20, 0.96), rgba(16, 10, 9, 0.98));
  --panel-backdrop: none;
  --chrome-backdrop: none;
  --button-primary-bg: linear-gradient(135deg, #8a301d 0%, #c44f2b 46%, #efb14c 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #9c3821 0%, #db5f32 46%, #f5c060 100%);
  --button-primary-solid-bg: #703221;
  --button-primary-solid-bg-hover: #86402a;
  --button-link-color: #ffbe76;
}

:root[data-theme='emerald-core'] {
  --page-bg:
    radial-gradient(circle at 12% 16%, rgba(56, 240, 179, 0.2), transparent 24%),
    radial-gradient(circle at 86% 14%, rgba(15, 167, 126, 0.18), transparent 24%),
    radial-gradient(circle at 74% 84%, rgba(130, 255, 221, 0.08), transparent 18%),
    linear-gradient(180deg, #061310 0%, #081b17 42%, #030b09 100%);
  --glow-a: rgba(56, 240, 179, 0.2);
  --glow-b: rgba(90, 255, 206, 0.16);
  --surface-strong: #0b1c18;
  --surface-soft: #112621;
  --surface-muted: #0c1815;
  --surface-emphasis: #14302a;
  --overlay-bg: linear-gradient(180deg, #10231e, #091714);
  --loading-mask: rgba(4, 10, 8, 0.8);
  --border-soft: rgba(82, 255, 197, 0.15);
  --border-strong: rgba(82, 255, 197, 0.26);
  --panel-stroke: rgba(90, 235, 188, 0.12);
  --shadow-strong: 0 24px 72px rgba(1, 8, 6, 0.48);
  --text-primary: #eefdf7;
  --text-secondary: rgba(221, 247, 239, 0.82);
  --text-muted: rgba(160, 206, 189, 0.56);
  --text-emphasis: #ffffff;
  --accent: #38f0b3;
  --accent-strong: #0fa77e;
  --success: #6ff1c2;
  --danger: #ff8aa0;
  --warning: #f9d86c;
  --chart-axis: rgba(209, 237, 229, 0.72);
  --chart-grid: rgba(88, 228, 174, 0.1);
  --table-header-bg: rgba(20, 42, 36, 0.98);
  --table-row-hover: rgba(23, 50, 42, 0.9);
  --panel-highlight: linear-gradient(180deg, rgba(56, 240, 179, 0.05), rgba(255, 255, 255, 0.01));
  --workspace-shell-bg: rgba(6, 17, 14, 0.92);
  --workspace-shell-border: rgba(87, 245, 180, 0.11);
  --panel-surface: linear-gradient(180deg, rgba(56, 240, 179, 0.05), transparent 18%), linear-gradient(145deg, #11231e, #091512);
  --chrome-surface: linear-gradient(145deg, #122922, #081411);
  --shell-surface: linear-gradient(180deg, rgba(20, 43, 36, 0.96), rgba(6, 17, 14, 0.98));
  --panel-backdrop: none;
  --chrome-backdrop: none;
  --button-primary-bg: linear-gradient(135deg, #0e6550 0%, #169e7a 48%, #39d9aa 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #11745a 0%, #18ae86 48%, #4ce6b8 100%);
  --button-primary-solid-bg: #0f5f4c;
  --button-primary-solid-bg-hover: #14745c;
  --button-link-color: #58f0c0;
}

:root[data-theme='cobalt-strike'] {
  --page-bg:
    radial-gradient(circle at 10% 16%, rgba(113, 184, 255, 0.2), transparent 24%),
    radial-gradient(circle at 86% 12%, rgba(27, 92, 255, 0.22), transparent 24%),
    radial-gradient(circle at 72% 82%, rgba(102, 140, 255, 0.12), transparent 20%),
    linear-gradient(180deg, #07111d 0%, #0b1526 40%, #050b14 100%);
  --glow-a: rgba(113, 184, 255, 0.22);
  --glow-b: rgba(27, 92, 255, 0.2);
  --surface-strong: #0d192c;
  --surface-soft: #14223a;
  --surface-muted: #0d1628;
  --surface-emphasis: #1a2b46;
  --overlay-bg: linear-gradient(180deg, #10203a, #0a1528);
  --loading-mask: rgba(4, 9, 18, 0.8);
  --border-soft: rgba(123, 177, 255, 0.16);
  --border-strong: rgba(123, 177, 255, 0.28);
  --panel-stroke: rgba(88, 143, 255, 0.12);
  --shadow-strong: 0 24px 72px rgba(1, 7, 18, 0.5);
  --text-primary: #f1f7ff;
  --text-secondary: rgba(224, 235, 255, 0.82);
  --text-muted: rgba(164, 183, 216, 0.58);
  --text-emphasis: #ffffff;
  --accent: #71b8ff;
  --accent-strong: #1b5cff;
  --success: #7ce7c6;
  --danger: #ff91a6;
  --warning: #ffd36e;
  --chart-axis: rgba(214, 226, 245, 0.72);
  --chart-grid: rgba(101, 150, 255, 0.1);
  --table-header-bg: rgba(20, 35, 56, 0.98);
  --table-row-hover: rgba(25, 43, 69, 0.92);
  --panel-highlight: linear-gradient(180deg, rgba(113, 184, 255, 0.05), rgba(255, 255, 255, 0.01));
  --workspace-shell-bg: rgba(7, 14, 24, 0.92);
  --workspace-shell-border: rgba(112, 169, 255, 0.12);
  --panel-surface: linear-gradient(180deg, rgba(113, 184, 255, 0.05), transparent 18%), linear-gradient(145deg, #112037, #091421);
  --chrome-surface: linear-gradient(145deg, #13233e, #09131f);
  --shell-surface: linear-gradient(180deg, rgba(20, 38, 64, 0.96), rgba(7, 14, 24, 0.98));
  --panel-backdrop: none;
  --chrome-backdrop: none;
  --button-primary-bg: linear-gradient(135deg, #193d9c 0%, #2467d7 52%, #63acff 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #2152bf 0%, #2d79ef 52%, #7bbcfe 100%);
  --button-primary-solid-bg: #193d9c;
  --button-primary-solid-bg-hover: #2152bf;
  --button-link-color: #8fc4ff;
}

:root[data-theme='obsidian-crown'] {
  --page-bg:
    radial-gradient(circle at 14% 16%, rgba(246, 208, 119, 0.14), transparent 22%),
    radial-gradient(circle at 86% 14%, rgba(184, 136, 42, 0.16), transparent 22%),
    linear-gradient(180deg, #111214 0%, #17181c 40%, #09090b 100%);
  --glow-a: rgba(246, 208, 119, 0.18);
  --glow-b: rgba(190, 145, 56, 0.12);
  --surface-strong: #17181d;
  --surface-soft: #202228;
  --surface-muted: #17191d;
  --surface-emphasis: #2a2d34;
  --overlay-bg: linear-gradient(180deg, #1d1f24, #14161a);
  --loading-mask: rgba(9, 9, 11, 0.84);
  --border-soft: rgba(232, 198, 112, 0.14);
  --border-strong: rgba(232, 198, 112, 0.24);
  --panel-stroke: rgba(217, 180, 96, 0.1);
  --shadow-strong: 0 24px 72px rgba(0, 0, 0, 0.46);
  --text-primary: #fff8ec;
  --text-secondary: rgba(245, 234, 210, 0.82);
  --text-muted: rgba(192, 176, 145, 0.56);
  --text-emphasis: #fffdf9;
  --accent: #f6d077;
  --accent-strong: #b8882a;
  --success: #8de0b1;
  --danger: #ff9aa7;
  --warning: #f7d578;
  --chart-axis: rgba(229, 220, 199, 0.72);
  --chart-grid: rgba(214, 181, 103, 0.1);
  --table-header-bg: rgba(32, 34, 40, 0.98);
  --table-row-hover: rgba(38, 40, 46, 0.92);
  --panel-highlight: linear-gradient(180deg, rgba(246, 208, 119, 0.04), rgba(255, 255, 255, 0.01));
  --workspace-shell-bg: rgba(12, 12, 14, 0.94);
  --workspace-shell-border: rgba(225, 190, 109, 0.1);
  --panel-surface: linear-gradient(180deg, rgba(246, 208, 119, 0.04), transparent 18%), linear-gradient(145deg, #202228, #131418);
  --chrome-surface: linear-gradient(145deg, #23252b, #141519);
  --shell-surface: linear-gradient(180deg, rgba(35, 36, 42, 0.96), rgba(12, 12, 14, 0.98));
  --panel-backdrop: none;
  --chrome-backdrop: none;
  --button-primary-bg: linear-gradient(135deg, #76511a 0%, #9f7223 48%, #c39a46 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #866025 0%, #b5832c 48%, #d4ac57 100%);
  --button-primary-solid-bg: #76511a;
  --button-primary-solid-bg-hover: #866025;
  --button-primary-text: #fffaf0;
  --button-link-color: #f1cb78;
}

:root[data-theme='solar-tide'] {
  --page-bg:
    radial-gradient(circle at 10% 16%, rgba(255, 205, 122, 0.18), transparent 26%),
    radial-gradient(circle at 88% 12%, rgba(255, 135, 98, 0.18), transparent 22%),
    radial-gradient(circle at 72% 80%, rgba(149, 118, 255, 0.18), transparent 24%),
    linear-gradient(180deg, #120d20 0%, #1a132b 30%, #0c1320 100%);
  --glow-a: rgba(255, 205, 122, 0.22);
  --glow-b: rgba(255, 135, 98, 0.18);
  --surface-strong: rgba(30, 20, 44, 0.72);
  --surface-soft: rgba(255, 244, 229, 0.08);
  --surface-muted: rgba(255, 255, 255, 0.05);
  --surface-emphasis: rgba(37, 23, 49, 0.68);
  --overlay-bg: linear-gradient(160deg, rgba(44, 23, 54, 0.9), rgba(17, 25, 40, 0.78));
  --loading-mask: rgba(13, 10, 24, 0.52);
  --border-soft: rgba(255, 221, 188, 0.14);
  --border-strong: rgba(255, 229, 189, 0.22);
  --panel-stroke: rgba(255, 221, 188, 0.1);
  --shadow-strong: 0 24px 80px rgba(11, 9, 24, 0.46);
  --text-primary: #fff9f1;
  --text-secondary: rgba(255, 233, 215, 0.82);
  --text-muted: rgba(242, 206, 184, 0.62);
  --text-emphasis: #fffdf9;
  --accent: #ffd784;
  --accent-strong: #ff9f6b;
  --success: #8ff0b9;
  --danger: #ff9e96;
  --warning: #ffe18b;
  --chart-axis: rgba(255, 229, 205, 0.74);
  --chart-grid: rgba(255, 228, 205, 0.1);
  --table-header-bg: rgba(255, 241, 227, 0.08);
  --table-row-hover: rgba(255, 241, 227, 0.05);
  --panel-surface: var(--panel-highlight), var(--overlay-bg);
  --chrome-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0.05)), var(--overlay-bg);
  --shell-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02)), var(--workspace-shell-bg);
  --panel-backdrop: blur(24px) saturate(145%);
  --chrome-backdrop: blur(28px) saturate(150%);
  --shell-backdrop: blur(18px) saturate(132%);
}

:root {
  --border-soft: color-mix(in srgb, var(--accent-strong) 10%, transparent);
  --border-strong: color-mix(in srgb, var(--accent-strong) 16%, transparent);
  --panel-stroke: color-mix(in srgb, var(--accent-strong) 7%, transparent);
  --panel-edge: color-mix(in srgb, var(--accent-strong) 11%, transparent);
  --control-border: color-mix(in srgb, var(--accent-strong) 13%, transparent);
  --control-border-hover: color-mix(in srgb, var(--accent-strong) 22%, transparent);
  --table-divider: color-mix(in srgb, var(--accent-strong) 7%, transparent);
  --table-frame: color-mix(in srgb, var(--accent-strong) 11%, transparent);
  --button-secondary-border: color-mix(in srgb, var(--accent-strong) 12%, transparent);
  --el-color-primary: var(--accent-strong);
  --el-color-success: var(--success);
  --el-color-warning: var(--warning);
  --el-color-danger: var(--danger);
  --el-text-color-primary: var(--text-primary);
  --el-text-color-regular: color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary) 22%);
  --el-text-color-secondary: var(--text-secondary);
  --el-text-color-placeholder: color-mix(in srgb, var(--text-secondary) 82%, transparent);
  --el-border-color: var(--control-border);
  --el-border-color-light: var(--panel-edge);
  --el-border-color-lighter: color-mix(in srgb, var(--panel-edge) 76%, transparent);
  --el-fill-color-blank: var(--surface-muted);
  --el-fill-color-light: var(--surface-soft);
  --el-fill-color-lighter: var(--surface-muted);
  --el-fill-color-dark: color-mix(in srgb, var(--surface-emphasis) 92%, transparent);
  --el-fill-color: color-mix(in srgb, var(--surface-soft) 72%, var(--surface-muted) 28%);
  --el-fill-color-darker: color-mix(in srgb, var(--surface-emphasis) 88%, transparent);
  --el-bg-color: transparent;
  --el-bg-color-page: transparent;
  --el-bg-color-overlay: var(--surface-strong);
  --el-color-white: var(--text-emphasis);
  --el-box-shadow-light: var(--shadow-strong);
  --el-mask-color: var(--loading-mask);
  --el-mask-color-extra-light: color-mix(in srgb, var(--loading-mask) 68%, transparent);
  --el-overlay-color-light: color-mix(in srgb, var(--loading-mask) 92%, transparent);
  --el-overlay-color-lighter: var(--loading-mask);
  --el-disabled-bg-color: var(--surface-muted);
  --el-disabled-text-color: color-mix(in srgb, var(--text-secondary) 74%, transparent);
  --el-border-radius-base: 10px;
  --el-border-radius-small: 8px;
  --el-border-radius-round: 999px;
}

:root,
:root[data-theme] {
  --el-color-info: var(--text-secondary) !important;
  --el-color-primary: var(--accent-strong) !important;
  --el-color-success: var(--success) !important;
  --el-color-warning: var(--warning) !important;
  --el-color-danger: var(--danger) !important;
  --el-text-color-primary: var(--text-primary) !important;
  --el-text-color-regular: color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary) 22%) !important;
  --el-text-color-secondary: var(--text-secondary) !important;
  --el-text-color-placeholder: color-mix(in srgb, var(--text-secondary) 82%, transparent) !important;
  --el-disabled-text-color: color-mix(in srgb, var(--text-secondary) 74%, transparent) !important;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
}

html {
  height: 100%;
  overflow-x: hidden;
  background: #08101d;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

body {
  margin: 0;
  font-family: var(--font-body);
  color: var(--text-primary);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-strong) 72%, black 28%), color-mix(in srgb, var(--surface-emphasis) 76%, black 24%)),
    var(--page-bg);
  background-attachment: scroll;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: auto;
  touch-action: pan-y pinch-zoom;
  -webkit-overflow-scrolling: touch;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

input,
button,
textarea,
select {
  font: inherit;
}

body::before,
body::after {
  content: none;
  position: fixed;
  inset: auto;
  width: 28vw;
  height: 28vw;
  border-radius: 999px;
  filter: blur(80px);
  opacity: 0.34;
  pointer-events: none;
  z-index: 0;
}

body::before {
  top: -10vw;
  right: -6vw;
  background: var(--glow-a);
}

body::after {
  left: -10vw;
  bottom: -14vw;
  background: var(--glow-b);
}

h1,
h2,
h3,
h4,
h5,
h6 {
  font-family: var(--font-heading);
  letter-spacing: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

::selection {
  background: color-mix(in srgb, var(--accent-strong) 30%, transparent);
  color: var(--text-emphasis);
}

#app {
  position: relative;
  z-index: 1;
  min-height: 100%;
  height: auto;
}

.native-platform body,
body.native-platform {
  -webkit-tap-highlight-color: transparent;
}

input,
select,
textarea {
  font-size: 16px;
}

@media (max-width: 1180px) {
  body {
    background-attachment: scroll, scroll;
  }

  body::before,
  body::after {
    width: 52vw;
    height: 52vw;
    opacity: 0.28;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
  }

  .page-header > *,
  .header-actions > *,
  .card-actions > * {
    min-width: 0;
  }

  .header-actions,
  .card-actions {
    display: flex;
    flex-wrap: wrap;
    width: 100%;
    gap: 10px;
  }

  .header-actions .el-input,
  .header-actions .el-input-number,
  .header-actions .el-select,
  .header-actions .el-date-editor,
  .header-actions .el-button,
  .header-actions .el-button-group,
  .card-actions .el-input,
  .card-actions .el-input-number,
  .card-actions .el-select,
  .card-actions .el-date-editor,
  .card-actions .el-button,
  .card-actions .el-button-group {
    width: 100% !important;
  }

  .el-dialog {
    width: min(92vw, 560px) !important;
    margin: max(16px, var(--safe-area-top)) auto !important;
  }

  .el-table,
  .el-tabs__header,
  .el-scrollbar__wrap,
  .el-table__body-wrapper,
  .el-table__header-wrapper {
    -webkit-overflow-scrolling: touch;
  }

  .el-table__body-wrapper,
  .el-table__header-wrapper,
  .el-scrollbar__wrap {
    overflow-x: auto !important;
  }

  .el-drawer {
    max-width: calc(100vw - 16px);
  }

  .el-pagination {
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .page-header {
    gap: 12px;
  }

  .page-header .el-card__body,
  .page-header .el-card__header {
    padding-inline: 14px;
  }

  .el-card__body {
    padding: 16px;
  }

  .el-message-box {
    width: calc(100vw - 24px) !important;
  }
}

body.native-keyboard-open .mobile-nav {
  opacity: 0;
  pointer-events: none;
  transform: translateY(calc(100% + 24px));
}

.el-button {
  border-radius: 10px;
  font-weight: 700;
}

.el-button--primary:not(.is-link):not(.is-text) {
  color: var(--button-primary-text) !important;
  border: 1px solid var(--button-primary-border);
  background-color: var(--button-primary-solid-bg) !important;
  background-image: var(--button-primary-bg) !important;
  box-shadow: var(--button-primary-shadow);
}

.el-button--primary:not(.is-link):not(.is-text):hover,
.el-button--primary:not(.is-link):not(.is-text):focus-visible,
.el-button--primary:not(.is-link):not(.is-text):active {
  color: var(--button-primary-text) !important;
  border-color: var(--button-primary-border);
  background-color: var(--button-primary-solid-bg-hover) !important;
  background-image: var(--button-primary-bg-hover) !important;
}

.el-button.is-text:not(.is-link),
.el-button--default:not(.is-link):not(.is-text) {
  color: var(--button-secondary-text);
  background: var(--button-secondary-bg);
  border-color: var(--button-secondary-border);
}

.el-button.is-text:not(.is-link):hover,
.el-button--default:not(.is-link):not(.is-text):hover,
.el-button--default:not(.is-link):not(.is-text):focus-visible {
  color: var(--button-secondary-text);
  background: var(--button-secondary-bg-hover);
  border-color: var(--control-border-hover);
}

.el-button--primary.is-link,
.el-link.el-link--primary {
  color: var(--button-link-color) !important;
}

.el-button--success.is-link,
.el-link.el-link--success {
  color: var(--success) !important;
}

.el-button--warning.is-link,
.el-link.el-link--warning {
  color: var(--warning) !important;
}

.el-button--danger.is-link,
.el-link.el-link--danger {
  color: var(--danger) !important;
}

.el-button--info.is-link,
.el-link.el-link--info {
  color: var(--text-secondary) !important;
}

.el-button--success:not(.is-link):not(.is-text) {
  color: #052016 !important;
  background-color: #86efac !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--success) 86%, white 14%), color-mix(in srgb, var(--success) 72%, var(--accent) 12%)) !important;
  border-color: color-mix(in srgb, var(--success) 48%, transparent) !important;
}

.el-button--warning:not(.is-link):not(.is-text) {
  color: #241704 !important;
  background-color: #ffd67d !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--warning) 88%, white 12%), color-mix(in srgb, var(--warning) 72%, var(--accent) 10%)) !important;
  border-color: color-mix(in srgb, var(--warning) 48%, transparent) !important;
}

.el-button--danger:not(.is-link):not(.is-text) {
  color: #2a0608 !important;
  background-color: #ff9f9f !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--danger) 88%, white 12%), color-mix(in srgb, var(--danger) 76%, var(--warning) 8%)) !important;
  border-color: color-mix(in srgb, var(--danger) 48%, transparent) !important;
}

.el-input-group__append .el-button,
.el-input-group__prepend .el-button {
  color: var(--text-primary) !important;
  background-color: rgba(20, 38, 64, 0.96) !important;
  background-image: none !important;
  border-color: var(--control-border) !important;
}

.el-button.is-plain.is-disabled,
.el-button.is-disabled,
.el-button.is-disabled span {
  color: color-mix(in srgb, var(--text-secondary) 78%, transparent) !important;
}

.el-card,
.el-table,
.el-dialog,
.el-tabs--border-card,
.el-drawer,
.el-message-box,
.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-notification,
.el-message {
  background: transparent !important;
  color: var(--text-primary);
}

.el-dropdown__popper.el-popper,
.el-select__popper.el-popper,
.el-picker__popper.el-popper,
.el-tooltip__popper.el-popper,
.el-popover.el-popper,
.el-cascader__dropdown.el-popper {
  padding: 0 !important;
  overflow: hidden;
  border-radius: 12px !important;
  border: 1px solid var(--panel-edge) !important;
  background: var(--panel-surface) !important;
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.el-dropdown__popper.el-popper > .el-popper__arrow:before,
.el-select__popper.el-popper > .el-popper__arrow:before,
.el-picker__popper.el-popper > .el-popper__arrow:before,
.el-tooltip__popper.el-popper > .el-popper__arrow:before,
.el-popover.el-popper > .el-popper__arrow:before,
.el-cascader__dropdown.el-popper > .el-popper__arrow:before {
  background: color-mix(in srgb, var(--surface-emphasis) 96%, transparent) !important;
  border-color: var(--panel-edge) !important;
}

.el-card,
.el-dialog,
.el-dialog__body,
.el-drawer,
.el-message-box,
.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-notification,
.el-message {
  border-radius: 10px !important;
  border: 1px solid var(--panel-edge) !important;
  background: var(--panel-surface) !important;
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-tooltip__popper.el-popper {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
}

.el-dropdown__list,
.el-select-dropdown__list,
.el-cascader-menu,
.el-picker-panel__content,
.el-date-range-picker__content {
  background: transparent !important;
}

.el-card__header,
.el-card__body,
.el-dialog__header,
.el-dialog__body,
.el-dialog__footer {
  color: var(--text-primary);
  border-color: var(--panel-stroke) !important;
}

.el-input__wrapper,
.el-select__wrapper,
.el-textarea__inner,
.el-input-number,
.el-input-number__decrease,
.el-input-number__increase,
.el-radio-button__inner,
.el-tabs--border-card,
.el-pagination button,
.el-pager li,
.el-date-editor,
.el-date-editor .el-range-input {
  background: var(--surface-soft) !important;
  box-shadow: inset 0 0 0 1px var(--control-border) !important;
  color: var(--text-primary) !important;
}

.el-pagination .btn-prev,
.el-pagination .btn-next,
.el-pagination .el-pager li,
.el-pagination button:disabled {
  border-color: var(--control-border) !important;
}

.el-input__inner,
.el-textarea__inner,
.el-input__inner::placeholder,
.el-textarea__inner::placeholder,
.el-input-number__input {
  color: var(--text-primary) !important;
  -webkit-text-fill-color: var(--text-primary) !important;
}

.el-input__wrapper.is-focus,
.el-select__wrapper.is-focused {
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent),
    0 12px 32px color-mix(in srgb, var(--accent-strong) 18%, transparent) !important;
}

.el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-border-color: var(--table-frame);
  --el-table-header-bg-color: var(--table-header-bg);
  --el-table-row-hover-bg-color: var(--table-row-hover);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
  --el-fill-color-lighter: var(--surface-soft);
  color: var(--text-primary) !important;
}

.el-table td.el-table__cell,
.el-table th.el-table__cell {
  border-bottom-color: var(--table-divider) !important;
}

.el-table th.el-table__cell,
.el-table tr,
.el-table td.el-table__cell,
.el-table__body-wrapper,
.el-table__header-wrapper {
  background: transparent !important;
}

.el-table th.el-table__cell {
  background: var(--table-header-bg) !important;
}

.el-table__inner-wrapper::before {
  background-color: var(--table-frame) !important;
}

.el-table--border::before,
.el-table--border::after,
.el-table--group::after,
.el-table__border-left-patch {
  background-color: var(--table-frame) !important;
}

.el-descriptions {
  --el-descriptions-table-border: var(--panel-stroke);
  color: var(--text-primary) !important;
}

.el-descriptions__body,
.el-descriptions__table,
.el-descriptions__cell {
  border-color: var(--panel-stroke) !important;
  background: transparent !important;
  color: var(--text-primary) !important;
}

.el-descriptions__label.el-descriptions__cell,
.el-descriptions__label {
  background: color-mix(in srgb, var(--surface-soft) 90%, var(--surface-emphasis) 10%) !important;
  color: var(--text-secondary) !important;
  font-weight: 700;
}

.el-descriptions__content.el-descriptions__cell,
.el-descriptions__content {
  background: color-mix(in srgb, var(--surface-muted) 88%, transparent) !important;
  color: var(--text-primary) !important;
}

.el-result {
  --el-result-title-font-size: 18px;
  --el-result-subtitle-font-size: 13px;
}

.el-result__title,
.el-result__title p,
.el-result__subtitle,
.el-result__subtitle p {
  color: var(--text-primary) !important;
}

.el-result__subtitle {
  color: var(--text-secondary) !important;
}

.el-dialog :where(p, span, small, strong, label, div),
.el-message-box :where(p, span, small, strong, label, div) {
  color: inherit;
}

.el-descriptions__label,
.el-descriptions__content,
.el-dialog__title,
.el-drawer__title,
.el-message-box__title,
.el-message-box__content,
.el-dropdown-menu__item,
.el-select-dropdown__item,
.el-checkbox__label,
.el-radio__label,
.el-form-item__label,
.el-empty__description p {
  color: var(--text-primary) !important;
}

.el-timeline {
  --el-timeline-node-color: color-mix(in srgb, var(--text-secondary) 46%, var(--panel-edge));
  color: var(--text-primary) !important;
}

.el-timeline-item {
  padding-bottom: 14px !important;
}

.el-timeline-item__content {
  color: var(--text-primary) !important;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.el-timeline-item__timestamp {
  color: var(--text-secondary) !important;
  font-size: 12px;
  line-height: 1.35 !important;
}

.el-timeline-item__tail {
  border-left-color: color-mix(in srgb, var(--text-secondary) 48%, transparent) !important;
}

.el-timeline-item__node {
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 12%, transparent);
}

.el-text,
.el-statistic__head,
.el-step__description,
.el-upload__tip,
.el-form-item__error,
.el-checkbox__label,
.el-radio__label,
.el-input__count,
.el-select-dropdown__empty,
.el-table__empty-text,
.el-empty__description {
  color: var(--text-secondary) !important;
}

.el-statistic__content,
.el-step__title,
.el-collapse-item__header,
.el-collapse-item__content,
.el-tabs__item {
  color: var(--text-primary) !important;
}

.el-dropdown-menu__item:hover,
.el-select-dropdown__item.hover,
.el-select-dropdown__item:hover {
  background: var(--surface-soft) !important;
}

.el-select-dropdown__item.selected {
  color: var(--accent) !important;
}

.el-dialog__headerbtn .el-dialog__close,
.el-message-box__headerbtn .el-message-box__close {
  color: var(--text-secondary) !important;
}

.el-dialog__headerbtn:hover .el-dialog__close,
.el-message-box__headerbtn:hover .el-message-box__close {
  color: var(--text-primary) !important;
}

.el-overlay,
.el-overlay-dialog {
  background: transparent !important;
}

.el-loading-mask {
  background: var(--loading-mask) !important;
  backdrop-filter: blur(18px);
}

.el-skeleton__item {
  background:
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--surface-muted) 88%, transparent),
      color-mix(in srgb, var(--surface-soft) 90%, var(--accent-strong) 4%),
      color-mix(in srgb, var(--surface-muted) 88%, transparent)
    ) !important;
  background-size: 220% 100% !important;
}

.el-divider {
  border-color: var(--panel-stroke) !important;
}

.el-progress-bar__outer {
  background: var(--surface-muted) !important;
}

.el-tag {
  border-radius: 999px;
  border-color: transparent !important;
}

.el-tag--primary {
  background: color-mix(in srgb, var(--accent-strong) 26%, transparent) !important;
  color: color-mix(in srgb, var(--text-primary) 86%, var(--accent) 14%) !important;
}

.el-tag--success {
  background: color-mix(in srgb, var(--success) 18%, transparent) !important;
  color: var(--success) !important;
}

.el-tag--danger {
  background: color-mix(in srgb, var(--danger) 18%, transparent) !important;
  color: var(--danger) !important;
}

.el-tag--warning {
  background: color-mix(in srgb, var(--warning) 18%, transparent) !important;
  color: var(--warning) !important;
}

.el-tag--info {
  background: color-mix(in srgb, var(--text-secondary) 18%, transparent) !important;
  color: var(--text-secondary) !important;
}

.page-header h2,
.card-header,
.symbol,
.price,
.value {
  color: var(--text-primary);
}
</style>
