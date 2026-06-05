export const BatchPersonaModal = {
  name: 'BatchPersonaModal',
  props: {
    dialog: {
      type: Object,
      required: true
    },
    systemPersonas: {
      type: Array,
      required: true
    },
    selectedCount: {
      type: Number,
      required: true
    }
  },
  emits: ['close', 'save', 'toggle-persona'],
  template: `
    <div v-if="dialog.visible" class="move-target-modal" role="dialog" aria-modal="true">
      <div class="move-target-modal-card">
        <p class="move-target-modal-eyebrow">批量设置</p>
        <h2>允许的人格限制</h2>
        <p>修改已选中的 {{ selectedCount }} 个表情的人格可用性限制（留空或勾选全部表示全局可用）。</p>
        
        <div class="drawer-personas-list" style="margin: 20px 0; text-align: left; max-height: 250px; overflow-y: auto; padding: 10px; border: 1px solid var(--border-color); border-radius: 6px;">
          <label style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px; cursor: pointer; color: var(--text-primary); text-transform: none; letter-spacing: normal;">
            <input type="checkbox" value="*" :checked="dialog.personas.includes('*')" @change="$emit('toggle-persona', '*')" style="width: 14px; height: 14px;" />
            <span>全局可用 (*)</span>
          </label>
          <label v-for="p in systemPersonas" :key="p.id" style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px; cursor: pointer; color: var(--text-primary); text-transform: none; letter-spacing: normal;">
            <input type="checkbox" :value="p.id" :checked="dialog.personas.includes(p.id) && !dialog.personas.includes('*')" @change="$emit('toggle-persona', p.id)" style="width: 14px; height: 14px;" />
            <span>{{ p.name }} ({{ p.id }})</span>
          </label>
        </div>
        
        <div class="confirm-modal-actions" style="margin-top: 20px; display: flex; justify-content: flex-end; gap: 8px;">
          <button class="btn-secondary" @click="$emit('close')">取消</button>
          <button class="btn-primary" @click="$emit('save')">
            保存修改
          </button>
        </div>
      </div>
    </div>
  `
};
