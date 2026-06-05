export const SyncDrawer = {
  name: 'SyncDrawer',
  props: {
    visible: {
      type: Boolean,
      required: true
    },
    checking: {
      type: Boolean,
      required: true
    },
    status: {
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
  emits: ['check-status', 'sync-config', 'remove-config', 'refresh-img-host', 'sync-to-remote', 'sync-from-remote'],
  template: `
    <div class="sync-drawer" v-show="visible">
      <div class="sync-grid">
        <!-- 本地配置同步卡片 -->
        <div class="sync-card">
          <div class="sync-card-header">
            <div class="sync-title">
              <i class="fas fa-arrows-spin header-icon"></i>
              <h3>配置与本地同步</h3>
            </div>
            <button class="btn-text" @click="$emit('check-status', true)" :disabled="checking">
              <i class="fas fa-sync" :class="{ 'fa-spin': checking }"></i> 检查状态
            </button>
          </div>
          <div class="sync-card-body">
            <div v-if="checking" class="loading-state">
              <i class="fas fa-circle-notch fa-spin"></i> 正在检查配置状态...
            </div>
            <div v-else>
              <div v-if="status.inSync" class="sync-status-ok">
                <i class="fas fa-circle-check"></i> 配置与文件夹结构一致！
              </div>
              <div v-else class="sync-status-warn">
                <div v-if="status.missingInConfig && status.missingInConfig.length > 0" class="sync-diff-group">
                  <h4>未注册的本地分类:</h4>
                  <div class="diff-tags">
                    <span v-for="cat in status.missingInConfig" :key="cat" class="diff-tag">
                      {{ cat }}
                    </span>
                  </div>
                </div>
                <div v-if="status.deletedCategories && status.deletedCategories.length > 0" class="sync-diff-group">
                  <h4>已删除的类别（配置残留）：</h4>
                  <div class="deleted-list">
                    <div v-for="cat in status.deletedCategories" :key="cat" class="deleted-item">
                      <span class="deleted-name">{{ cat }}</span>
                      <div class="deleted-actions">
                        <button class="btn-sm btn-danger" @click="$emit('remove-config', cat)">删除配置</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="sync-card-footer">
            <button class="btn-primary w-100" @click="$emit('sync-config')" :disabled="checking || status.inSync">
              <i class="fas fa-arrows-rotate"></i> 同步所有配置到本地
            </button>
          </div>
        </div>

        <!-- 云端图床同步卡片 -->
        <div class="sync-card">
          <div class="sync-card-header">
            <div class="sync-title">
              <i class="fas fa-cloud header-icon"></i>
              <h3>图床云端同步</h3>
            </div>
            <button class="btn-text" @click="$emit('refresh-img-host', true)" :disabled="imgHostSyncing">
              <i class="fas fa-rotate" :class="{ 'fa-spin': imgHostSyncing }"></i> 刷新图床
            </button>
          </div>
          <div class="sync-card-body">
            <div class="img-host-details">
              <div class="detail-row">
                <span class="label">图床服务商</span>
                <span class="value">{{ imgHostStatus.provider }}</span>
              </div>
              <div class="detail-row">
                <span class="label">云端文件</span>
                <span class="value font-num">
                  {{ imgHostStatus.remoteImageCount }} 张 ({{ imgHostStatus.remoteStorageSize }})
                </span>
              </div>
              <div class="detail-row highlight" v-if="imgHostStatus.uploadCount > 0 || imgHostStatus.downloadCount > 0">
                <span class="label">待同步数量</span>
                <span class="value sync-badges">
                  <span v-if="imgHostStatus.uploadCount > 0" class="badge upload-badge">
                    <i class="fas fa-arrow-up"></i> {{ imgHostStatus.uploadCount }} 待上传
                  </span>
                  <span v-if="imgHostStatus.downloadCount > 0" class="badge download-badge">
                    <i class="fas fa-arrow-down"></i> {{ imgHostStatus.downloadCount }} 待下载
                  </span>
                </span>
              </div>
              <div class="detail-row" v-else>
                <span class="label">状态</span>
                <span class="value text-ok"><i class="fas fa-circle-check"></i> 云端已同步</span>
              </div>
            </div>
          </div>
          <div class="sync-card-footer split-buttons">
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
  `
};
