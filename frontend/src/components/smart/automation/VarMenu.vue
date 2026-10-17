<template>
  <!-- 变量菜单（§11.2 变量系统）：仪表盘ⓘ / 分析报告ⓘ / 自然时间 / 第 N 步的 —— 二级飞出，
       对齐参照 右上角工具栏-新建自动化提醒.png（悬停ⓘ提示「插入的仪表盘将以图片形式展示」） -->
  <div class="vm" :style="posStyle" @mousedown.prevent @click.stop>
    <div v-if="!valueMode" class="vm-item has-sub" @mouseenter="hover = 'dash'">
      仪表盘
      <el-tooltip content="插入的仪表盘将以链接形式展示" placement="top"><StIcon name="info" :size="13" class="vm-i" /></el-tooltip>
      <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'dash'" class="vm-sub">
        <div v-for="d in dashboards" :key="d.id" class="vm-item"
             @click="pick({ kind: 'dashboard', entryId: d.id, name: d.name }, `仪表盘 ${d.name}`)">
          <StIcon name="dashboard" :size="14" />{{ d.name }}
        </div>
        <div v-if="!dashboards.length" class="vm-empty">暂无仪表盘</div>
      </div>
    </div>
    <div v-if="!valueMode" class="vm-item has-sub" @mouseenter="hover = 'report'">
      分析报告
      <el-tooltip content="插入的分析报告将以链接形式展示" placement="top"><StIcon name="info" :size="13" class="vm-i" /></el-tooltip>
      <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'report'" class="vm-sub">
        <div class="vm-empty">暂无分析报告</div>
      </div>
    </div>
    <div class="vm-item has-sub" @mouseenter="hover = 'time'">
      自然时间 <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'time'" class="vm-sub">
        <div class="vm-item" @click="pick({ kind: 'time', key: 'today' }, '今天')">今天</div>
        <div class="vm-item" @click="pick({ kind: 'time', key: 'now' }, '现在')">现在</div>
      </div>
    </div>
    <div v-for="s in steps" :key="s.step" class="vm-item has-sub" @mouseenter="hover = `s${s.step}`">
      第{{ s.step }}步的 <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === `s${s.step}`" class="vm-sub vm-sub-scroll">
        <div v-for="v in s.vars" :key="v.key" class="vm-item"
             @click="pick(v.var, `第${s.step}步${s.name}的 ${v.label}`)">
          <StIcon :name="v.icon || 'text'" :size="14" />{{ v.label }}
        </div>
        <div v-if="!s.vars.length" class="vm-empty">该步骤没有可用变量</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },        // [{step, name, vars: [{key, label, icon, var}]}]
  dashboards: { type: Array, default: () => [] },   // [{id, name}]
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  valueMode: { type: Boolean, default: false },     // 赋值场景：只给时间与步骤变量
})
const emit = defineEmits(['pick'])
const hover = ref(null)
const posStyle = computed(() => ({
  left: `${Math.min(props.x, window.innerWidth - 480)}px`,
  top: `${Math.min(props.y, window.innerHeight - 220)}px`,
}))
function pick(v, label) { emit('pick', v, label) }
</script>

<style scoped>
.vm { position: fixed; z-index: 4000; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 6px; min-width: 220px; }
.vm-item { position: relative; display: flex; align-items: center; gap: 8px; padding: 9px 14px; border-radius: 6px; cursor: pointer; font-size: 14px; color: var(--st-text-1); white-space: nowrap; }
.vm-item:hover { background: var(--st-bg-hover); }
.vm-item .st-icon { color: var(--st-text-2); }
.vm-i { color: var(--st-text-3) !important; }
.vm-caret { margin-left: auto; color: var(--st-text-3) !important; }
.vm-sub { position: absolute; left: calc(100% + 4px); top: -6px; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 6px; min-width: 220px; }
.vm-sub-scroll { max-height: 320px; overflow: auto; }
.vm-empty { padding: 9px 14px; font-size: 13px; color: var(--st-text-4); }
</style>
