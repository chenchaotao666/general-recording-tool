<template>
  <!-- 带 {变量} 高亮的文本框：透明文字的 textarea 叠在高亮背板上（光标/选区仍由 textarea 提供），滚动同步 -->
  <div class="hl-wrap">
    <div ref="backdrop" class="backdrop" aria-hidden="true"><span v-html="highlighted" /></div>
    <el-input ref="inp" type="textarea" :rows="rows" :autosize="autosize" :model-value="modelValue"
      :placeholder="placeholder" class="hl-textarea" @update:model-value="$emit('update:modelValue', $event)" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  rows: { type: [Number, String], default: undefined },        // 固定行数
  autosize: { type: [Object, Boolean], default: false },       // 自适应 {minRows, maxRows}（与 rows 二选一）
  placeholder: { type: String, default: '' },
})
defineEmits(['update:modelValue'])

const inp = ref(null)
const backdrop = ref(null)

// {var} / {{var}} 渲染成高亮胶囊；先转义 HTML 防注入
const highlighted = computed(() => {
  const esc = (props.modelValue || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 末尾补一个空行占位：textarea 里最后的换行有高度，背板没有会对不齐
  return esc.replace(/(\{\{?[^{}]+\}?\})/g, '<span class="tok">$1</span>') + '\n'
})

function textareaEl() {
  return inp.value?.textarea || inp.value?.$el?.querySelector('textarea')
}
defineExpose({ textareaEl })   // 供外层做光标处插入

// 背板滚动跟随 textarea（内容超长时高亮不错位）
onMounted(() => {
  const ta = textareaEl()
  ta?.addEventListener('scroll', () => {
    if (backdrop.value) {
      backdrop.value.scrollTop = ta.scrollTop
      backdrop.value.scrollLeft = ta.scrollLeft
    }
  })
})
</script>

<style scoped>
.hl-wrap { position: relative; }
/* 背板与 textarea 字体/内边距必须完全一致，高亮才对齐。
   注意 EP 2.x 的 textarea 边框是 box-shadow inset 画的、border:none 不占布局，
   背板 inset 必须是 0（写 1px 会导致背板文字右移，光标看起来压在字符上） */
.backdrop {
  position: absolute; inset: 0; overflow: hidden; pointer-events: none;
  padding: 5px 11px; font-size: 12px; line-height: 1.5; font-family: inherit;
  white-space: pre-wrap; word-break: break-all; color: #303133; box-sizing: border-box;
}
.backdrop :deep(.tok) {
  /* 胶囊内边距必须配等量负 margin：padding 会参与行内布局、把后续文字和光标真实位置错开
     （caret 由透明文字的 textarea 渲染，背板文字右移一点看起来就是光标压在字符上） */
  background: #ecf5ff; color: #409eff; border-radius: 3px; padding: 0 1px; margin: 0 -1px;
}
/* textarea 文字透明（由背板显示），光标与选区保持可见 */
.hl-textarea :deep(.el-textarea__inner) {
  color: transparent; caret-color: #303133; background: transparent;
  font-size: 12px; line-height: 1.5; font-family: inherit;
  white-space: pre-wrap; word-break: break-all;
}
.hl-textarea :deep(.el-textarea__inner)::placeholder { color: #a8abb2; }
.hl-textarea :deep(.el-textarea__inner)::selection { background: rgba(64, 158, 255, .25); }
</style>
