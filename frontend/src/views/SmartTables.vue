<template>
  <div class="smart-page">
    <el-card shadow="never" class="hero">
      <div class="hero-inner">
        <el-icon class="hero-icon"><Tickets /></el-icon>
        <h2>智能表</h2>
        <p class="desc">
          类似 Excel 的在线表格 + 数据库：26 种字段类型、多视图（筛选/分组/排序/填色）、
          关联与公式、自动化提醒、表单收集、行列级权限、AI 字段。
        </p>
        <el-button type="primary" disabled>新建智能表（V1 开发中）</el-button>
        <p class="hint">设计文档：docs/智慧表格设计文档.md ｜ 实施计划：V1 MVP</p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { Tickets } from '@element-plus/icons-vue'
</script>

<style scoped>
.smart-page { padding: 24px; }
.hero { border: 1px solid var(--el-border-color-lighter); }
.hero-inner {
  display: flex; flex-direction: column; align-items: center;
  padding: 80px 0; gap: 12px; text-align: center;
}
.hero-icon { font-size: 48px; color: var(--el-color-primary); }
h2 { margin: 0; }
.desc { max-width: 560px; color: var(--el-text-color-secondary); line-height: 1.8; margin: 0; }
.hint { color: var(--el-text-color-placeholder); font-size: 12px; margin: 8px 0 0; }
</style>
