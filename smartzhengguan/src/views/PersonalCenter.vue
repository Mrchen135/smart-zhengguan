<template>
  <PageDataState :loading="dataLoading" :error="dataError" @retry="retryDatabasePage">
  <div v-if="pageData" class="personal-page">
    <div class="page-header">
      <div class="header-left">
        <span class="page-title">{{ pageData.title }}</span>
        <span class="page-subtitle">{{ pageData.subtitle }}</span>
      </div>
      <div class="header-right">
        <span class="update-time">上次登录：{{ profile.lastLogin }}</span>
      </div>
    </div>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="card in pageData.statCards" :key="card.title">
        <DashboardCard
          :title="card.title"
          :number="card.number"
          :icon="card.icon"
          :iconBg="card.iconBg"
          :changeLabel="card.changeLabel"
        />
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :span="14">
        <div class="section-card">
          <div class="card-header">
            <span class="card-title">个人资料</span>
            <div class="header-actions">
              <el-button @click="resetProfile">重置</el-button>
              <el-button type="primary" class="primary-btn" :loading="saving" @click="saveProfile">保存资料</el-button>
            </div>
          </div>
          <el-form :model="profile" label-width="90px" class="profile-form">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="姓名">
                  <el-input v-model="profile.name" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="角色">
                  <el-input v-model="profile.role" disabled />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="所属部门">
                  <el-input v-model="profile.department" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="工号">
                  <el-input v-model="profile.jobNo" disabled />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="手机号">
                  <el-input v-model="profile.phone" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="邮箱">
                  <el-input v-model="profile.email" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="section-card profile-side-card">
          <div class="profile-top">
            <el-avatar :size="64" class="profile-avatar">{{ profile.name.charAt(0) }}</el-avatar>
            <div class="profile-summary">
              <div class="profile-name">{{ profile.name }}</div>
              <div class="profile-role">{{ profile.role }}</div>
              <div class="profile-dept">{{ profile.department }}</div>
            </div>
          </div>
          <div class="profile-tags">
            <el-tag
              v-for="tag in pageData.profileTags"
              :key="tag.label"
              :type="tag.type"
              effect="plain"
            >
              {{ tag.label }}
            </el-tag>
          </div>
          <div class="quick-list">
            <div
              v-for="item in pageData.quickActions"
              :key="item.label"
              class="quick-item"
              @click="$router.push(item.route)"
            >
              <span class="quick-label">{{ item.label }}</span>
              <span class="quick-desc">{{ item.desc }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="bottom-row">
      <el-col :span="14">
        <div class="section-card">
          <div class="card-header">
            <span class="card-title">最近操作记录</span>
          </div>
          <el-table :data="pageData.operationLogs" stripe size="small" class="compact-table">
            <el-table-column prop="time" label="时间" width="120" />
            <el-table-column prop="module" label="模块" width="110" />
            <el-table-column prop="action" label="操作内容" min-width="180" />
            <el-table-column prop="status" label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.statusType" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="section-card">
          <div class="card-header">
            <span class="card-title">常用入口</span>
          </div>
          <div class="shortcut-list">
            <div
              v-for="item in pageData.shortcuts"
              :key="item.label"
              class="shortcut-item"
              @click="$router.push(item.route)"
            >
              <span class="shortcut-label">{{ item.label }}</span>
              <span class="shortcut-arrow">进入 ></span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</PageDataState>
</template>

<script>
import { withDatabasePage } from '../utils/databasePage'
import DashboardCard from '../components/DashboardCard.vue'
import { getPersonalCenterData } from '../services/dataService'
import { saveProfile } from '../services/accountService'
export default withDatabasePage({
  components: { DashboardCard },
  data() { return { pageData: null, baseProfile: null, profile: { name: '', role: '', department: '', jobNo: '', phone: '', email: '', lastLogin: '' }, saving: false } },
  async mounted() { await this.loadProfile() },
  methods: {
    applyData(data) { this.pageData = data; this.baseProfile = { ...data.profile }; this.profile = { ...data.profile } },
    async loadProfile() { this.applyData(await getPersonalCenterData()) },
    async saveProfile() {
      if (this.saving) return
      this.saving = true
      try { this.applyData(await saveProfile(this.profile)); window.dispatchEvent(new Event('account-updated')); this.$message.success('个人资料已保存到数据库') }
      catch (error) { this.$message.error(error.message) }
      finally { this.saving = false }
    },
    resetProfile() { this.profile = { ...this.baseProfile } },
  },
})
</script>

<style scoped>
.personal-page { color: #333; }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  gap: 16px;
}
.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.page-title { font-size: 20px; font-weight: 600; color: #333; }
.page-subtitle,
.update-time { font-size: 13px; color: #86909C; }
.stat-row,
.chart-row,
.bottom-row { margin-bottom: 16px; }
.section-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  height: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F0F0F0;
}
.card-title { font-size: 16px; font-weight: 600; color: #1D2939; }
.header-actions { display: flex; gap: 8px; }
.primary-btn { background: #0A2463 !important; border-color: #0A2463 !important; }
.profile-form { padding-top: 4px; }
.profile-side-card { display: flex; flex-direction: column; gap: 16px; }
.profile-top { display: flex; align-items: center; gap: 16px; }
.profile-avatar { background: #165DFF; font-size: 26px; flex-shrink: 0; }
.profile-name { font-size: 20px; font-weight: 600; color: #1D2939; }
.profile-role,
.profile-dept { font-size: 13px; color: #667085; margin-top: 4px; }
.profile-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.quick-list,
.shortcut-list { display: flex; flex-direction: column; gap: 10px; }
.quick-item,
.shortcut-item {
  padding: 12px 14px;
  border-radius: 8px;
  background: #F8FAFC;
  border: 1px solid #EEF2F6;
  cursor: pointer;
}
.quick-label,
.shortcut-label { font-size: 14px; font-weight: 500; color: #1D2939; }
.quick-desc,
.shortcut-arrow { display: block; font-size: 12px; color: #667085; margin-top: 4px; }
.compact-table :deep(.el-table__header th) {
  background: #F8FAFC;
  color: #344054;
  font-weight: 600;
  font-size: 13px;
}
</style>
