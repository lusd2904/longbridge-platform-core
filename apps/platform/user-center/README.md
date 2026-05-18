# User Center

职责：

- 登录
- 用户资料
- 券商账户绑定
- 用户级配置与关注标的

迁移来源：

- `backend-server/src/api/user_routes.py`
- `backend-server/src/core/platform/PlatformAccessService.py`
- `web/src/views/Profile.vue`

当前状态：

- 已在 `8101` 运行
- 已支持登录、会话、用户 bootstrap
- 已补充个人资料、修改密码、配置读取与更新
