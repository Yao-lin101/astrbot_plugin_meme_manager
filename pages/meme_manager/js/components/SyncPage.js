const VECTOR_STATUS_LABELS = {
  ready: '可用',
  empty: '待向量化',
  syncing: '补算中',
  rebuilding: '重建中',
  provider_unavailable: 'Embedding Provider 不可用',
  model_mismatch: '需要重构',
  error: '读取失败',
};

export const SyncPage = {
  name: 'SyncPage',
  props: {
    vectorChecking: {
      type: Boolean,
      required: true
    },
    vectorStatus: {
      type: Object,
      required: true
    },
    imgHostSyncing: {
      type: Boolean,
      required: true
    },
    imgHostStatus: {
      type: Object,
      required: true
    }
  },
  emits: ['refresh-vector-status', 'refresh-img-host', 'sync-to-remote', 'sync-from-remote'],
  computed: {
    vectorStatusLabel() {
      if (this.vectorChecking) return '读取中…';
      return VECTOR_STATUS_LABELS[this.vectorStatus.status] ?? '待读取';
    }
  },
  template: `
    <div class="config-container">
      <div style="display: grid; grid-template-columns: 1fr; gap: 24px; width: 100%;">
        <div class="sync-grid">
          <div class="config-card">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 8px;">
              <span class="config-card-title" style="border: none; padding-left: 0; display: flex; align-items: center; gap: 8px; margin-bottom: 0;">
                <i class="fas fa-database" style="color: var(--primary-color);" aria-hidden="true"></i>
                向量数据库状态
              </span>
              <button class="btn-secondary" style="padding: 4px 10px; font-size: 12px;" @click="$emit('refresh-vector-status')" :disabled="vectorChecking">
                <i class="fas fa-rotate" :class="{ 'fa-spin': vectorChecking }" aria-hidden="true"></i> 刷新状态
              </button>
            </div>

            <div class="vector-db-summary" aria-live="polite" :aria-busy="vectorChecking">
              <div class="vector-db-state">
                <span>LanceDB 缓存</span>
                <strong :data-state="vectorChecking ? 'loading' : vectorStatus.status">{{ vectorStatusLabel }}</strong>
              </div>
              <dl class="vector-db-metrics">
                <div>
                  <dt>向量维度</dt>
                  <dd>{{ vectorStatus.dimension ?? '—' }}</dd>
                </div>
                <div>
                  <dt>已向量化标签</dt>
                  <dd>{{ vectorStatus.tagCount ?? '—' }}</dd>
                </div>
              </dl>
            </div>
            <p v-if="vectorStatus.status === 'model_mismatch'" class="form-hint">
              更换模型后，执行 <code>/表情管理 重构向量缓存</code>。
            </p>
          </div>

          <!-- 云端图床同步卡片 -->
          <div class="config-card">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 8px;">
              <span class="config-card-title" style="border: none; padding-left: 0; display: flex; align-items: center; gap: 8px; margin-bottom: 0;">
                <i class="fas fa-cloud" style="color: var(--primary-color);"></i>
                图床云端同步
              </span>
              <button class="btn-secondary" style="padding: 4px 10px; font-size: 12px;" @click="$emit('refresh-img-host', true)" :disabled="imgHostSyncing">
                <i class="fas fa-rotate" :class="{ 'fa-spin': imgHostSyncing }"></i> 刷新图床
              </button>
            </div>

            <p class="form-hint">
              将本地表情包图片同步到配置的外部云图床（R2 或 Stardots），用于在外部网络环境下正常展示图片，减少流量消耗。
            </p>

            <div style="min-height: 120px; display: flex; flex-direction: column; justify-content: center; gap: 8px; background: var(--btn-default-bg); border-radius: var(--radius-md); border: 1px solid var(--border-color); padding: 16px;">
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--text-secondary);">图床服务商</span>
                <span style="font-weight: 700;">{{ imgHostStatus.provider }}</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--text-secondary);">云端文件</span>
                <span style="font-weight: 700; font-family: monospace;">{{ imgHostStatus.remoteImageCount }} 张 ({{ imgHostStatus.remoteStorageSize }})</span>
              </div>
              
              <div style="border-top: 1px dashed var(--border-color); margin: 6px 0; padding-top: 6px;"></div>

              <div v-if="imgHostStatus.uploadCount > 0 || imgHostStatus.downloadCount > 0" style="display: flex; justify-content: space-between; align-items: center; font-size: 13px;">
                <span style="color: var(--text-secondary);">待同步数量</span>
                <div style="display: flex; gap: 6px;">
                  <span v-if="imgHostStatus.uploadCount > 0" style="font-size: 11px; background: rgba(59, 130, 246, 0.1); color: var(--primary-color); padding: 2px 8px; border-radius: 4px; font-weight: 600;">
                    <i class="fas fa-arrow-up"></i> {{ imgHostStatus.uploadCount }} 待上传
                  </span>
                  <span v-if="imgHostStatus.downloadCount > 0" style="font-size: 11px; background: rgba(245, 158, 11, 0.1); color: var(--warn-color); padding: 2px 8px; border-radius: 4px; font-weight: 600;">
                    <i class="fas fa-arrow-down"></i> {{ imgHostStatus.downloadCount }} 待下载
                  </span>
                </div>
              </div>
              <div v-else style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--text-secondary);">同步状态</span>
                <span style="color: var(--ok-color); font-weight: 600;"><i class="fas fa-circle-check"></i> 云端已同步</span>
              </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px;">
              <button class="btn-primary" @click="$emit('sync-to-remote')" :disabled="imgHostStatus.uploadCount === 0 || imgHostSyncing">
                <i class="fas fa-cloud-arrow-up"></i> 上传到云端
              </button>
              <button class="btn-primary" @click="$emit('sync-from-remote')" :disabled="imgHostStatus.downloadCount === 0 || imgHostSyncing">
                <i class="fas fa-cloud-arrow-down"></i> 从云端下载
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  `
};
