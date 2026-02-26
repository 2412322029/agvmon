<template>
    <n-result status="404" title="404 资源不存在" description="生活总归带点荒谬">
        <template #footer>
            <n-button type="primary" @click="handleClick">返回首页</n-button>
        </template>
    </n-result>
</template>
<script setup>
import { NButton, NResult } from 'naive-ui';
import { useRouter } from 'vue-router';

const router = useRouter();

const handleClick = () => {
    router.push('/');
};
</script>