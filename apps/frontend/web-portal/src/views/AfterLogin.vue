<template>
  <div class="after-login">
    <h1>登录成功</h1>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

onMounted(() => {
})
</script>

<style scoped>
.after-login {
  padding: 40px;
  text-align: center;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  margin: 20px;
  
  h1 {
    font-size: 24px;
    color: #303133;
    margin-bottom: 16px;
  }
  
  p {
    font-size: 16px;
    color: #606266;
    margin-bottom: 8px;
  }
}
</style>
