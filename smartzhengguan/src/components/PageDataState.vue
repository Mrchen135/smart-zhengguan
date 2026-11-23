<template>
  <div class="database-page-state">
    <el-skeleton v-if="loading" :rows="8" animated class="database-skeleton" />
    <el-result v-else-if="error" icon="error" title="数据加载失败" :sub-title="error">
      <template #extra><el-button type="primary" @click="$emit('retry')">重新加载</el-button></template>
    </el-result>
    <div v-show="!error" :style="{ visibility: loading ? 'hidden' : 'visible' }"><slot /></div>
  </div>
</template>
<script setup>
defineProps({ loading: Boolean, error: { type: String, default: '' } })
defineEmits(['retry'])
</script>
<style scoped>
.database-skeleton { padding: 32px; background: white; border-radius: 12px; }
</style>
