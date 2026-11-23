<template>
  <PageDataState :loading="dataLoading" :error="dataError" @retry="retryDatabasePage">
  <section class="settings-page" v-if="config">
    <div class="heading"><h2>系统设置</h2><p>工作台配置由后端保存，刷新或重新登录后仍然生效。</p></div>
    <el-alert v-if="!config.canEdit" title="当前账号可查看配置，修改需要管理员权限" type="info" :closable="false" show-icon />
    <el-card shadow="never">
      <el-form label-position="top" :disabled="!config.canEdit || saving">
        <el-form-item label="登录后的默认入口"><el-select v-model="form.default_page"><el-option v-for="item in pages" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <el-form-item label="数据管理中批次列表每页条数"><el-radio-group v-model="form.batch_page_size"><el-radio-button v-for="size in [10,20,50,100]" :key="size" :value="size">{{ size }} 条</el-radio-button></el-radio-group></el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button><el-button @click="form = { ...config.values }">重置</el-button>
      </el-form>
      <p class="updated">最近保存：{{ config.updatedAt ? new Date(config.updatedAt).toLocaleString('zh-CN') : '尚未修改，使用默认配置' }}</p>
    </el-card>
    <el-card shadow="never"><template #header>当前账号的配置操作记录</template><el-table :data="config.logs" empty-text="尚无配置修改记录"><el-table-column prop="time" label="时间" width="180" /><el-table-column prop="action" label="操作" /><el-table-column prop="status" label="结果" width="100" /></el-table></el-card>
  </section>
</PageDataState>
</template>
<script>
import { withDatabasePage } from '../utils/databasePage'
import { getSystemSettingsData } from '../services/dataService'
import { saveSystemSettings } from '../services/accountService'
export default withDatabasePage({
  data() { return { config: null, form: {}, saving: false, pages: [
    { value: '/home', label: '首页' }, { value: '/academic-status', label: '学籍管理' },
    { value: '/data-management', label: '数据管理' }, { value: '/intelligent-prediction', label: '智能预测' },
    { value: '/query-results', label: '综合画像' },
  ] } },
  async mounted() { this.config = await getSystemSettingsData(); this.form = { ...this.config.values } },
  methods: {
    async save() {
      if (this.saving) return
      this.saving = true
      try { this.config = await saveSystemSettings(this.form); this.form = { ...this.config.values }; this.$message.success('配置已保存到数据库') }
      catch (error) { this.$message.error(error.message) }
      finally { this.saving = false }
    },
  },
})
</script>
<style scoped>
.settings-page { display: grid; gap: 18px; max-width: 1100px; margin: auto; }
.heading { background: linear-gradient(120deg,#eff6ff,#f0fdfa); padding: 20px 26px; border-radius: 14px; }
h2 { margin: 0 0 10px; color: #13345f; } p { color: #64748b; font-size: 14px; }
.el-select { width: 320px; max-width: 100%; }.updated { margin-top: 22px; }
</style>
