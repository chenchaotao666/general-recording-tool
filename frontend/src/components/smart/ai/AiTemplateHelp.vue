<template>
  <el-popover :visible="open" trigger="click" placement="right-start" :fallback-placements="['left-start']"
              :width="460" :offset="12" :show-arrow="false" :hide-after="0" :popper-options="popperOptions"
              popper-class="st-tbpanel ai-selected-template-pop">
    <template #reference>
      <div ref="triggerRef" role="button" tabindex="0" @keydown.enter.self.prevent="show" @keydown.space.self.prevent="show" class="ati-help-trigger" :class="{ 'ati-help-calculation': scene.formulaDisplay || (scene.local && scene.calculationLogic) }" :aria-expanded="open" aria-label="查看模板介绍与效果示例"
              @mouseenter="show" @mouseleave="scheduleHide" @focus="show" @blur="scheduleHide" @click="show" @keydown.esc.stop.prevent="close">
        <template v-if="scene.formulaDisplay">
          <span class="ati-help-caption">使用公式计算</span>
          <span class="ati-help-actions">
            <button type="button" aria-label="编辑公式" title="编辑公式" @click.stop="editFormula"><StIcon name="pencil" :size="16" /></button>
            <button type="button" aria-label="复制公式" title="复制公式" @click.stop="copyFormula"><StIcon name="copy" :size="16" /></button>
          </span>
          <span class="ati-help-content ati-help-formula"><template v-for="(part, index) in formulaParts" :key="index"><span v-if="part.field" class="ati-help-field">{{ part.text }}</span><template v-else>{{ part.text }}</template></template></span>
        </template>
        <template v-else-if="scene.local && scene.calculationLogic">
          <span class="ati-help-caption">{{ scene.asset ? '处理逻辑' : '计算逻辑' }}</span>
          <span class="ati-help-content">{{ scene.calculationLogic }}</span>
        </template>
        <span v-else>{{ (scene.desc || scene.label || '').replaceAll('{input}', '所选字段') }}</span>
      </div>
    </template>
    <aside ref="detailRef" class="ati-help-detail" aria-label="已选模板详情" @mouseenter="cancelHide" @mouseleave="scheduleHide" @focusin="cancelHide" @focusout="scheduleHide" @keydown.esc.stop.prevent="close">
      <AiTemplateIntro :key="scene.key" :scene="scene" expanded standalone />
    </aside>
  </el-popover>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AiTemplateIntro from './AiTemplateIntro.vue'
import StIcon from '../icons/StIcon.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
const props = defineProps({ scene: { type: Object, required: true } })
const emit = defineEmits(['edit-formula'])
async function editFormula() {
  close()
  try {
    await ElMessageBox.confirm('编辑公式内容需要将 AI 字段转为公式字段', '', {
      confirmButtonText: '继续编辑', cancelButtonText: '取消', closeOnClickModal: false,
    })
    emit('edit-formula')
  } catch { /* Cancel keeps the AI field unchanged. */ }
}
async function copyFormula() {
  try {
    await navigator.clipboard.writeText(props.scene.formulaDisplay || '')
    ElMessage.success('公式已复制')
  } catch { ElMessage.error('复制失败，请重试') }
}
// Preserve quoted literals; only actual bracketed references become field chips.
const formulaParts = computed(() => (props.scene.formulaDisplay || '').match(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\[[^\]]+\]|[^"'\[]+|./g)?.map(text => ({
  field: text.startsWith('[') && text.endsWith(']'),
  text: text.startsWith('[') && text.endsWith(']') ? text.slice(1, -1) : text,
})) || [])
const open = ref(false)
const triggerRef = ref(null), detailRef = ref(null)
let hideTimer
function cancelHide() { clearTimeout(hideTimer) }
function show() { cancelHide(); open.value = true }
function close() { cancelHide(); open.value = false }
function scheduleHide() { cancelHide(); hideTimer = setTimeout(close, 200) }
onBeforeUnmount(cancelHide)
// Keep one owner of visibility: the trigger and teleported details are one area.
// Popover's delayed click updates must not undo the explicit button toggle.
function onOutsidePointer(event) {
  if (![triggerRef.value, detailRef.value].some(el => el?.contains(event.target))) close()
}
onMounted(() => document.addEventListener('pointerdown', onOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutsidePointer))
watch(() => props.scene.key, close)
const popperOptions = {
  strategy: 'fixed',
  modifiers: [{ name: 'preventOverflow', options: { boundary: 'viewport', rootBoundary: 'viewport', padding: 12, tether: false } }],
}
</script>

<style>
.ai-selected-template-pop.st-tbpanel.el-popover.el-popper { padding: 0; max-width: calc(100vw - 24px); box-sizing: border-box; overflow: hidden; }
</style>
<style scoped>
.ati-help-trigger { display: block; width: 100%; box-sizing: border-box; padding: 8px 12px; border: 1px solid #E5E6EB; border-radius: 6px; background: #FFFFFF; color: var(--st-text-2); font: inherit; line-height: 1.6; cursor: pointer; text-align: left; overflow-wrap: anywhere; transition: background-color .15s, border-color .15s; }
.ati-help-trigger:hover, .ati-help-trigger:focus-visible { background: #F7F8FA; }
.ati-help-trigger { font-size: 14px; }
.ati-help-content { white-space: pre-wrap; }
.ati-help-trigger { position: relative; }
.ati-help-actions { position: absolute; top: 6px; right: 8px; display: flex; gap: 4px; opacity: 0; pointer-events: none; }
.ati-help-trigger:hover .ati-help-actions, .ati-help-trigger:focus-within .ati-help-actions { opacity: 1; pointer-events: auto; }
.ati-help-actions button { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; padding: 0; border: 0; border-radius: 4px; background: transparent; color: #86909C; cursor: pointer; }
.ati-help-actions button:hover { background: #E5E6EB; color: #4E5969; }
.ati-help-caption { padding-right: 64px; }
.ati-help-calculation { background: #F7F7F9; border-color: transparent; padding: 10px 12px; border-radius: 8px; }
.ati-help-calculation:hover, .ati-help-calculation:focus-visible { background: #F0F1F3; }
.ati-help-caption { display: block; margin-bottom: 6px; color: #86909C; }
.ati-help-formula { font-family: Consolas, 'SFMono-Regular', monospace; line-height: 2; }
.ati-help-field { display: inline-block; vertical-align: baseline; max-width: 100%; box-sizing: border-box; margin: 0 2px; padding: 0 6px; border: 1px solid #69B1FF; border-radius: 12px; background: #E6F4FF; color: #334155; font-family: inherit; line-height: 22px; overflow-wrap: anywhere; }
.ati-help-trigger:focus-visible { outline: 2px solid var(--st-primary); outline-offset: 2px; }
.ati-help-detail { padding: 16px; box-sizing: border-box; max-height: calc(100dvh - 24px); overflow-y: auto; overflow-x: hidden; scrollbar-width: none; overscroll-behavior: contain; background: linear-gradient(145deg, #F6F0FC, #F7F8FA 150px); }
.ati-help-detail::-webkit-scrollbar { display: none; }
</style>
