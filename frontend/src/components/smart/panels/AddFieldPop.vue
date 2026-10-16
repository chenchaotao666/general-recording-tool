<template>
  <!-- 添加列：锚定浮层（对齐参照 添加列-所有字段类型.png）：
       字段名输入（蓝下划线）→ AI 字段通栏入口 → 「选择字段类型」两列图标网格 → 底部快捷键提示。
       ↑↓←→ 移动，⏎ 选定，Tab 选定并继续添加下一列（emit pick-again），Esc 关闭 -->
  <div class="afp-mask" @click="$emit('close')" @contextmenu.prevent="$emit('close')">
    <div ref="popRef" class="afp" :style="{ left: `${pos.x}px`, top: `${pos.y}px` }" @click.stop @mousedown.stop>
      <input ref="nameRef" v-model="name" class="afp-name" placeholder="字段名称"
             @keydown="onKey" @keydown.esc.stop="$emit('close')" />
      <div class="afp-ai" @click="ai">
        <StIcon name="sparkle" :size="15" class="afp-ai-icon" />AI 字段
        <StIcon name="chevron-right" :size="13" class="afp-ai-caret" />
      </div>
      <div class="afp-divider" />
      <div class="afp-label">选择字段类型</div>
      <div class="afp-grid">
        <div v-for="(t, i) in typeList" :key="t.key" class="afp-type" :class="{ on: i === idx }"
             @mouseenter="idx = i" @click="pick(t, false)">
          <StIcon :name="t.key" :size="15" />{{ t.label }}
        </div>
      </div>
      <div class="afp-hint">↑↓ 选择　⏎ 完成　Tab 再添加一列</div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import { FIELD_REGISTRY } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  x: { type: Number, default: 200 },
  y: { type: Number, default: 100 },
})
const emit = defineEmits(['pick', 'pick-again', 'close'])

// 参照顺序：基础 → 协作/媒体 → 标识 → 关联 → 计算 → 系统（只列 FIELD_REGISTRY 支持的类型）
const ORDER = ['text', 'singleSelect', 'multiSelect', 'number', 'percent', 'currency', 'progress', 'date',
               'member', 'image', 'file', 'relation', 'url', 'phone', 'email', 'checkbox', 'autoNumber',
               'formula', 'lookup', 'createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime']
const typeList = computed(() => ORDER.filter(k => FIELD_REGISTRY[k]).map(k => ({ key: k, label: FIELD_REGISTRY[k].label })))

const name = ref('')
const idx = ref(0)
const nameRef = ref(null)
const popRef = ref(null)

// 位置钳制在视口内
const pos = computed(() => ({
  x: Math.max(8, Math.min(props.x, window.innerWidth - 500)),
  y: Math.max(8, Math.min(props.y, window.innerHeight - 480)),
}))

onMounted(async () => { await nextTick(); nameRef.value?.focus() })

function onKey(e) {
  const n = typeList.value.length
  if (e.key === 'ArrowDown') { e.preventDefault(); idx.value = Math.min(n - 1, idx.value + 2) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); idx.value = Math.max(0, idx.value - 2) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); idx.value = Math.min(n - 1, idx.value + 1) }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); idx.value = Math.max(0, idx.value - 1) }
  else if (e.key === 'Enter') { e.preventDefault(); pick(typeList.value[idx.value], false) }
  else if (e.key === 'Tab') { e.preventDefault(); pick(typeList.value[idx.value], true) }
}
function pick(t, again) {
  if (!t) return
  emit(again ? 'pick-again' : 'pick', { field_type: t.key, label: name.value.trim() })
}
function ai() { ElMessage.info('AI 字段将在后续版本提供，敬请期待') }
</script>

<style scoped>
.afp-mask { position: fixed; inset: 0; z-index: 3000; }
.afp {
  position: fixed; width: 480px; background: #fff; border-radius: 8px;
  box-shadow: var(--st-shadow-pop); padding: 16px 16px 10px; display: flex; flex-direction: column;
}
.afp-name {
  border: none; outline: none; font-size: 14px; padding: 4px 2px 8px; width: 100%;
  border-bottom: 2px solid var(--st-primary); box-sizing: border-box;
}
.afp-name::placeholder { color: var(--st-text-4); }
.afp-ai {
  display: flex; align-items: center; gap: 8px; padding: 10px 2px; margin-top: 6px;
  font-size: 13px; cursor: pointer; border-radius: 6px; color: var(--st-text-1);
}
.afp-ai:hover { background: var(--st-bg-hover); }
.afp-ai-icon { color: var(--st-ai); }
.afp-ai-caret { margin-left: auto; color: var(--st-text-3); }
.afp-divider { height: 1px; background: var(--st-border); margin: 4px 0; }
.afp-label { font-size: 12px; color: var(--st-text-3); padding: 6px 2px; }
.afp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; max-height: 380px; overflow: auto; }
.afp-type {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; font-size: 13px;
  cursor: pointer; border-radius: 6px; color: var(--st-text-1);
}
.afp-type .st-icon { color: var(--st-text-2); }
.afp-type.on { background: var(--st-bg-hover); }
.afp-hint { font-size: 11px; color: var(--st-text-4); padding: 8px 2px 2px; }
</style>
