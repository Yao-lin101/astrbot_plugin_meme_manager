export const SyncPage = {
  name: 'SyncPage',
  props: {
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
    <div class="config-container">
      <div style="display: grid; grid-template-columns: 1fr; gap: 24px; width: 100%;">
        <!-- For desktop, double column. For mobile, single column. -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 24px;">
          
          <!-- 本地配置同步卡片 -->
          <div class="config-card">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 8px;">
              <span class="config-card-title" style="border: none; padding-left: 0; display: flex; align-items: center; gap: 8px; margin-bottom: 0;">
                <i class="fas fa-arrows-spin" style="color: var(--primary-color);"></i>
                配置与本地同步
              </span>
              <button class="btn-secondary" style="padding: 4px 10px; font-size: 12px;" @click="$emit('check-status', true)" :disabled="checking">
                <i class="fas fa-sync" :class="{ 'fa-spin': checking }"></i> 检查状态
              </button>
            </div>
            
            <p class="form-hint">
              检查表情包在数据库中的分类配置与服务器本地的实际文件夹目录结构是否一致，并修复配置残留或未注册目录的问题。
            </p>

            <div style="min-height: 120px; display: flex; align-items: center; justify-content: center; background: var(--btn-default-bg); border-radius: var(--radius-md); border: 1px solid var(--border-color); padding: 16px;">
              <div v-if="checking" style="display: flex; align-items: center; gap: 8px; color: var(--text-secondary);">
                <i class="fas fa-circle-notch fa-spin"></i> 正在检查配置状态...
              </div>
              <div v-else style="width: 100%;">
                <div v-if="status.inSync" style="color: var(--ok-color); font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 8px;">
                  <i class="fas fa-circle-check" style="font-size: 16px;"></i> 配置与文件夹结构完全一致！
                </div>
                <div v-else style="display: flex; flex-direction: column; gap: 12px;">
                  <div v-if="status.missingInConfig && status.missingInConfig.length > 0" class="sync-diff-group">
                    <h4 style="font-size: 13px; font-weight: 700; margin-bottom: 6px;">未注册的本地分类 (文件夹存在但数据库无配置):</h4>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                      <span v-for="cat in status.missingInConfig" :key="cat" style="font-size: 11px; background: rgba(59, 130, 246, 0.08); color: var(--primary-color); border: 1px solid rgba(59, 130, 246, 0.15); padding: 2px 8px; border-radius: 4px;">
                        {{ cat }}
                      </span>
                    </div>
                  </div>
                  <div v-if="status.deletedCategories && status.deletedCategories.length > 0" class="sync-diff-group">
                    <h4 style="font-size: 13px; font-weight: 700; margin-bottom: 6px; color: var(--warn-color);">已删除的类别 (数据库配置残留):</h4>
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                      <div v-for="cat in status.deletedCategories" :key="cat" style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); padding: 6px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
                        <span style="font-size: 12px; font-weight: 600;">{{ cat }}</span>
                        <button class="btn-sm btn-danger" style="padding: 2px 8px; font-size: 11px;" @click="$emit('remove-config', cat)">删除残留配置</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <button class="btn-primary" style="width: 100%; margin-top: 10px;" @click="$emit('sync-config')" :disabled="checking || status.inSync">
              <i class="fas fa-arrows-rotate"></i> 一键同步所有配置
            </button>
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
