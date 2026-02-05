<template>
  <div class="ssh-view">
    <n-card title="SSH 文件管理" :bordered="false">
      <SSHComponent :showInput="true" />
    </n-card>
  </div>
</template>

<script setup>
import SSHComponent from '@/components/ssh.vue';
import { NCard } from 'naive-ui';
</script>

<style scoped>
.ssh-view {
  padding: 2px;
}
</style>