<template>
  <div class="portrait-plot" ref="host" role="img" :aria-label="description"></div>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps({ options: { type: [Object, Function], required: true }, description: { type: String, required: true } })
const emit = defineEmits(['select'])
const host = ref(null)
let chart, observer, lastWidth = 0
const draw = () => {
  if (!host.value || !chart) return
  const width = host.value.clientWidth
  chart.resize()
  const options = typeof props.options === 'function' ? props.options(width) : props.options
  chart.setOption({ ...options, aria: { enabled: true, description: props.description } }, true)
  lastWidth = width
}
onMounted(() => {
  chart = echarts.init(host.value, null, { renderer: 'svg' })
  chart.on('click', params => emit('select', params))
  draw()
  observer = new ResizeObserver(() => { if (host.value.clientWidth !== lastWidth) draw(); else chart?.resize() })
  observer.observe(host.value)
})
watch(() => [props.options, props.description], draw, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
</script>
<style scoped>
.portrait-plot { width: 100%; height: 310px; min-width: 0; }
@media (max-width: 600px) { .portrait-plot { height: 300px; } }
</style>
