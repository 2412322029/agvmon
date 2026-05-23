<script setup>
import { useNotification } from 'naive-ui';
import { connectGossipWs } from '../composables/gossipNotif';

const notif = useNotification();

const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
if (isLocal && 'Notification' in window && Notification.permission === 'default') {
  Notification.requestPermission();
}

connectGossipWs((data) => {
  notif.info({
    title: `广播: ${data.sender}`,
    content: data.message,
    duration: 5000,
  });
  if (isLocal && 'Notification' in window && Notification.permission === 'granted') {
    new Notification(`[Gossip] ${data.sender}`, {
      body: data.message,
      icon: '/favicon.ico',
    });
  }
});
</script>

<template>
  <div style="display: none;" />
</template>
