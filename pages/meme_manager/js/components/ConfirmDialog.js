export const ConfirmDialog = {
  name: 'ConfirmDialog',
  props: {
    dialog: {
      type: Object,
      required: true
    }
  },
  emits: ['confirm'],
  template: `
    <div v-if="dialog.visible" class="confirm-modal" role="dialog" aria-modal="true">
      <div class="confirm-modal-card">
        <h2>{{ dialog.title }}</h2>
        <p>{{ dialog.description }}</p>
        <div v-if="dialog.imageUrl || dialog.localImageUrl" class="confirm-modal-comparison">
          <div v-if="dialog.localImageUrl" class="comparison-column">
            <div class="comparison-label">新上传的图片</div>
            <img :src="dialog.localImageUrl" alt="Uploading Meme" />
          </div>
          <div v-if="dialog.imageUrl && dialog.localImageUrl" class="comparison-separator">
            <i class="fas fa-arrows-left-right"></i>
          </div>
          <div v-if="dialog.imageUrl" class="comparison-column">
            <div class="comparison-label">已有的相似表情</div>
            <img :src="dialog.imageUrl" alt="Similar Meme" />
          </div>
        </div>
        <div class="confirm-modal-actions">
          <button class="btn-secondary" @click="$emit('confirm', false)">取消</button>
          <button :class="dialog.confirmClass === 'danger' ? 'btn-danger' : 'btn-primary'" @click="$emit('confirm', true)">
            {{ dialog.confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  `
};
