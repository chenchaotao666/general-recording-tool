<template>
  <section v-if="scene" class="ati" :class="{ 'ati-standalone': standalone }" :aria-label="`${scene.label}模板介绍`">
    <div class="ati-head"><strong>{{ scene.label }}</strong><span class="ati-method">{{ scene.executionLabel || (scene.local ? '本地计算' : '使用模型生成') }}</span><span v-if="scene.scope === 'table'" class="ati-method">整表统计</span></div>
    <p>{{ (scene.desc || '').replaceAll('{input}', '所选字段') }}</p>
    <p v-if="scene.disabled" class="ati-unavailable">{{ scene.disabledReason || '该模板暂不可用' }}</p>
    <details :key="scene.key" :open="expanded">
      <summary v-show="!standalone">模板介绍与效果示例</summary>
      <dl v-if="!standalone"><dt>输入要求</dt><dd>{{ scene.inputHint || '选择相关字段作为输入' }}</dd><dt>输出结果</dt><dd>{{ outputLabel }}</dd></dl>
      <ul v-if="!standalone && scene.notes?.length"><li v-for="note in scene.notes" :key="note">{{ note }}</li></ul>
      <details v-if="!scene.local && scene.prompt" class="ati-prompt" :open="standalone"><summary>查看默认执行指令</summary><pre>{{ scene.prompt }}</pre></details>
      <details v-if="scene.formulaDisplay" class="ati-prompt" open><summary>使用公式计算</summary><pre>{{ scene.formulaDisplay }}</pre><small>按绑定字段执行此公式，不调用模型。复制到公式列时请替换为实际字段名。</small></details>
      <details v-else-if="scene.local && scene.calculationLogic" class="ati-prompt ati-logic" open><summary>{{ scene.asset ? '处理逻辑' : '计算逻辑' }}</summary><pre>{{ scene.calculationLogic }}</pre></details>
      <div v-if="scene.sample" class="ati-example"><span>示例数据 · 非当前表试算结果</span><AiSceneCard bare :sample="scene.sample" :output-type="scene.outputType" /></div>
      <p v-else class="ati-tip">选择输入字段后，可通过“生成预览”查看当前表的实际处理结果。</p>
      <details v-if="standalone" class="ati-usage" open><summary>输入要求与使用说明</summary>
        <dl><dt>输入要求</dt><dd>{{ scene.inputHint || '选择相关字段作为输入' }}</dd><dt>输出结果</dt><dd>{{ outputLabel }}</dd></dl>
        <ul v-if="scene.notes?.length"><li v-for="note in scene.notes" :key="note">{{ note }}</li></ul>
      </details>
    </details>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AiSceneCard from './AiSceneCard.vue'
const props = defineProps({ scene: Object, expanded: Boolean, standalone: Boolean })
const outputLabel = computed(() => ({ text: '文本', number: '数字', percent: '百分比', progress: '进度', date: '日期', singleSelect: '单选标签', multiSelect: '多选标签', checkbox: '复选框', file: '可下载附件' })[props.scene?.outputType] || '文本')
</script>
<style scoped>
.ati { background: #F7F8FA; border: 1px solid #EBECEE; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.65; color: var(--st-text-2); overflow-wrap: anywhere; }
.ati-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--st-text-1); }
.ati-method { font-size: 12px; padding: 0 6px; background: #EAF1FE; color: #245BBD; border-radius: 4px; }
.ati p { margin: 8px 0; }
.ati summary { cursor: pointer; color: var(--st-primary); }
.ati dl { display: grid; grid-template-columns: 60px 1fr; gap: 6px 10px; margin: 10px 0; }
.ati dt { color: var(--st-text-3); }
.ati dd { margin: 0; }
.ati ul { margin: 8px 0; padding-left: 18px; }
.ati pre { white-space: pre-wrap; font: inherit; margin: 8px 0; max-height: 180px; overflow: auto; }
.ati-example { margin-top: 12px; }
.ati-example > span, .ati-tip { font-size: 12px; color: var(--st-text-3); }
.ati-example :deep(.asc-table) { margin-top: 6px; background: #fff; }
.ati-unavailable { color: #9A6700; }
.ati-standalone { padding: 0; border: 0; background: transparent; }
.ati-standalone .ati-head { padding-bottom: 12px; font-size: 16px; }
.ati-standalone > p { background: #fff; padding: 12px; border-radius: 8px; margin: 0 0 12px; line-height: 1.8; }
.ati-standalone .ati-prompt { padding: 12px; background: #fff; border-radius: 8px; }
.ati-standalone pre { max-height: none; }
.ati-logic pre { max-height: none; overflow: visible; }
.ati-standalone .ati-example :deep(.asc-ell) { white-space: normal; overflow-wrap: anywhere; }
.ati-standalone .ati-example :deep(.asc-td) { padding: 8px; }
.ati-usage { margin-top: 12px; }
</style>
