export const CategoryRenameModal = {
  name: 'CategoryRenameModal',
  props: {
    dialog: {
      type: Object,
      required: true
    }
  },
  emits: ['close', 'save'],
  template: `
    <div v-if="dialog.visible" class="category-edit-modal" role="dialog" aria-modal="true">
      <div class="category-edit-modal-card">
        <p class="category-edit-modal-eyebrow">标签管理</p>
        <h2>重命名标签</h2>
        <p>重命名标签 「{{ dialog.originalCategory }}」 及其关联 of 表情包。</p>
        <div class="category-edit-form-panel">
          <label>新标签名称</label>
          <input type="text" v-model="dialog.category" class="form-control" placeholder="请输入新标签名称" />
        </div>
        <div class="category-edit-modal-actions">
          <button class="btn-secondary" @click="$emit('close')">取消</button>
          <button class="btn-primary" @click="$emit('save')">
            保存修改
          </button>
        </div>
      </div>
    </div>
  `
};
