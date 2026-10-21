<template>
  <el-dialog :model-value="visible" width="800px" class="contact-picker-dialog" append-to-body destroy-on-close :show-close="false" @update:model-value="$emit('close')">
    <div class="contact-picker" @mousedown.stop @click.stop>
      <section class="contact-source">
        <el-input v-model="query" placeholder="搜索" clearable :prefix-icon="Search" aria-label="搜索联系人" />
        <div class="contact-tree">
          <div v-if="error" class="contact-empty">{{ error }} <button @click="$emit('retry')">重试</button></div>
          <div v-else-if="loading" class="contact-empty">加载中…</div>
          <template v-else>
            <template v-for="section in sections" :key="section.key">
              <button class="contact-section" :aria-expanded="!collapsed[section.key]" @click="collapsed[section.key] = !collapsed[section.key]">
                <el-icon><ArrowRight v-if="collapsed[section.key]" /><ArrowDown v-else /></el-icon>
                <el-icon class="section-icon"><component :is="section.icon" /></el-icon>{{ section.name }}
              </button>
              <div v-if="!collapsed[section.key] || query">
                <template v-for="group in section.groups" :key="group.key">
                  <div v-if="group.name" class="contact-group">{{ group.name }}</div>
                  <button v-for="p in group.members" :key="p.id" class="contact-person" :class="{ selected: chosen.includes(p.id) }" :aria-pressed="chosen.includes(p.id)" @click="toggle(p.id)">
                    <span class="contact-check" :class="{ checked: chosen.includes(p.id) }">{{ chosen.includes(p.id) ? '✓' : '' }}</span>
                    <PersonAvatar :person="p" /><span class="person-name">{{ p.name }}</span>
                  </button>
                </template>
                <div v-if="!section.groups.some(g => g.members.length)" class="contact-empty">{{ query ? '无匹配联系人' : '暂无联系人' }}</div>
              </div>
            </template>
          </template>
        </div>
      </section>
      <section class="contact-selected">
        <header><strong>选择联系人</strong><span>已选择 {{ chosen.length }} 个联系人</span><button class="contact-icon" aria-label="关闭" @click="$emit('close')"><el-icon><Close /></el-icon></button></header>
        <div class="chosen-list">
          <div v-for="id in chosen" :key="id" class="chosen-person"><PersonAvatar :person="lookup(id)" /><span class="person-name">{{ lookup(id).name }}</span><button class="contact-icon" :aria-label="`移除${lookup(id).name}`" @click="toggle(id)"><el-icon><Close /></el-icon></button></div>
          <div v-if="!chosen.length" class="contact-empty">从左侧选择联系人</div>
        </div>
        <footer><el-button type="primary" @click="confirm">确定</el-button><el-button @click="$emit('close')">取消</el-button></footer>
      </section>
    </div>
  </el-dialog>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { Search, Close, ArrowRight, ArrowDown, UserFilled, OfficeBuilding, User } from '@element-plus/icons-vue'
import PersonAvatar from './PersonAvatar.vue'
import { person, selectedIds, togglePerson } from './people.js'
const props = defineProps({ visible: Boolean, modelValue: [Array, Number, String], multiple: { type: Boolean, default: true }, directory: Object, people: { type: Array, default: () => [] }, loading: Boolean, error: String })
const emit = defineEmits(['close', 'confirm', 'retry'])
const chosen = ref([]), query = ref(''), collapsed = ref({})
watch(() => props.visible, v => { if (v) { chosen.value = selectedIds(props.modelValue); query.value = '' } }, { immediate: true })
const sections = computed(() => {
  const d = props.directory || {}
  const filter = values => (values || []).map(person).filter(p => p.name.toLowerCase().includes(query.value.trim().toLowerCase()))
  return [
    { key: 'groups', name: '用户组', icon: UserFilled, groups: (d.groups || []).map(g => ({ key: g.id, name: g.name, members: filter(g.members) })) },
    { key: 'friends', name: '好友', icon: User, groups: [{ key: 'friends', members: filter(d.friends) }] },
    { key: 'enterprise', name: d.enterprise?.name || '企业成员', icon: OfficeBuilding, groups: [{ key: 'enterprise', members: filter(d.enterprise?.members || props.people) }] },
  ]
})
const allPeople = computed(() => [...props.people, ...(props.directory?.enterprise?.members || []), ...(props.directory?.friends || []), ...(props.directory?.groups || []).flatMap(g => g.members || [])].map(person))
const lookup = id => allPeople.value.find(p => p.id === id) || { id, name: `#${id}` }
function toggle(id) { chosen.value = togglePerson(chosen.value, id, props.multiple) }
function confirm() { emit('confirm', props.multiple ? [...chosen.value] : chosen.value[0] ?? null, chosen.value.map(lookup)) }
</script>
<style>
.el-dialog.contact-picker-dialog { padding: 0; border-radius: 10px; overflow: hidden; max-width: calc(100vw - 32px); }
.contact-picker-dialog .el-dialog__header { display: none; }
.contact-picker-dialog .el-dialog__body { padding: 0; }
</style>
<style scoped>
.contact-picker { display: grid; grid-template-columns: 1fr 1fr; height: min(640px, 75vh); color: #242830; font-size: 14px; }
.contact-source { background: #f5f6f8; padding: 24px 16px; display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.contact-source > .el-input { padding: 0 8px; box-sizing: border-box; margin-bottom: 20px; }
.contact-tree, .chosen-list { overflow-y: auto; flex: 1; min-height: 0; }
button { cursor: pointer; font: inherit; color: inherit; }
.contact-section { display: flex; align-items: center; gap: 10px; border: 0; background: transparent; width: 100%; padding: 12px 8px; text-align: left; border-radius: 6px; }
.section-icon { background: #6099f5; color: white; padding: 4px; border-radius: 3px; }
.contact-group { padding: 10px 16px 6px 40px; color: #7e8591; font-size: 13px; }
.contact-person { border: 0; background: transparent; display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 12px 8px 36px; margin-bottom: 4px; border-radius: 6px; text-align: left; }
.contact-person:hover, .contact-section:hover, .contact-icon:hover { background: #e9eaed; }
.contact-person.selected { background: #e1ecfc; }
.contact-check { width: 16px; height: 16px; border: 1px solid #aeb3ba; border-radius: 3px; background: white; flex: none; line-height: 16px; text-align: center; }
.contact-check.checked { background: #3080f5; border-color: #3080f5; color: white; }
.person-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.contact-selected { display: flex; flex-direction: column; min-height: 0; min-width: 0; padding: 24px; }
header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
header strong { font-size: 16px; white-space: nowrap; }
header > span { margin-left: auto; color: #8a929e; font-size: 12px; }
.contact-icon { border: 0; background: transparent; border-radius: 4px; width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; flex: none; color: #868c95; }
.chosen-person { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
footer { display: flex; gap: 12px; padding-top: 20px; }
footer .el-button { flex: 1; margin: 0; height: 36px; }
.contact-empty { padding: 16px; color: #959ca7; font-size: 13px; }
@media(max-width: 560px) { .contact-selected { padding: 12px; } .contact-source { padding: 12px 4px; } header { flex-wrap: wrap; gap: 4px; } .contact-person { padding-left: 8px; } }
</style>
