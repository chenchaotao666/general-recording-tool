<template>
  <div class="smart-menu"><slot /></div>
</template>

<style scoped>
.smart-menu { position: fixed; box-sizing: border-box; background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: min(170px, calc(100vw - 16px)); max-width: calc(100vw - 16px); max-height: calc(100vh - 16px); max-height: calc(100dvh - 16px); overflow: auto; overscroll-behavior: contain; color: var(--st-text-2); font-size: var(--st-font-size); }
.smart-menu :deep(.mi) { display: flex; align-items: center; gap: 8px; padding: 0 12px; height: var(--st-list-item-height); box-sizing: border-box; border: 0; border-radius: 4px; background: transparent; font: inherit; text-align: left; cursor: pointer; white-space: nowrap; color: var(--st-text-2); }
.smart-menu :deep(.mi .st-icon) { flex-shrink: 0; color: inherit; }
.smart-menu :deep(.mi:hover:not(:disabled):not(.disabled)), .smart-menu :deep(.mi:focus-visible:not(:disabled)) { background: var(--st-bg-hover); }
.smart-menu :deep(.mi:focus-visible) { outline: 1px solid var(--st-primary); outline-offset: -1px; }
.smart-menu :deep(.mi.disabled), .smart-menu :deep(.mi:disabled) { color: var(--st-disabled); cursor: not-allowed; }
.smart-menu :deep(.mi.danger) { color: var(--el-color-danger); }
.smart-menu :deep(.fm-divider) { height: 1px; background: var(--st-border); margin: 4px 6px; }
.smart-menu :deep(.fm-sub) { position: fixed; z-index: 1; box-sizing: border-box; background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: 140px; max-width: calc(100vw - 16px); max-height: calc(100vh - 16px); max-height: calc(100dvh - 16px); overflow: auto; overscroll-behavior: contain; }
</style>
