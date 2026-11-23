// Keep each page's existing chart setup, but make initial API failures reviewable.
export function withDatabasePage(options) {
  const originalData = options.data
  const originalMounted = options.mounted
  return {
    ...options,
    data() { return { ...originalData?.call(this), dataLoading: true, dataError: '' } },
    async mounted() { await this.retryDatabasePage() },
    methods: {
      ...options.methods,
      async retryDatabasePage() {
        this.dataLoading = true
        this.dataError = ''
        try { await originalMounted?.call(this) }
        catch (error) { this.dataError = error.message || '无法连接后端服务，请重试' }
        finally { this.dataLoading = false }
      },
    },
  }
}
