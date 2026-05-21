# User Center

User Center 是平台账号与权限服务，默认端口 `8101`。前端登录、菜单、角色、用户管理、系统配置都从这里读取。

## 做了什么

- 登录、登出、刷新 token、当前用户信息。
- 平台 bootstrap：返回 user、access、menus、subsystems、navigation。
- 用户资料、密码、系统配置、资产趋势、系统日志。
- 角色和菜单治理：`PlatformAccessService` 种子维护平台能力和菜单。
- 管理员用户管理：创建、更新、删除、重置密码。
- 已新增 `sentiment-center` 菜单，能力为 `market.sentiment.view`。

## 主要接口

- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/info`
- `GET /api/v1/users/bootstrap`
- `GET /api/v1/users/profile`
- `PUT /api/v1/users/profile`
- `PUT /api/v1/auth/password`
- `GET /api/v1/config`
- `PUT /api/v1/config`
- `GET /api/v1/platform/roles`
- `GET /api/v1/platform/menus`
- `POST /api/v1/platform/roles`
- `PUT /api/v1/platform/roles/{role_code}`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users`
- `PUT /api/v1/admin/users/{user_id}`
- `DELETE /api/v1/admin/users/{user_id}`
- `PUT /api/v1/admin/users/{user_id}/password`

## 使用

```bash
cd apps/platform/user-center
./run.sh
```

登录示例：

```bash
curl -fsS -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  http://127.0.0.1:8101/api/v1/auth/login
```

## 依赖

- MySQL：用户、角色、菜单、系统配置。
- `backend-server/src/core/platform/PlatformAccessService.py`：平台访问控制核心。
- `backend-server/src/api/auth_routes.py` 等 legacy helper：重构期兼容边界。

## 验证

```bash
curl -fsS http://127.0.0.1:8101/health
TOKEN=$(curl -fsS -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' http://127.0.0.1:3100/svc/user/api/v1/auth/login | node -e 'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>process.stdout.write(JSON.parse(s).data.token))')
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/svc/user/api/v1/users/bootstrap
```
