export const ImportModal = {
  name: 'ImportModal',
  props: {
    dialog: {
      type: Object,
      required: true
    },
    activeCategory: {
      type: String,
      required: true
    },
    importableEmojisList: {
      type: Array,
      required: true
    },
    getImageUrl: {
      type: Function,
      required: true
    }
  },
  emits: ['close', 'submit', 'toggle-emoji'],
  template: `
    <div v-if="dialog.visible" class="emoji-detail-modal" role="dialog" aria-modal="true" @click.self="$emit('close')">
      <div class="emoji-detail-modal-card" style="max-width: 800px; width: 90%;">
        <div class="drawer-header">
          <span class="drawer-title">导入已存表情到标签「{{ activeCategory }}」</span>
          <button class="drawer-close-btn" @click="$emit('close')">&times;</button>
        </div>
        <div class="drawer-content" style="max-height: 50vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px;">
          <p style="margin-bottom: 15px; color: var(--text-secondary);">请选择要追加到当前分类的表情包（已选中 {{ dialog.selectedEmojis.size }} 个）：</p>
          <div v-if="importableEmojisList.length === 0" style="padding: 40px; text-align: center; color: var(--text-secondary);">
            没有可导入的其他表情包。
          </div>
          <div v-else class="emoji-grid" style="grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px;">
            <div v-for="emoji in importableEmojisList" 
                 :key="emoji" 
                 class="emoji-card" 
                 :class="{ active: dialog.selectedEmojis.has(emoji) }"
                 style="margin: 0;">
              <div class="emoji-item" 
                   :class="{ selected: dialog.selectedEmojis.has(emoji), 'selection-mode': true }"
                   :style="{ backgroundImage: 'url(' + getImageUrl(emoji, true) + ')', width: '100%', height: '100px', borderRadius: '6px' }"
                   @click="$emit('toggle-emoji', emoji)">
                 <button type="button" class="selection-indicator" aria-label="选择表情包"></button>
              </div>
            </div>
          </div>
        </div>
        <div class="drawer-actions" style="margin-top: 20px;">
          <button class="btn-secondary" @click="$emit('close')">取消</button>
          <button class="btn-primary" :disabled="dialog.selectedEmojis.size === 0" @click="$emit('submit')">确认导入</button>
        </div>
      </div>
    </div>
  `
};
