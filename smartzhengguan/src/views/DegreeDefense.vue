<template>
  <PageDataState :loading="dataLoading" :error="dataError" @retry="retryDatabasePage">
  <FeatureWorkspace v-if="config" :config="config" />
</PageDataState>
</template>

<script>
import { withDatabasePage } from '../utils/databasePage'
import FeatureWorkspace from '../components/FeatureWorkspace.vue'
import { getDegreeDefenseData } from '../services/dataService'

export default withDatabasePage({
  components: { FeatureWorkspace },
  data() {
    return {
      config: null,
    }
  },
  async mounted() {
    this.config = await getDegreeDefenseData()
  },
})
</script>
