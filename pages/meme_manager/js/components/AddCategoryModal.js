export const AddCategoryModal = {
  name: 'AddCategoryModal',
  props: {
    form: {
      type: Object,
      required: true
    }
  },
  emits: ['close', 'save'],
  template: `
    <div v-if="form.visible" class="category-edit-modal" role="dialog" aria-modal="true">
      <div class="category-edit-modal-card">
        <p class="category-edit-modal-eyebrow">标签管理</p>
        <h2>添加新标签</h2>
        <div class="category-edit-form-panel">
          <label>标签名称</label>
          <input type="text" v-model="form.name" placeholder="标签名称" class="form-control" />
        </div>
        <div class="category-edit-modal-actions">
          <button class="btn-secondary" @click="$emit('close')">取消</button>
          <button class="btn-primary" @click="$emit('save')">
            保存标签
          </button>
        </div>
      </div>
    </div>
  `
};
