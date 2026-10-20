<template>
  <router-view v-slot="{ Component, route }">
    <KeepAlive :max="8">
      <component :is="Component" v-if="Component" :key="route.path" />
    </KeepAlive>
    <el-empty v-if="!Component" :description="loading ? '正在加载…' : '从左侧选择或新建工作表'" />
  </router-view>
</template>

<script setup>
defineProps({ loading: Boolean })
</script>
