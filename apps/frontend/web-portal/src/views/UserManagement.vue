<template>
  <div class="user-management-page">
    <div class="page-header">
      <div>
        <h2>用户与角色</h2>
      </div>
      <div class="page-actions">
        <el-button :icon="Setting" @click="showCreateRoleDialog">新增角色</el-button>
        <el-button type="primary" :icon="Plus" @click="showAddUserDialog">添加用户</el-button>
      </div>
    </div>

    <div class="user-stats">
      <el-card v-for="stat in userStats" :key="stat.label" class="stat-card glass-card">
        <div class="stat-content">
          <div class="stat-icon" :style="{ background: stat.color }">
            <el-icon size="20">
              <component :is="stat.icon" />
            </el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ stat.label }}</div>
            <div class="stat-value">{{ stat.value }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card class="glass-card role-panel">
      <template #header>
        <div class="card-header">
          <span>角色与菜单权限</span>
          <div class="header-actions">
            <el-tag size="small" type="info">{{ roleOptions.length }} 个角色</el-tag>
            <el-button size="small" @click="loadRoleResources" :loading="roleLoading">刷新角色</el-button>
          </div>
        </div>
      </template>

      <div class="role-grid">
        <article v-for="role in roleOptions" :key="role.roleCode" class="role-card">
          <div class="role-card-head">
            <div>
              <div class="role-title-row">
                <h3>{{ role.roleName }}</h3>
                <el-tag size="small" :type="roleTagType(role.roleCode)">{{ role.roleCode }}</el-tag>
                <el-tag v-if="role.isSystem" size="small" type="info" effect="plain">系统角色</el-tag>
              </div>
            </div>
            <el-button type="primary" link @click="editRole(role)">编辑权限</el-button>
          </div>

          <div class="role-metrics">
            <div class="metric-item">
              <span>菜单数</span>
              <strong>{{ role.menuCount || 0 }}</strong>
            </div>
            <div class="metric-item">
              <span>当前页用户</span>
              <strong>{{ getRoleUserCount(role.roleCode) }}</strong>
            </div>
            <div class="metric-item">
              <span>附加能力</span>
              <strong>{{ (role.extraCapabilities || []).length }}</strong>
            </div>
          </div>

          <div class="role-menu-tags">
            <el-tag
              v-for="menu in getRoleMenuPreview(role)"
              :key="`${role.roleCode}-${menu.code}`"
              size="small"
              effect="plain"
            >
              {{ menu.title }}
            </el-tag>
            <span v-if="!getRoleMenuPreview(role).length" class="empty-hint">尚未配置菜单</span>
          </div>
        </article>
      </div>
    </el-card>

    <el-card class="glass-card user-table">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <div class="header-actions">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索用户名 / 邮箱"
              :prefix-icon="Search"
              clearable
              style="width: 240px"
              @clear="handleFilterChange"
              @keyup.enter="handleFilterChange"
            />
            <el-select v-model="filterRole" placeholder="角色" clearable style="width: 180px" @change="handleFilterChange">
              <el-option label="全部角色" value="" />
              <el-option v-for="role in roleOptions" :key="role.roleCode" :label="role.roleName" :value="role.roleCode" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 140px" @change="handleFilterChange">
              <el-option label="全部状态" value="" />
              <el-option label="正常" value="active" />
              <el-option label="禁用" value="disabled" />
              <el-option label="锁定" value="locked" />
            </el-select>
            <el-button @click="loadUsers" :loading="loading">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="users" v-loading="loading" style="width: 100%" table-layout="auto">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column prop="platform_role_code" label="角色" width="160">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.platform_role_code)">
              {{ roleLabel(row.platform_role_code) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="broker_account_count" label="券商账户" width="110" />
        <el-table-column label="量化 API" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.quant_api_enabled ? 'success' : 'info'">
              {{ row.quant_api_enabled ? '已开通' : '未开通' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务中心" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.task_admin_enabled ? 'warning' : 'info'">
              {{ row.task_admin_enabled ? '可管理' : '无权限' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_time" label="最后登录" width="180">
          <template #default="{ row }">
            {{ formatDate(row.last_login_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editUser(row)">编辑</el-button>
            <el-button type="warning" link size="small" @click="toggleStatus(row)">
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button type="info" link size="small" @click="resetPassword(row)">重置密码</el-button>
            <el-button type="danger" link size="small" @click="removeUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="roleDialogVisible"
      :title="roleDialogMode === 'edit' ? '编辑角色' : '新增角色'"
      width="920px"
      top="6vh"
      class="role-dialog"
    >
      <el-form ref="roleFormRef" :model="roleForm" :rules="roleRules" label-width="100px">
        <div class="form-grid">
          <el-form-item label="角色编码" prop="roleCode">
            <el-input v-model="roleForm.roleCode" :disabled="roleDialogMode === 'edit'" placeholder="例如 research_lead" />
          </el-form-item>
          <el-form-item label="角色名称" prop="roleName">
            <el-input v-model="roleForm.roleName" placeholder="输入角色名称" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number v-model="roleForm.priority" :min="0" :step="10" style="width: 100%" />
          </el-form-item>
          <el-form-item label="附加能力">
            <el-checkbox-group v-model="roleForm.extraCapabilities">
              <el-checkbox label="quant.use">量化交易能力</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
        </div>

        <el-form-item label="角色说明">
          <el-input v-model="roleForm.description" type="textarea" :rows="3" placeholder="说明这个角色能处理哪些工作" />
        </el-form-item>

        <div class="menu-section-head">
          <div>
            <strong>菜单权限</strong>
          </div>
          <div class="menu-section-actions">
            <el-button size="small" @click="selectAllRoleMenus">全选</el-button>
            <el-button size="small" @click="clearAllRoleMenus">清空</el-button>
          </div>
        </div>

        <div class="menu-matrix">
          <section v-for="subsystem in groupedMenus" :key="subsystem.code" class="menu-block">
            <div class="menu-block-head">
              <div>
                <strong>{{ subsystem.title }}</strong>
                <span>{{ subsystem.items.length }} 个菜单</span>
              </div>
              <el-checkbox
                :model-value="isSubsystemChecked(subsystem)"
                :indeterminate="isSubsystemIndeterminate(subsystem)"
                @change="toggleSubsystemMenus(subsystem, $event)"
              >
                全选
              </el-checkbox>
            </div>
            <div class="menu-group-list">
              <div v-for="group in subsystem.groups" :key="`${subsystem.code}-${group.code}`" class="menu-group">
                <div class="menu-group-title">{{ group.title }}</div>
                <el-checkbox-group v-model="roleForm.menuCodes">
                  <el-checkbox
                    v-for="menu in group.items"
                    :key="menu.code"
                    :label="menu.code"
                  >
                    {{ menu.title }}
                  </el-checkbox>
                </el-checkbox-group>
              </div>
            </div>
          </section>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleSaving" @click="saveRole">保存角色</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="userDialogVisible"
      :title="isEdit ? '编辑用户' : '添加用户'"
      width="680px"
      top="8vh"
    >
      <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-width="110px">
        <div class="form-grid">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="userForm.username" :disabled="isEdit" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="userForm.email" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="userForm.phone" />
          </el-form-item>
          <el-form-item label="昵称">
            <el-input v-model="userForm.nickname" />
          </el-form-item>
          <el-form-item v-if="!isEdit" label="密码" prop="password">
            <el-input v-model="userForm.password" type="password" show-password />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="userForm.status">
              <el-option label="正常" value="active" />
              <el-option label="禁用" value="disabled" />
              <el-option label="锁定" value="locked" />
            </el-select>
          </el-form-item>
          <el-form-item label="平台角色" prop="platform_role_code">
            <el-select v-model="userForm.platform_role_code">
              <el-option
                v-for="role in roleOptions"
                :key="role.roleCode"
                :label="role.roleName"
                :value="role.roleCode"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="登录角色">
            <el-select v-model="userForm.role">
              <el-option label="普通用户" value="user" />
              <el-option label="管理员" value="admin" />
            </el-select>
          </el-form-item>
        </div>

        <div class="inline-note">
          <span>菜单显示以平台角色为准；量化交易需同时满足角色能力、量化 API 开关和已绑定券商账户。</span>
        </div>

        <el-form-item label="量化交易 API">
          <el-switch v-model="userForm.quant_api_enabled" />
        </el-form-item>
        <el-form-item label="任务中心权限">
          <el-switch v-model="userForm.task_admin_enabled" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="userDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Setting, Star, User, UserFilled, Wallet } from '@element-plus/icons-vue'
import {
  createPlatformRole,
  createUser,
  deleteUser,
  getPlatformBootstrap,
  getPlatformMenus,
  getPlatformRoles,
  getUsers,
  resetUserPassword,
  updatePlatformRole,
  updateUser
} from '../api/platform.js'
import { setSession } from '../utils/auth.js'

const loading = ref(false)
const saving = ref(false)
const roleLoading = ref(false)
const roleSaving = ref(false)
const users = ref([])
const total = ref(0)
const roleOptions = ref([])
const platformMenus = ref([])
const searchKeyword = ref('')
const filterRole = ref('')
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const userDialogVisible = ref(false)
const roleDialogVisible = ref(false)
const isEdit = ref(false)
const roleDialogMode = ref('create')
const userFormRef = ref(null)
const roleFormRef = ref(null)

const userForm = reactive({
  id: null,
  username: '',
  email: '',
  phone: '',
  nickname: '',
  password: '',
  role: 'user',
  status: 'active',
  platform_role_code: 'user',
  preferred_subsystem_code: 'workspace',
  quant_api_enabled: false,
  task_admin_enabled: false
})

const roleForm = reactive({
  roleCode: '',
  roleName: '',
  description: '',
  priority: 0,
  menuCodes: [],
  extraCapabilities: []
})

const userRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, message: '请输入初始密码', trigger: 'blur' }],
  platform_role_code: [{ required: true, message: '请选择平台角色', trigger: 'change' }]
}

const roleRules = {
  roleCode: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
  roleName: [{ required: true, message: '请输入角色名称', trigger: 'blur' }]
}

const userStats = computed(() => {
  const list = users.value
  return [
    { label: '当前页用户', value: list.length, icon: User, color: 'linear-gradient(135deg, #2f7df6, #6dc7ff)' },
    { label: '角色数量', value: roleOptions.value.length, icon: Setting, color: 'linear-gradient(135deg, #ffb84d, #ff8f4d)' },
    { label: '量化 API 用户', value: list.filter((item) => item.quant_api_enabled).length, icon: Wallet, color: 'linear-gradient(135deg, #18c59e, #65f0a7)' },
    { label: '活跃状态', value: list.filter((item) => item.status === 'active').length, icon: UserFilled, color: 'linear-gradient(135deg, #8f7bff, #5b93ff)' }
  ]
})

const groupedMenus = computed(() => {
  const subsystemMap = new Map()
  platformMenus.value.forEach((menu, index) => {
    const subsystemCode = String(menu.subsystemCode || 'workspace')
    if (!subsystemMap.has(subsystemCode)) {
      subsystemMap.set(subsystemCode, {
        code: subsystemCode,
        title: menu.subsystemTitle || subsystemCode,
        sortIndex: Number(menu.subsystemSortIndex ?? index),
        items: [],
        groups: []
      })
    }
    subsystemMap.get(subsystemCode).items.push(menu)
  })

  return Array.from(subsystemMap.values())
    .sort((a, b) => a.sortIndex - b.sortIndex)
    .map((subsystem) => {
      const groupMap = new Map()
      subsystem.items.forEach((menu, index) => {
        const groupCode = String(menu.group || 'general')
        if (!groupMap.has(groupCode)) {
          groupMap.set(groupCode, {
            code: groupCode,
            title: menu.groupTitle || groupCode,
            sortIndex: Number(menu.sortIndex ?? index),
            items: []
          })
        }
        groupMap.get(groupCode).items.push(menu)
      })
      return {
        ...subsystem,
        groups: Array.from(groupMap.values()).sort((a, b) => a.sortIndex - b.sortIndex)
      }
    })
})

const roleLabel = (roleCode) => roleOptions.value.find((item) => item.roleCode === roleCode)?.roleName || roleCode || '未设置'
const roleTagType = (roleCode) => ({ admin: 'danger', trader: 'warning', user: 'primary' }[roleCode] || 'success')
const statusLabel = (status) => ({ active: '正常', disabled: '禁用', locked: '锁定' }[status] || status || '--')
const statusTagType = (status) => ({ active: 'success', disabled: 'info', locked: 'danger' }[status] || 'info')
const formatDate = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

const getRoleUserCount = (roleCode) => users.value.filter((item) => item.platform_role_code === roleCode).length
const getRoleMenuPreview = (role) => {
  const menuCodes = new Set(role?.menuCodes || [])
  return platformMenus.value.filter((item) => menuCodes.has(item.code)).slice(0, 6)
}

const resetUserForm = () => {
  Object.assign(userForm, {
    id: null,
    username: '',
    email: '',
    phone: '',
    nickname: '',
    password: '',
    role: 'user',
    status: 'active',
    platform_role_code: roleOptions.value.find((item) => item.roleCode === 'user')?.roleCode || roleOptions.value[0]?.roleCode || 'user',
    preferred_subsystem_code: 'workspace',
    quant_api_enabled: false,
    task_admin_enabled: false
  })
}

const resetRoleForm = () => {
  Object.assign(roleForm, {
    roleCode: '',
    roleName: '',
    description: '',
    priority: 0,
    menuCodes: [],
    extraCapabilities: []
  })
}

const refreshBootstrap = async () => {
  try {
    const bootstrap = await getPlatformBootstrap()
    if (bootstrap?.data) {
      setSession(bootstrap.data)
    }
  } catch (error) {
    console.error('刷新会话失败:', error)
  }
}

const loadRoles = async () => {
  const res = await getPlatformRoles()
  roleOptions.value = Array.isArray(res?.data) ? res.data : []
}

const loadMenus = async () => {
  const res = await getPlatformMenus()
  platformMenus.value = Array.isArray(res?.data) ? res.data.filter((item) => item.enabled) : []
}

const loadRoleResources = async () => {
  roleLoading.value = true
  try {
    await Promise.all([loadRoles(), loadMenus()])
  } catch (error) {
    console.error('加载角色资源失败:', error)
    ElMessage.error(error?.data?.error || '加载角色资源失败')
  } finally {
    roleLoading.value = false
  }
}

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await getUsers({
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchKeyword.value.trim(),
      role: filterRole.value,
      status: filterStatus.value
    })
    const payload = res?.data || {}
    users.value = Array.isArray(payload.list) ? payload.list : []
    total.value = Number(payload.total || 0)
  } catch (error) {
    console.error('加载用户失败:', error)
    ElMessage.error(error?.data?.error || '加载用户失败')
  } finally {
    loading.value = false
  }
}

const showCreateRoleDialog = () => {
  roleDialogMode.value = 'create'
  resetRoleForm()
  roleDialogVisible.value = true
}

const editRole = (role) => {
  roleDialogMode.value = 'edit'
  Object.assign(roleForm, {
    roleCode: role.roleCode,
    roleName: role.roleName,
    description: role.description || '',
    priority: Number(role.priority || 0),
    menuCodes: Array.isArray(role.menuCodes) ? [...role.menuCodes] : [],
    extraCapabilities: Array.isArray(role.extraCapabilities) ? [...role.extraCapabilities] : []
  })
  roleDialogVisible.value = true
}

const normalizeRolePayload = () => ({
  roleCode: roleForm.roleCode.trim().toLowerCase(),
  roleName: roleForm.roleName.trim(),
  description: roleForm.description.trim(),
  priority: Number(roleForm.priority || 0),
  menuCodes: Array.from(new Set(roleForm.menuCodes)).filter(Boolean),
  extraCapabilities: Array.from(new Set(roleForm.extraCapabilities)).filter(Boolean)
})

const saveRole = async () => {
  if (!roleFormRef.value) return

  try {
    roleSaving.value = true
    await roleFormRef.value.validate()
    const payload = normalizeRolePayload()
    if (!payload.menuCodes.length) {
      ElMessage.warning('至少需要勾选一个菜单')
      return
    }
    if (roleDialogMode.value === 'edit') {
      await updatePlatformRole(payload.roleCode, payload)
      ElMessage.success('角色权限已更新')
    } else {
      await createPlatformRole(payload)
      ElMessage.success('角色已创建')
    }
    roleDialogVisible.value = false
    await Promise.all([loadRoleResources(), loadUsers(), refreshBootstrap()])
  } catch (error) {
    console.error('保存角色失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '保存角色失败')
  } finally {
    roleSaving.value = false
  }
}

const selectAllRoleMenus = () => {
  roleForm.menuCodes = platformMenus.value.map((item) => item.code)
}

const clearAllRoleMenus = () => {
  roleForm.menuCodes = []
}

const subsystemMenuCodes = (subsystem) => subsystem?.items?.map((item) => item.code).filter(Boolean) || []
const isSubsystemChecked = (subsystem) => {
  const codes = subsystemMenuCodes(subsystem)
  return codes.length > 0 && codes.every((code) => roleForm.menuCodes.includes(code))
}
const isSubsystemIndeterminate = (subsystem) => {
  const codes = subsystemMenuCodes(subsystem)
  const checkedCount = codes.filter((code) => roleForm.menuCodes.includes(code)).length
  return checkedCount > 0 && checkedCount < codes.length
}
const toggleSubsystemMenus = (subsystem, checked) => {
  const codes = subsystemMenuCodes(subsystem)
  if (checked) {
    roleForm.menuCodes = Array.from(new Set([...roleForm.menuCodes, ...codes]))
    return
  }
  roleForm.menuCodes = roleForm.menuCodes.filter((code) => !codes.includes(code))
}

const showAddUserDialog = () => {
  isEdit.value = false
  resetUserForm()
  userDialogVisible.value = true
}

const editUser = (row) => {
  isEdit.value = true
  Object.assign(userForm, {
    id: row.id,
    username: row.username,
    email: row.email || '',
    phone: row.phone || '',
    nickname: row.nickname || '',
    password: '',
    role: row.role || (row.platform_role_code === 'admin' ? 'admin' : 'user'),
    status: row.status || 'active',
    platform_role_code: row.platform_role_code || roleOptions.value.find((item) => item.roleCode === 'user')?.roleCode || roleOptions.value[0]?.roleCode || 'user',
    preferred_subsystem_code: row.preferred_subsystem_code || 'workspace',
    quant_api_enabled: Boolean(row.quant_api_enabled),
    task_admin_enabled: Boolean(row.task_admin_enabled)
  })
  userDialogVisible.value = true
}

const normalizeUserPayload = () => ({
  username: userForm.username.trim(),
  email: userForm.email.trim(),
  phone: userForm.phone.trim(),
  nickname: userForm.nickname.trim(),
  password: userForm.password,
  role: userForm.platform_role_code === 'admin' ? 'admin' : userForm.role,
  status: userForm.status,
  platform_role_code: userForm.platform_role_code,
  preferred_subsystem_code: userForm.preferred_subsystem_code,
  quant_api_enabled: Boolean(userForm.quant_api_enabled),
  task_admin_enabled: Boolean(userForm.task_admin_enabled)
})

const saveUser = async () => {
  if (!userFormRef.value) return

  try {
    saving.value = true
    await userFormRef.value.validate()
    const payload = normalizeUserPayload()

    if (isEdit.value && userForm.id) {
      await updateUser(userForm.id, payload)
      ElMessage.success('用户信息已更新')
    } else {
      await createUser(payload)
      ElMessage.success('用户已创建')
    }

    userDialogVisible.value = false
    await Promise.all([loadUsers(), refreshBootstrap()])
  } catch (error) {
    console.error('保存用户失败:', error)
    ElMessage.error(error?.data?.error || '保存用户失败')
  } finally {
    saving.value = false
  }
}

const toggleStatus = async (row) => {
  try {
    const nextStatus = row.status === 'active' ? 'disabled' : 'active'
    await updateUser(row.id, { status: nextStatus })
    ElMessage.success(`用户已${nextStatus === 'active' ? '启用' : '禁用'}`)
    await Promise.all([loadUsers(), refreshBootstrap()])
  } catch (error) {
    console.error('更新状态失败:', error)
    ElMessage.error(error?.data?.error || '更新状态失败')
  }
}

const resetPassword = async (row) => {
  try {
    const { value } = await ElMessageBox.prompt(`请输入 ${row.username} 的新密码`, '重置密码', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputType: 'password',
      inputValidator: (inputValue) => (String(inputValue || '').length >= 6 ? true : '密码至少 6 位')
    })
    await resetUserPassword(row.id, { new_password: value })
    ElMessage.success('密码已重置')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('重置密码失败:', error)
      ElMessage.error(error?.data?.error || '重置密码失败')
    }
  }
}

const removeUser = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除用户 ${row.username} 吗？`, '删除用户', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await deleteUser(row.id)
    ElMessage.success('用户已删除')
    await Promise.all([loadUsers(), refreshBootstrap()])
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除用户失败:', error)
      ElMessage.error(error?.data?.error || '删除用户失败')
    }
  }
}

const handleFilterChange = () => {
  currentPage.value = 1
  loadUsers()
}

const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  loadUsers()
}

const handleCurrentChange = (page) => {
  currentPage.value = page
  loadUsers()
}

onMounted(async () => {
  await Promise.all([loadRoleResources(), loadUsers()])
  if (!roleOptions.value.find((item) => item.roleCode === userForm.platform_role_code) && roleOptions.value.length) {
    userForm.platform_role_code = roleOptions.value[0].roleCode
  }
})
</script>

<style scoped lang="scss">
.user-management-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.page-header,
.page-actions,
.card-header,
.header-actions,
.stat-content,
.role-title-row,
.role-card-head,
.role-metrics,
.menu-section-head,
.menu-section-actions,
.menu-block-head {
  display: flex;
  align-items: center;
}

.page-header {
  justify-content: space-between;
  gap: 18px;

  h2 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
  }
}

.page-actions {
  gap: 12px;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.user-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  :deep(.el-card__body) {
    padding: 18px;
  }
}

.stat-content {
  gap: 14px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: #fff;
}

.stat-label {
  color: var(--text-muted);
  font-size: 13px;
}

.stat-value {
  margin-top: 4px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.card-header {
  justify-content: space-between;
  gap: 14px;
}

.header-actions {
  gap: 12px;
  flex-wrap: wrap;
  min-width: 0;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.role-panel,
.user-table,
.menu-matrix {
  min-width: 0;
}

.role-card {
  padding: 18px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(248, 250, 252, 0.95));
}

.role-card-head {
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;

  h3 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 8px 0 0;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.role-title-row {
  gap: 8px;
  flex-wrap: wrap;
}

.role-metrics {
  gap: 12px;
  margin-top: 16px;
}

.metric-item {
  flex: 1;
  min-width: 0;
  padding: 12px;
  border-radius: 14px;
  background: var(--surface-soft);
  border: 1px solid var(--border-soft);

  span {
    display: block;
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 8px;
    color: var(--text-primary);
    font-size: 20px;
  }
}

.role-menu-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.user-table :deep(.el-card__body) {
  overflow-x: auto;
}

.user-table :deep(.el-table .cell) {
  word-break: break-word;
}

.role-dialog :deep(.el-dialog) {
  max-height: 88vh;
}

.role-dialog :deep(.el-dialog__body) {
  max-height: calc(88vh - 124px);
  overflow-y: auto;
  overflow-x: hidden;
}

.empty-hint {
  color: var(--text-muted);
  font-size: 13px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.inline-note {
  margin-bottom: 18px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--surface-soft);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.menu-section-head {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;

  strong {
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
    font-size: 13px;
  }
}

.menu-section-actions {
  gap: 8px;
}

.menu-matrix {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.menu-block {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.menu-block-head {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;

  strong {
    color: var(--text-primary);
  }

  span {
    display: block;
    margin-top: 4px;
    color: var(--text-muted);
    font-size: 12px;
  }
}

.menu-group-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.menu-group {
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.menu-group-title {
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .user-stats,
  .role-grid,
  .menu-group-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .page-header,
  .card-header,
  .page-actions,
  .header-actions,
  .form-grid,
  .menu-section-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .page-actions,
  .header-actions {
    width: 100%;
  }

  .user-table :deep(.el-table) {
    min-width: 1120px;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr;
  }

  .user-stats {
    grid-template-columns: 1fr;
  }
}
</style>
