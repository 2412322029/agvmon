<script setup>
import { useNotification } from 'naive-ui';
import { connectGossipWs } from '../composables/gossipNotif';

const notif = useNotification();
connectGossipWs((data) => {
  notif.info({
    title: `广播: ${data.sender}`,
    content: data.message,
    duration: 5000,
  });
});
</script>

<template>
  <div style="display: none;" />
</template>
