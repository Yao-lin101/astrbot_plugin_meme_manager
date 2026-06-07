export const DangerConfirmDialog = {
  name: 'DangerConfirmDialog',
  props: {
    dialog: {
      type: Object,
      required: true
    }
  },
  emits: ['start-countdown', 'confirm', 'cancel'],
  template: `
    <div v-if="dialog.visible" class="danger-modal" role="dialog" aria-modal="true">
      <div class="danger-modal-card">
        <h2>{{ dialog.title }}</h2>
        <p>{{ dialog.description }}</p>

        <div v-if="dialog.stage === 'ack'" class="danger-modal-check">
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary);">
            <input type="checkbox" @change="$emit('start-countdown')" />
            <span>我已了解此操作的风险和影响</span>
          </label>
        </div>
        <div v-else-if="dialog.stage === 'countdown'" class="danger-modal-stage-text">
          请在 {{ dialog.countdown }} 秒后确认操作
        </div>
        <div v-else-if="dialog.stage === 'input'" class="danger-modal-check">
          <p>请输入 <strong>CONFIRM</strong> 以确认此项敏感操作：</p>
          <input type="text" id="danger-modal-ack" class="form-control text-center" @keyup.enter="$emit('confirm')" />
        </div>

        <div class="danger-modal-actions">
          <button class="btn-secondary" @click="$emit('cancel')">取消</button>
          <button class="btn-danger" :disabled="dialog.stage !== 'input'" @click="$emit('confirm')">
            {{ dialog.actionLabel }}
          </button>
        </div>
      </div>
    </div>
  `
};
