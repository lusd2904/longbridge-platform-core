import { request } from './requestPure.js'

// 获取用户列表
export const getUsers = (params) => request.get('/svc/user/api/v1/admin/users', params)

// 创建用户
export const createUser = (data) => request.post('/svc/user/api/v1/admin/users', data)

// 更新用户
export const updateUser = (id, data) => request.put(`/svc/user/api/v1/admin/users/${encodeURIComponent(id)}`, data)

// 删除用户
export const deleteUser = (id) => request.delete(`/svc/user/api/v1/admin/users/${encodeURIComponent(id)}`)

// 重置用户密码
export const resetUserPassword = (id, data) => request.put(`/svc/user/api/v1/admin/users/${encodeURIComponent(id)}/password`, data)

// 获取用户配置
export const getUserConfigs = (userId) => request.get(`/svc/user/api/v1/admin/users/${encodeURIComponent(userId)}/configs`)

// 更新用户配置
export const updateUserConfigs = (userId, data) => request.put(`/svc/user/api/v1/admin/users/${encodeURIComponent(userId)}/configs`, data)
