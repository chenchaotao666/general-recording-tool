<template>
  <el-popover v-model:visible="open" trigger="click" placement="bottom-start" :width="300"
              :hide-after="0" :show-arrow="false" popper-class="schedule-time-pop" @show="reset">
    <template #reference>
      <button type="button" class="st-control st-control--native stp-trigger">{{ modelValue || '09:00' }}<StIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" /></button>
    </template>
    <div class="stp-columns">
      <div ref="hours" class="stp-column" role="listbox" aria-label="小时">
        <button v-for="h in 24" :key="h" type="button" role="option" :aria-selected="hour === h - 1"
                :class="{ selected: hour === h - 1 }" @click="hour = h - 1; center()">{{ pad(h - 1) }}{{ hour === h - 1 ? '时' : '' }}</button>
      </div>
      <div ref="minutes" class="stp-column" role="listbox" aria-label="分钟">
        <button v-for="m in 60" :key="m" type="button" role="option" :aria-selected="minute === m - 1"
                :class="{ selected: minute === m - 1 }" @click="minute = m - 1; center()">{{ pad(m - 1) }}{{ minute === m - 1 ? '分' : '' }}</button>
      </div>
    </div>
    <div class="stp-footer">
      <button type="button" class="st-button stp-now" @click="now">此刻</button>
      <el-button class="st-button st-button--primary" type="primary" @click="confirm">确定</el-button>
    </div>
  </el-popover>
</template>
<script setup>
import { nextTick, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
const props = defineProps({ modelValue: { type: String, default: '09:00' } })
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const hour = ref(9)
const minute = ref(0)
const hours = ref(null)
const minutes = ref(null)
const pad = n => String(n).padStart(2, '0')
async function center() {
  await nextTick()
  if (hours.value) hours.value.scrollTop = hour.value * 36
  if (minutes.value) minutes.value.scrollTop = minute.value * 36
}
function reset() {
  const [h, m] = (props.modelValue || '09:00').split(':').map(Number)
  hour.value = h; minute.value = m
  center()
}
function now() {
  const time = new Date()
  hour.value = time.getHours(); minute.value = time.getMinutes()
  center()
}
function confirm() {
  emit('update:modelValue', `${pad(hour.value)}:${pad(minute.value)}`)
  open.value = false
}
</script>
<style scoped>
.stp-trigger { display: inline-flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 36px; padding: 6px 12px; background: #fff; border: 1px solid var(--st-border); border-radius: 5px; font: inherit; color: var(--st-text-2); cursor: pointer; }
.stp-columns { display: flex; padding: 6px; }
.stp-column { flex: 1; height: 252px; overflow-y: auto; scrollbar-width: thin; padding: 108px 0; box-sizing: border-box; }
.stp-column button { display: block; width: 100%; height: 36px; border: 0; background: transparent; font: inherit; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.stp-column button:hover { background: var(--st-bg-hover); }
.stp-column button.selected { background: #d6e7ff; color: var(--st-primary); }
.stp-footer { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-top: 1px solid var(--st-border); }
.stp-now { border: 0; background: transparent; color: var(--st-text-2); font: inherit; cursor: pointer; }
</style>
<style>
.schedule-time-pop.el-popover { padding: 0; border-radius: 10px; }
</style>
