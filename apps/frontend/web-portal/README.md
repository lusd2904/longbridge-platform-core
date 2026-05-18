# Web Portal

职责：

- 新版统一前端入口
- 用户视角页面编排
- 分析、交易、策略、风控页面整合

迁移来源：

- `web/src/`

当前状态：

- 已可在 `3100` 启动
- 已接入 `user-center` / `market-service` / `analysis-service` / `strategy-service` / `trade-service` / `scheduler-service` / `risk-service` / `api-gateway`
- 当前已落地登录页、重构工作台、市场页、分析页、策略页、交易页、个人中心、调度页、风控页、通知页
- 后续继续扩展为更完整的策略编排、跨服务调度和用户中心视图
- 已接入 Capacitor，可生成 Android / iOS 原生壳；iOS 工程默认使用 Swift

当前路由：

- `/login`
- `/dashboard`
- `/trading`
- `/positions`
- `/orders`
- `/stock-pool`
- `/symbol/:symbol`
- `/ai-analysis`
- `/strategy`
- `/backtest`
- `/risk`
- `/market`
- `/kline`
- `/recommendations`
- `/finance-news`
- `/profile`
- `/broker-management`
- `/notifications`
- `/settings`
- `/user-management`
- `/scheduler-center`

移动端目录：

- Android 原生工程：`apps/web-portal/android/`
- iOS 原生工程：`apps/web-portal/ios/`

常用命令：

- `npm run assets:generate`
- `npm run mobile:prepare`
- `npm run mobile:build`
- `npm run android:add`
- `npm run ios:add`
- `npm run cap:sync`
- `npm run android:open`
- `npm run ios:open`
- `npm run android:build`
- `npm run android:debug`
- `npm run ios:build`
- `npm run ios:debug`
- `npm run ios:preflight`
- `npm run android:release`
- `npm run ios:archive`
- `npm run ios:export:ipa`
- `npm run trade:regression`
- `npm run verify:platform`
- `npm run mobile:debug`
- `npm run mobile:release`

原生增强：

- 已接入 Android 返回键处理、状态栏样式同步、键盘弹出时底部导航避让
- Android / iOS / macOS 都会根据容器自动走对应的接口基地址，并优先复用统一的 `VITE_NATIVE_API_BASE_URL`

联调说明：

- Android 模拟器默认请求 `http://10.0.2.2:3100`
- iOS 模拟器默认请求 `http://127.0.0.1:3100`
- macOS Electron 默认请求 `http://127.0.0.1:3100`
- 真机或其他环境建议优先在 `apps/web-portal/.env` 里设置 `VITE_NATIVE_API_BASE_URL`，再按需覆盖 `VITE_ANDROID_API_BASE_URL` / `VITE_IOS_API_BASE_URL` / `VITE_DESKTOP_API_BASE_URL`
- Electron 主进程运行时支持 `REFV2_DESKTOP_API_BASE`，未设置时会自动复用 `VITE_NATIVE_API_BASE_URL`
- 环境变量样例文件位于仓库根目录：`/.env.example`
- 原生端快捷样例文件位于：`apps/web-portal/.env.mobile.example`

模拟器调试：

- `npm run android:debug` 会自动复用或启动本机 Android 模拟器，开启 live reload，并为 `3100` 建立 `adb reverse`
- `npm run ios:debug` 会自动复用或启动本机 iOS Simulator，并以 `127.0.0.1:3100` 进入 live reload
- `npm run mobile:debug` 会串行拉起 iOS 和 Android 两端的 live reload 调试
- 三个命令都会先检查 `3100` 的 Vite dev server；若未运行，会自动在后台启动
- 如需指定设备，可设置 `ANDROID_AVD_NAME` 或 `IOS_SIMULATOR_UDID`
- 如需改 live reload 地址，可设置 `CAPACITOR_LIVE_RELOAD_HOST`，默认是 `127.0.0.1`

iOS 构建前置检查：

- `npm run ios:preflight` 会自动检查 `DEVELOPER_DIR`、Xcode CLI 与 iOS Simulator Runtime
- 默认校验 `iOS 26.4` runtime，缺失时会自动执行 `xcodebuild -downloadPlatform iOS`
- 如需切换目标 runtime，可设置 `IOS_SIM_RUNTIME_VERSION`

交易回归：

- `npm run trade:regression` 会自动登录、读取交易账户、检查 `/svc/trade/health` 是否暴露 Longbridge 观测信息
- 该回归还会验证下单链路不再返回 `502`，并要求错误返回包含参考价来源元数据

平台验证：

- `npm run verify:platform` 会串行执行 Python 测试、Web 单元测试；若本地 phase1 栈已运行，再额外检查各服务 `/health` 是否满足统一契约

打包与资源：

- 当前移动端版本号已与前端版本 `0.1.0` 对齐
- 已增加默认移动端图标和启动页生成脚本，可重复执行 `npm run assets:generate`
- 如需连续构建 Android + iOS，优先使用 `npm run mobile:build`，该命令会先统一同步 Capacitor 资源，再串行构建两端，避免并发触发 `cap sync`

发布说明：

- Android release 支持两种签名配置方式：`android/keystore.properties` 或环境变量 `ANDROID_STORE_FILE` / `ANDROID_STORE_PASSWORD` / `ANDROID_KEY_ALIAS` / `ANDROID_KEY_PASSWORD`
- Android 签名样例位于 `apps/web-portal/android/keystore.properties.example`
- 执行 `npm run android:release` 后可在 `apps/web-portal/android/app/build/outputs/` 获取 `aab/apk` release 产物
- 若未提供正式 keystore，release APK 会自动回退到 debug keystore 签名，便于本地安装测试；正式上架仍建议配置自己的发布签名
- iOS 归档命令为 `npm run ios:archive`，默认输出到 `apps/web-portal/ios/build/App.xcarchive`
- iOS 导出 ipa 命令为 `npm run ios:export:ipa`，默认读取 `apps/web-portal/ios/App/ExportOptions.plist`
- iOS 导出参数样例位于 `apps/web-portal/ios/App/ExportOptions.plist.example`
