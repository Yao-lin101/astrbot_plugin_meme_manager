export const ContextMenu = {
  name: 'ContextMenu',
  props: {
    menu: {
      type: Object,
      required: true
    }
  },
  emits: ['delete', 'move', 'copy', 'convert-gif', 'paste'],
  template: `
    <div v-if="menu.visible" 
         class="batch-context-menu" 
         :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
         @click.stop>
      <div class="batch-context-menu-header">
        <p>
          批量管理 ({{ menu.targetItems.length }} 个文件)
        </p>
      </div>
      <div class="batch-context-menu-actions">
        <button class="danger" @click="$emit('delete')">
          <i class="fas fa-trash-can icon"></i>删除文件
        </button>
        <button class="secondary" @click="$emit('move')">
          <i class="fas fa-right-left icon"></i>移动文件
        </button>
        <button class="secondary" @click="$emit('copy')">
          <i class="fas fa-copy icon"></i>复制文件
        </button>
        <button class="secondary" @click="$emit('convert-gif')">
          <i class="fas fa-file-image icon"></i>转换为 GIF
        </button>
        <button :disabled="menu.pasteableItems.length === 0" @click="$emit('paste')">
          <i class="fas fa-paste icon"></i>粘贴文件 ({{ menu.pasteableItems.length }})
        </button>
      </div>
    </div>
  `
};
