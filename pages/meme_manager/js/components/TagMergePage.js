export const TagMergePage = {
  name: 'TagMergePage',
  props: {
    dialog: {
      type: Object,
      required: true
    },
    similarityThreshold: {
      type: [Number, String],
      required: true
    },
    tagMergeGroups: {
      type: Array,
      required: true
    },
    tagMergeTotalTags: {
      type: Number,
      required: true
    },
    tagMergeTagsWithoutVector: {
      type: Number,
      required: true
    },
    totalMergeCount: {
      type: Number,
      required: true
    }
  },
  emits: ['update:similarity-threshold', 'scan', 'set-representative', 'toggle-tag', 'merge'],
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
    <div class="config-container">
      <div class="config-card">
        <div class="config-card-title">
          <i class="fas fa-object-group" style="color: var(--primary-color); margin-right: 6px;"></i>
          标签合并 / 清理
        </div>


        <!-- 控制面板 (阈值 + 扫描) -->
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; padding: 16px; background: var(--btn-default-bg); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
          <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 280px;">
            <label style="font-size: 13px; font-weight: 600; color: var(--text-primary); white-space: nowrap;">
              相似度阈值: <span style="color: var(--primary-color); font-family: monospace; font-size: 14px; font-weight: 700;">{{ similarityThreshold }}%</span>
            </label>
            <input type="range" min="50" max="95" step="1" v-model="localThreshold" style="flex: 1; cursor: pointer;" :disabled="dialog.scanning || dialog.merging" />
            <span style="font-size: 11px; color: var(--text-secondary); white-space: nowrap;">(推荐 78% - 85%)</span>
          </div>

          <div style="display: flex; align-items: center; gap: 16px;">
            <button class="btn-primary" @click="$emit('scan')" :disabled="dialog.scanning || dialog.merging">
              <i class="fas" :class="dialog.scanning ? 'fa-spinner fa-spin' : 'fa-search'"></i>
              {{ dialog.scanning ? '正在扫描...' : '开始扫描' }}
            </button>
          </div>
        </div>

        <!-- 扫描结果 -->
        <div style="min-height: 200px; display: flex; flex-direction: column; gap: 16px;">
          <!-- Loading -->
          <div v-if="dialog.scanning" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); gap: 12px;">
            <i class="fas fa-spinner fa-spin fa-2x" style="color: var(--primary-color);"></i>
            <p style="font-size: 14px;">正在基于标签向量比对相似度...</p>
          </div>

          <!-- Empty -->
          <div v-else-if="tagMergeGroups.length === 0" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); text-align: center; gap: 12px; border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
            <i class="fas fa-tags" style="font-size: 40px; color: var(--border-color); margin-bottom: 8px;"></i>
            <p style="font-size: 14px; font-weight: 600; color: var(--text-primary);">
              {{ dialog.scanned ? '未发现可合并的标签组' : '未进行扫描' }}
            </p>
            <p style="font-size: 13px; max-width: 420px; margin: 0 auto;">
              {{ dialog.scanned ? '未发现可合并的相似标签组，可尝试降低相似度阈值重新扫描。' : '选择相似度阈值，然后点击“开始扫描”来寻找语义相近的标签。' }}
            </p>
            <p v-if="dialog.scanned && tagMergeTagsWithoutVector > 0" style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">
              注意：共有 {{ tagMergeTagsWithoutVector }} 个标签尚未计算向量，未参与本次扫描。
            </p>
          </div>

          <!-- Groups -->
          <div v-else style="display: flex; flex-direction: column; gap: 16px;">
            <div v-if="tagMergeTagsWithoutVector > 0" style="font-size: 12px; color: var(--text-secondary); background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: var(--radius-sm); padding: 10px 14px; display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-circle-info" style="color: #f59e0b;"></i>
              <span>共扫描 {{ tagMergeTotalTags }} 个标签，其中 {{ tagMergeTagsWithoutVector }} 个尚未计算向量，未参与本次扫描。</span>
            </div>

            <div v-for="(group, gIdx) in tagMergeGroups" :key="group.id" class="tag-merge-group-card" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-element); overflow: hidden; box-shadow: var(--shadow-sm);">
              <div class="tag-merge-group-header" style="padding: 12px 16px; background: var(--btn-default-bg); border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13.5px; font-weight: 700; color: var(--text-primary);">
                  相似组 #{{ gIdx + 1 }}
                </span>
                <span style="font-size: 11px; background: rgba(59, 130, 246, 0.08); color: var(--primary-color); padding: 4px 10px; border-radius: 20px; font-weight: 600; border: 1px solid rgba(59, 130, 246, 0.15);">
                  平均相似度 {{ Math.round(group.avg_similarity * 100) }}%
                </span>
              </div>

              <div class="tag-merge-group-body" style="padding: 16px;">
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                  点击标签设为 <strong style="color: var(--primary-color);">代表标签</strong>（合并目标）；点击右侧 &times; 可排除该标签。
                </p>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                  <div
                    v-for="tag in group.tags"
                    :key="tag.name"
                    class="tag-merge-pill"
                    :class="{ representative: tag.is_representative, disabled: !tag.enabled }"
                  >
                    <span class="tag-merge-pill-label" @click="$emit('set-representative', group, tag.name)">
                      <i v-if="tag.is_representative" class="fas fa-star" style="font-size: 10px; margin-right: 4px;"></i>
                      {{ tag.name }}
                      <span class="tag-merge-pill-count">{{ tag.meme_count }}</span>
                    </span>
                    <button
                      v-if="!tag.is_representative"
                      type="button"
                      class="tag-merge-pill-toggle"
                      :title="tag.enabled ? '不参与合并' : '恢复参与合并'"
                      @click="$emit('toggle-tag', group, tag.name)"
                    >
                      <i class="fas" :class="tag.enabled ? 'fa-xmark' : 'fa-rotate-left'"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom Actions -->
      <div v-if="tagMergeGroups.length > 0" class="form-actions-bar">
        <div style="font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; margin-right: auto;">
          <span>将合并 <strong style="color: var(--primary-color); font-size: 15px; font-weight: 700;">{{ totalMergeCount }}</strong> 个标签</span>
        </div>
        <button class="btn-primary" @click="$emit('merge')" :disabled="dialog.merging || totalMergeCount === 0">
          <i class="fas" :class="dialog.merging ? 'fa-spinner fa-spin' : 'fa-object-group'"></i>
          确认合并 ({{ totalMergeCount }} 个标签)
        </button>
      </div>
    </div>
  `
};
