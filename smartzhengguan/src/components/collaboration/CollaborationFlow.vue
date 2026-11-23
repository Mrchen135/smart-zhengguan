<template>
  <ol class="collaboration-flow" aria-label="端云协同处理过程" aria-live="polite">
    <li v-for="(step,index) in steps" :key="step.title" class="flow-step" :class="step.status">
      <div class="step-caption"><span class="step-number">{{ String(index+1).padStart(2,'0') }}</span><span>{{ step.title }}</span><span v-if="step.status==='done'" class="step-check">✓</span></div>
      <strong>{{ step.value }}</strong><p>{{ step.caption }}</p>
    </li>
  </ol>
</template>
<script setup>
defineProps({ steps: { type: Array, required: true } })
</script>
<style scoped>
.collaboration-flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:0;margin:0;list-style:none}.flow-step{position:relative;border:1px solid #e0e8f0;background:#f8fafc;border-radius:12px;padding:16px;min-width:0}.step-caption{display:flex;gap:8px;align-items:center;color:#688094;font-size:12px}.step-number{font:11px/1.8 Consolas,monospace;letter-spacing:1px;color:#8199ac}.step-check{margin-left:auto;color:#278777}.flow-step strong{display:block;font-size:19px;line-height:1.6;color:#2c4c68;margin:10px 0 5px}.flow-step p{font-size:11px;color:#74899b;line-height:1.7;margin:0}.flow-step.done{background:#f0f8f6;border-color:#d8ebe4}.flow-step.done strong{color:#286d62}.flow-step.blocked{background:#fff8eb;border-color:#f0dfbc}.flow-step.blocked strong{color:#9b6b24}.flow-step.active{background:#eff5ff;border-color:#9dbbe2}.flow-step.active strong{color:#285f9e}@media(max-width:1100px){.collaboration-flow{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.flow-step{padding:12px}.flow-step strong{font-size:16px}}
</style>
