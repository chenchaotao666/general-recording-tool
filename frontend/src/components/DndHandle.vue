<!-- 拖拽把手：六点 grip，纯视觉提示（整行可拖，拖动事件在行元素上）；仅在父条目 hover 时可见。
     样式在 styles/tree-dnd.css，配合 useTreeDnd 使用 -->
<template>
  <span class="dnd-handle" title="拖动排序" @click.stop><i v-for="d in 6" :key="d" /></span>
</template>
