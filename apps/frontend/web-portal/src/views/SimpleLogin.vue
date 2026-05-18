<template>
  <div class="simple-login">
    <h1>登录</h1>
    <form @submit.prevent="handleLogin">
      <div>
        <label>用户名:</label>
        <input v-model="username" type="text" placeholder="请输入用户名" />
      </div>
      <div>
        <label>密码:</label>
        <input v-model="password" type="password" placeholder="请输入密码" />
      </div>
      <button type="submit" :disabled="loading">
        {{ loading ? '登录中...' : '登录' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { login } from '../utils/auth.js'

const username = ref('')
const password = ref('')
const loading = ref(false)

const handleLogin = async () => {
  try {
    loading.value = true
    const res = await login({ username: username.value, password: password.value })
    if (res.success) {
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      window.location.href = '/'
    } else {
      alert('登录失败: ' + (res.error || '未知错误'))
    }
  } catch (error) {
    console.error('登录失败:', error)
    alert('登录失败: ' + (error.response?.data?.error || '网络错误'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.simple-login {
  max-width: 400px;
  margin: 100px auto;
  padding: 40px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  
  h1 {
    text-align: center;
    margin-bottom: 32px;
    color: #303133;
  }
  
  form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  
  div {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  label {
    font-size: 14px;
    color: #606266;
  }
  
  input {
    padding: 12px;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    font-size: 14px;
  }
  
  button {
    padding: 12px;
    background: #409eff;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
    
    &:disabled {
      background: #c0c4cc;
      cursor: not-allowed;
    }
  }
}
</style>