<template>
  <div class="privacy-page">
    <header class="privacy-header"><div class="header-identity"><span class="header-symbol"><el-icon :size="27"><Lock /></el-icon></span><div><div class="heading-line"><h1>端云协同工作台</h1><span class="workspace-badge">任务与过程一体展示</span></div><p>提出具体问题，查看本地统计、隐私检查、云端解读与执行结果。</p></div></div><el-button plain @click="$router.push('/intelligent-prediction')">返回智能预测</el-button></header>
    <TaskWorkspace />
  </div>
</template>
<script setup>
import { Lock } from '@element-plus/icons-vue'
import TaskWorkspace from '../components/collaboration/TaskWorkspace.vue'
</script>
<style scoped>
.privacy-page{max-width:1600px;margin:0 auto;color:#24324a}.privacy-header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:24px;padding:7px 0 20px;border-bottom:1px solid #e3eaf1}.header-identity{display:flex;align-items:center;gap:14px;min-width:0}.header-symbol{display:grid;place-items:center;width:52px;height:52px;flex-shrink:0;background:#edf5f7;color:#277879;border-radius:14px}.heading-line{display:flex;align-items:center;gap:12px;flex-wrap:wrap}h1{font-size:24px;font-weight:600;color:#163952;margin:0}.workspace-badge{font-size:11px;color:#577c88;background:#edf5f7;border:1px solid #d7e7eb;padding:4px 8px;border-radius:5px}.privacy-header p{font-size:13px;color:#6b8093;margin:9px 0 0;line-height:1.7}@media(max-width:700px){.privacy-header{align-items:flex-start;flex-wrap:wrap}.header-symbol{width:42px;height:42px}h1{font-size:21px}}
</style>
