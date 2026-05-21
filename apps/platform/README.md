# Platform Module

平台模块负责账号、权限、菜单、系统配置、服务目录和依赖观测，是前端工作台进入所有业务域的基础。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `user-center` | `8101` | 登录、用户、角色、菜单、配置、平台 bootstrap |
| `api-gateway` | `5101` | 服务目录、依赖探测和观测聚合 |

## 启动

```bash
cd apps/platform
./run.sh
```

单服务：

```bash
cd apps/platform/user-center && ./run.sh
cd apps/platform/api-gateway && ./run.sh
```

Docker compose 会自动以 `user-center -> api-gateway` 顺序拉起。

## 关键交付

- `PlatformAccessService` 维护角色、能力、菜单和子系统种子。
- 菜单中已包含 `sentiment-center`，能力为 `market.sentiment.view`。
- 登录返回 token + user bootstrap，前端启动后也会刷新 bootstrap，避免旧菜单缓存。
- API Gateway 聚合全部服务健康状态和服务目录；Web Portal 的 `/svc/gateway/...` 会访问它。

## 验证

```bash
curl -fsS http://127.0.0.1:8101/health
curl -fsS http://127.0.0.1:5101/health
python3 scripts/check_platform_health.py
```

更多说明见：

- [User Center](./user-center/README.md)
- [API Gateway](./api-gateway/README.md)
