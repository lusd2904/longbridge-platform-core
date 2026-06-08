import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'

const serviceUrl = (env, key, fallback) => `http://127.0.0.1:${env[key] || fallback}`

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const webPort = Number(env.REF_WEB_PORTAL_PORT || 3100)
  const isTest = process.env.VITEST === 'true'

  const manualChunks = (id) => {
    if (!id.includes('node_modules')) {
      return undefined
    }

    if (id.includes('echarts') || id.includes('zrender') || id.includes('vue-echarts')) {
      return 'vendor-charts'
    }

    if (
      id.includes('@floating-ui') ||
      id.includes('@ctrl/tinycolor')
    ) {
      return 'vendor-ui-utils'
    }

    if (id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia')) {
      return 'vendor-vue'
    }

    return undefined
  }

  return {
    plugins: [
      vue(),
      Components({
        dts: false,
        resolvers: [
          ElementPlusResolver({
            importStyle: isTest ? false : 'css'
          })
        ]
      })
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    css: {
      devSourcemap: true,
      preprocessorOptions: {
        scss: {
          additionalData: '@use "@/styles/variables.scss" as *;'
        }
      }
    },
    server: {
      host: '0.0.0.0',
      port: webPort,
      strictPort: true,
      cors: true,
      hmr: { overlay: false },
      proxy: {
        '/svc/user': {
          target: serviceUrl(env, 'REF_USER_CENTER_PORT', 8101),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/user/, '')
        },
        '/svc/market/ws': {
          target: serviceUrl(env, 'REF_MARKET_SERVICE_PORT', 8102),
          changeOrigin: true,
          ws: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/market/, '')
        },
        '/svc/market': {
          target: serviceUrl(env, 'REF_MARKET_SERVICE_PORT', 8102),
          changeOrigin: true,
          ws: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/market/, '')
        },
        '/svc/analysis': {
          target: serviceUrl(env, 'REF_ANALYSIS_SERVICE_PORT', 8103),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/analysis/, '')
        },
        '/svc/strategy': {
          target: serviceUrl(env, 'REF_STRATEGY_SERVICE_PORT', 8104),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/strategy/, '')
        },
        '/svc/trade/ws': {
          target: serviceUrl(env, 'REF_TRADE_SERVICE_PORT', 8105),
          changeOrigin: true,
          ws: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/trade/, '')
        },
        '/svc/trade': {
          target: serviceUrl(env, 'REF_TRADE_SERVICE_PORT', 8105),
          changeOrigin: true,
          ws: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/trade/, '')
        },
        '/svc/risk': {
          target: serviceUrl(env, 'REF_RISK_SERVICE_PORT', 8108),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/risk/, '')
        },
        '/svc/scheduler': {
          target: serviceUrl(env, 'REF_SCHEDULER_SERVICE_PORT', 8107),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/scheduler/, '')
        },
        '/svc/gateway': {
          target: serviceUrl(env, 'REF_GATEWAY_PORT', 5101),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/gateway/, '')
        },
        '/svc/sentiment': {
          target: serviceUrl(env, 'REF_SENTIMENT_SERVICE_PORT', 8106),
          changeOrigin: true,
          rewrite: (rawPath) => rawPath.replace(/^\/svc\/sentiment/, '')
        }
      }
    },
    preview: {
      host: '0.0.0.0',
      port: 4100
    },
    build: {
      sourcemap: false,
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        output: {
          manualChunks
        }
      }
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['tests/unit/**/*.spec.js']
    }
  }
})
