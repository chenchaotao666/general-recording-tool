<template>
  <span class="people-picker" @mousedown.stop @click.stop>
    <el-popover :visible="opened && !contacts" placement="bottom-start" :width="300" :show-arrow="false" popper-class="people-picker-pop" :persistent="false">
      <template #reference><div ref="trigger" class="people-trigger" @click="opened ? finish() : focus()"><span>{{ selectedNames }}</span><CellDropdown overlay flush :open="opened && !contacts" label="选择人员" @click="opened ? finish() : focus()" /></div></template>
      <div ref="panel" @mousedown.stop @click.stop @keydown.esc.stop.prevent="cancel">
        <div class="people-search"><el-input ref="search" v-model="query" placeholder="搜索成员" clearable aria-label="搜索成员" @keydown.enter="onEnter" @keydown.tab="onEnter" /></div>
        <div class="people-heading">企业成员</div>
        <div class="people-options">
          <div v-if="loading" class="people-empty">加载中…</div>
          <div v-else-if="error" class="people-empty">{{ error }} <button @click="load">重试</button></div>
          <template v-else>
            <button v-for="p in filtered" :key="p.id" class="people-option" :class="{ selected: chosen.includes(p.id) }" :aria-pressed="chosen.includes(p.id)" @click="pick(p)"><PersonAvatar :person="p" /><span>{{ p.name }}</span><el-icon v-if="chosen.includes(p.id)"><Check /></el-icon></button>
            <div v-if="!filtered.length" class="people-empty">{{ query ? '无匹配成员' : '暂无企业成员' }}</div>
          </template>
        </div>
        <button class="people-directory" @click="contacts = true">从通讯录选择...</button>
      </div>
    </el-popover>
    <ContactPickerDialog :visible="contacts" :model-value="chosen" :multiple="multiple" :directory="directory" :people="people" :loading="loading" :error="error" @retry="load" @close="closeContacts" @confirm="confirmContacts" />
  </span>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'
import CellDropdown from '../smart/grid/CellDropdown.vue'
import { getUserDirectory } from '../../api/index.js'
import ContactPickerDialog from './ContactPickerDialog.vue'
import PersonAvatar from './PersonAvatar.vue'
import { person, selectedIds, togglePerson } from './people.js'
const props = defineProps({ advanceOnEnter: Boolean, initialQuery: String, modelValue: [Array, Number, String], multiple: { type: Boolean, default: true }, people: { type: Array, default: () => [] }, loadDirectory: { type: Function, default: getUserDirectory } })
const emit = defineEmits(['advance', 'update:modelValue', 'confirm', 'cancel', 'people-loaded'])
const opened = ref(false), contacts = ref(false), query = ref(''), chosen = ref([]), directory = ref(null), loading = ref(false), error = ref('')
watch(() => props.initialQuery, value => { if (value != null) query.value = value })
const trigger = ref(null), panel = ref(null), search = ref(null)
watch(() => props.modelValue, v => { if (!opened.value) chosen.value = selectedIds(v) }, { immediate: true })
const enterprise = computed(() => (directory.value?.enterprise?.members || props.people).map(person))
const allPeople = computed(() => [...props.people, ...enterprise.value, ...(directory.value?.friends || []), ...(directory.value?.groups || []).flatMap(g => g.members || [])].map(person))
const selectedNames = computed(() => chosen.value.map(id => allPeople.value.find(p => p.id === id)?.name || `#${id}`).join('、'))
const filtered = computed(() => enterprise.value.filter(p => p.name.toLowerCase().includes(query.value.trim().toLowerCase())))
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try { directory.value = await props.loadDirectory(); emit('people-loaded', allPeople.value) }
  catch { error.value = '通讯录加载失败' }
  finally { loading.value = false }
}
async function focus() {
  chosen.value = selectedIds(props.modelValue); opened.value = true; query.value = props.initialQuery || ''
  if (!directory.value) load()
  await nextTick(); search.value?.focus()
}
function finish() {
  const value = props.multiple ? [...chosen.value] : chosen.value[0] ?? null
  opened.value = false; emit('update:modelValue', value); emit('confirm', value)
}
function pick(p) { chosen.value = togglePerson(chosen.value, p.id, props.multiple); if (!props.multiple) finish() }
function onEnter(event) {
  if (event.key === 'Tab' && !props.advanceOnEnter) return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault(); event.stopPropagation()
  if (!props.advanceOnEnter) { if (filtered.value[0]) pick(filtered.value[0]); return }
  const match = query.value.trim() ? filtered.value[0] : null
  if (match && !chosen.value.includes(match.id)) chosen.value = props.multiple ? [...chosen.value, match.id] : [match.id]
  finish(); emit('advance', event.key === 'Tab' ? (event.shiftKey ? 'left' : 'right') : event.shiftKey ? 'up' : 'down')
}
function cancel() { opened.value = false; emit('cancel') }
function closeContacts() { contacts.value = false; nextTick(() => search.value?.focus()) }
function confirmContacts(value, people) { chosen.value = selectedIds(value); contacts.value = false; emit('people-loaded', people); finish() }
function outside(e) { if (opened.value && !contacts.value && !trigger.value?.contains(e.target) && !panel.value?.contains(e.target)) finish() }
onMounted(() => document.addEventListener('mousedown', outside, true))
onBeforeUnmount(() => document.removeEventListener('mousedown', outside, true))
defineExpose({ focus })
</script>
<style>
.el-popper.people-picker-pop { padding: 0; border: 1px solid #dedfe3; border-radius: 8px; box-shadow: 0 4px 16px #0002; max-width: calc(100vw - 24px); }
</style>
<style scoped>
.people-picker { display: block; width: 100%; }
button { font: inherit; color: inherit; cursor: pointer; }
.people-trigger { position: relative; width: 100%; height: 100%; min-height: 28px; box-sizing: border-box; display: flex; align-items: center; border: 0; background: transparent; padding: 0 8px; color: #7f8590; }
.people-trigger span { flex: 1; text-align: left; color: #30343b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.people-search { padding: 12px 16px; border-bottom: 1px solid #edeef0; }
.people-search :deep(.el-input__wrapper) { box-shadow: none; padding: 0; }
.people-heading { padding: 12px 18px 6px; color: #969da8; font-size: 13px; }
.people-options { max-height: 240px; overflow-y: auto; padding: 0 6px 8px; }
.people-option { display: flex; align-items: center; gap: 10px; width: 100%; border: 0; background: transparent; border-radius: 6px; padding: 8px 12px; text-align: left; }
.people-option span:nth-child(2) { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.people-option:hover { background: #f1f2f4; }
.people-option.selected { background: #eaf1ff; }
.people-directory { display: block; width: 100%; padding: 14px 18px; text-align: left; background: transparent; border: 0; border-top: 1px solid #edeef0; border-radius: 0 0 8px 8px; }
.people-directory:hover { background: #f1f2f4; }
.people-empty { padding: 12px; color: #959ca7; font-size: 13px; }
</style>
