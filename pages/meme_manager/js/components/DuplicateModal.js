export const DuplicateModal = {
  name: 'DuplicateModal',
  props: {
    dialog: {
      type: Object,
      required: true
    },
    similarityThreshold: {
      type: [Number, String],
      required: true
    },
    duplicateGroups: {
      type: Array,
      required: true
    },
    totalDeletesCount: {
      type: Number,
      required: true
    },
    getImageUrl: {
      type: Function,
      required: true
    },
    formatBytes: {
      type: Function,
      required: true
    }
  },
  emits: ['update:similarity-threshold', 'scan', 'toggle-action', 'resolve', 'close'],
  computed: {
    localThreshold: {
      get() {
        return this.similarityThreshold;
      },
      set(val) {
        this.$emit('update:similarity-threshold', Number(val));
      }
    }
  },
  template: `
    <div v-if="dialog.visible" class="emoji-detail-modal" role="dialog" aria-modal="true" @click.self="$emit('close')">
      <div class="emoji-detail-modal-card" style="max-width: 900px; width: 95%; max-height: 90vh; display: flex; flex-direction: column;">
        
        <div class="drawer-header" style="padding: 16px 20px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;">
          <span class="drawer-title" style="font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-clone" style="color: var(--primary-color);"></i>
            检查重复/相似表情包
          </span>
          <button class="drawer-close-btn" @click="$emit('close')">&times;</button>
        </div>

        <!-- 控制面板 (控制阈值、开始扫描) -->
        <div class="dedup-control-panel" style="padding: 16px 20px; background: rgba(0, 0, 0, 0.01); border-bottom: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; flex-shrink: 0;">
          <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 250px;">
            <label style="font-size: 13px; font-weight: 600; color: var(--text-secondary); white-space: nowrap;">
              相似度阈值: <span style="color: var(--primary-color); font-family: monospace; font-size: 14px;">{{ similarityThreshold }}%</span>
            </label>
            <input type="range" min="50" max="100" step="1" v-model="localThreshold" style="flex: 1; cursor: pointer;" :disabled="dialog.scanning || dialog.resolving" />
            <span style="font-size: 11px; color: var(--text-secondary); white-space: nowrap;">(推荐 85% - 90%)</span>
          </div>
          
          <div style="display: flex; align-items: center; gap: 16px;">
            <button class="btn-primary" @click="$emit('scan')" :disabled="dialog.scanning || dialog.resolving">
              <i class="fas" :class="dialog.scanning ? 'fa-spinner fa-spin' : 'fa-search'"></i>
              {{ dialog.scanning ? '正在扫描...' : '开始扫描' }}
            </button>
          </div>
        </div>

        <!-- 扫描结果列表 -->
        <div style="flex: 1; overflow-y: auto; padding: 20px; min-height: 200px;">
          <!-- Loading state -->
          <div v-if="dialog.scanning" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); gap: 12px;">
            <i class="fas fa-spinner fa-spin fa-2x" style="color: var(--primary-color);"></i>
            <p style="font-size: 14px;">正在全库比对表情特征，这可能需要数秒钟...</p>
          </div>

          <!-- Empty state (Initial or No duplicates) -->
          <div v-else-if="duplicateGroups.length === 0" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); text-align: center; gap: 12px;">
            <i class="far fa-copy" style="font-size: 40px; color: var(--border-color);"></i>
            <p style="font-size: 14px; max-width: 320px;">
              {{ dialog.scanning ? '' : '选择合适的相似度阈值，然后点击“开始扫描”来寻找相似表情包' }}
            </p>
          </div>

          <!-- Duplicate Groups List -->
          <div v-else style="display: flex; flex-direction: column; gap: 24px;">
            <div v-for="(group, gIdx) in duplicateGroups" :key="group.id" class="dedup-group-card" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); background: #ffffff; overflow: hidden; box-shadow: var(--shadow-sm);">
              
              <div class="dedup-group-header" style="padding: 10px 16px; background: rgba(0, 0, 0, 0.02); border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; font-weight: 600; color: var(--text-secondary);">
                  相似组 #{{ gIdx + 1 }}
                </span>
                <span style="font-size: 11px; background: rgba(59, 130, 246, 0.08); color: var(--primary-color); padding: 2px 8px; border-radius: 10px; font-weight: 500;">
                  共 {{ group.memes.length }} 张相似图片
                </span>
              </div>

              <div class="dedup-group-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; padding: 16px;">
                <div v-for="meme in group.memes" :key="meme.filename" class="dedup-meme-card" :class="meme.action" style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; display: flex; gap: 12px; transition: var(--transition); background: #ffffff; position: relative;">
                  
                  <!-- Thumbnail with overlay for action -->
                  <div style="width: 80px; height: 80px; flex-shrink: 0; background-size: contain; background-position: center; background-repeat: no-repeat; background-color: rgba(0,0,0,0.02); border-radius: 4px; border: 1px solid var(--border-color);" :style="{ backgroundImage: 'url(' + getImageUrl(meme.filename) + ')' }"></div>
                  
                  <!-- Info & Action -->
                  <div style="flex: 1; display: flex; flex-direction: column; justify-content: space-between; min-width: 0;">
                    <div style="margin-bottom: 4px;">
                      <div style="font-size: 12px; font-weight: 600; color: var(--text-primary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;" :title="meme.filename">
                        {{ meme.filename }}
                      </div>
                      <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                        <span style="font-family: monospace;">{{ meme.width }}x{{ meme.height }}</span>
                        <span>&bull;</span>
                        <span>{{ formatBytes(meme.size_bytes) }}</span>
                        <span v-if="meme.similarity < 1.0" style="color: var(--primary-color); font-weight: 600;">
                          &bull; 相似度 {{ Math.round(meme.similarity * 100) }}%
                        </span>
                      </div>
                    </div>

                    <div style="display: flex; gap: 6px; margin-top: 8px;">
                      <button type="button" class="btn-sm" :class="meme.action === 'keep' ? 'btn-primary' : 'btn-secondary'" style="padding: 3px 10px; font-size: 11px;" @click="$emit('toggle-action', group, meme, 'keep')">
                        <i class="fas fa-check"></i> 保留
                      </button>
                      <button type="button" class="btn-sm" :class="meme.action === 'delete' ? 'btn-danger' : 'btn-secondary'" style="padding: 3px 10px; font-size: 11px;" @click="$emit('toggle-action', group, meme, 'delete')">
                        <i class="fas fa-trash-can"></i> 删除
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Bottom Actions -->
        <div class="drawer-actions" style="padding: 16px 20px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; background: rgba(0, 0, 0, 0.01); flex-shrink: 0;">
          <div style="font-size: 13px; color: var(--text-secondary);">
            <span v-if="duplicateGroups.length > 0">
              已选择删除 <strong style="color: var(--danger-color); font-size: 14px;">{{ totalDeletesCount }}</strong> 张重复表情
            </span>
          </div>
          
          <div style="display: flex; gap: 8px;">
            <button class="btn-secondary" @click="$emit('close')" :disabled="dialog.resolving">取消</button>
            <button class="btn-primary" @click="$emit('resolve')" :disabled="dialog.resolving || totalDeletesCount === 0 || duplicateGroups.length === 0">
              <i class="fas" :class="dialog.resolving ? 'fa-spinner fa-spin' : 'fa-trash-can'"></i>
              确认清理 (删除 {{ totalDeletesCount }} 张)
            </button>
          </div>
        </div>

      </div>
    </div>
  `
};
