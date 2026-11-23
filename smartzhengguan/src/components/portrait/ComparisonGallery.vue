<template>
<section class="report-comparison-section">
      <div class="report-comparison-heading"><div class="report-kicker">COMPARISON / {{ comparison.acrossGrades?'同专业 · 跨年级比较':'多维度对比' }}</div><h2>{{ comparison.acrossGrades?'沿年级看培养与发展差异':'从结构、培养到发展去向' }}</h2><p>六张图直接展示；点击图中的年级或专业可联动解读。{{ comparison.acrossGrades?'这是不同入学年级的截面比较，不是同一批学生的时间趋势。':'' }}</p></div>
      <div class="report-selection"><span>{{ selected ? '正在解读：'+selected.grade+' · '+selected.major : '正在比较全部组合' }}</span><button v-if="selected" @click="$emit('clear')">清除选择</button><p v-if="selected">{{ selectedNarrative.findings[0] }} {{ selectedNarrative.recommendation }}</p></div>
      <div class="report-chart-grid"><article v-for="card in comparisonCharts" :key="card.id" class="report-chart-card"><header><h3>{{ card.title }}</h3><p>{{ card.subtitle }}</p></header><PortraitChart :options="card.options" :description="card.title" @select="$emit('select',$event)"/><div class="report-chart-conclusion"><b>读图结论</b><p>{{ card.conclusion }}</p></div></article></div>
      <div class="report-chart-grid report-structure-grid"><article class="report-chart-card"><header><h3>年级—专业—去向关联</h3><p>带宽表示人数；呈现当前分布，不表示个人的时间流转。</p></header><PortraitChart :options="sankeyOptions" description="年级、专业与去向结构" @select="$emit('select',$event)"/></article><article class="report-chart-card"><header><h3>群体与性别结构</h3><p>点击扇区选择对应年级专业组合。</p></header><PortraitChart :options="sunburstOptions" description="专业与性别构成" @select="$emit('select',$event)"/></article></div>
    </section>
</template>
<script setup>
import PortraitChart from './PortraitChart.vue'
defineProps(['comparison','selected','selectedNarrative','comparisonCharts','sankeyOptions','sunburstOptions'])
defineEmits(['select','clear'])
</script>
