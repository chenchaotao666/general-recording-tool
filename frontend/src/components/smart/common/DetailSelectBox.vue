<template>
  <div class="detail-select-box"><slot /></div>
</template>

<style scoped>
.detail-select-box { position: relative; min-height: 38px; box-sizing: border-box; border-radius: 6px; }
/* One positioning container for every detail selector, including wrapped tags. */
.detail-select-box :deep(.people-trigger),
.detail-select-box :deep(.image-cell-trigger),
.detail-select-box :deep(.file-cell-trigger),
.detail-select-box :deep(.relation-trigger),
.detail-select-box :deep(.link-cell-trigger) { position: static; padding-right: 30px; }
.detail-select-box :deep(.cell-dropdown.cell-dropdown-overlay) {
  top: 50%; bottom: auto; right: 8px; transform: translateY(-50%);
  opacity: 0; pointer-events: none;
}
.detail-select-box:hover :deep(.cell-dropdown.cell-dropdown-overlay),
.detail-select-box:focus-within :deep(.cell-dropdown.cell-dropdown-overlay),
.detail-select-box :deep(.cell-dropdown.cell-dropdown-overlay.open) {
  opacity: 1; pointer-events: auto;
}
.detail-select-box :deep(.cell-dropdown.cell-dropdown-overlay.cell-dropdown-top) {
  top: 7px; bottom: auto; transform: none;
}
</style>
