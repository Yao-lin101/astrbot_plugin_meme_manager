export const BatchAnalyzeModal = {
  name: 'BatchAnalyzeModal',
  props: {
    dialog: {
      type: Object,
      required: true
    },
    selectedCount: {
      type: Number,
      required: true
    },
    getImageUrl: {
      type: Function,
      required: true
    }
  },
  emits: ['close', 'start', 'cancel'],
  template: `
    <div v-if="dialog.visible" class="emoji-detail-modal" role="dialog" aria-modal="true">
      <div class="emoji-detail-modal-card" style="max-width: 700px; width: 90%; max-height: 90vh; display: flex; flex-direction: column;">
        
        <div class="drawer-header" style="padding: 16px 20px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;">
          <span class="drawer-title" style="font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-brain" style="color: var(--primary-color);"></i>
            批量重新分析表情包 (已选 {{ selectedCount }} 个)
          </span>
          <button class="drawer-close-btn" @click="$emit('close')" :disabled="dialog.step === 'progress' && dialog.status.status === 'running'">&times;</button>
        </div>

        <!-- 阶段 1：配置界面 -->
        <div v-if="dialog.step === 'config'" class="drawer-content" style="padding: 20px; flex: 1; overflow-y: auto;">
          <!-- 基础配置 -->
          <div style="display: flex; flex-direction: column; gap: 20px;">
            <div class="form-group" style="margin-bottom: 0;">
              <label style="font-size: 14px; font-weight: 600; color: var(--text-primary); display: block; margin-bottom: 8px;">选择多模态 AI 供应商</label>
              <select class="form-control" v-model="dialog.selectedProvider" style="width: 100%; height: 38px; padding: 0 10px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary);">
                <option value="">-- 请选择供应商 --</option>
                <option v-for="prov in dialog.providers" :key="prov.id" :value="prov.id">
                  {{ prov.name }} ({{ prov.id }})
                </option>
              </select>
              <p style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">需要选择支持图片理解（多模态）的供应商实例，否则分析可能会失败。</p>
            </div>

            <div class="form-group" style="margin-bottom: 0;">
              <label style="font-size: 14px; font-weight: 600; color: var(--text-primary); display: block; margin-bottom: 8px;">分析内容选择</label>
              <div style="display: flex; flex-direction: column; gap: 12px;">
                <label style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary); font-size: 13px;">
                  <input type="checkbox" v-model="dialog.analyzeTags" style="width: 16px; height: 16px;" />
                  <span>重新分析标签 (完全覆盖现有标签)</span>
                </label>
                <label style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary); font-size: 13px;">
                  <input type="checkbox" v-model="dialog.analyzeDescription" style="width: 16px; height: 16px;" />
                  <span>重新分析描述 (覆盖现有描述)</span>
                </label>
              </div>
            </div>

            <div v-show="dialog.analyzeDescription && !dialog.analyzeTags" class="form-group" style="margin-bottom: 0; padding-left: 12px; border-left: 2px solid var(--primary-color, #3b82f6);">
              <label style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary); font-size: 13px;">
                <input type="checkbox" v-model="dialog.passExistingTagsAsRef" style="width: 16px; height: 16px;" />
                <span>传入现有标签作为分析参考</span>
              </label>
            </div>
          </div>

          <!-- 提示词配置 -->
          <div style="display: flex; flex-direction: column; height: 100%; margin-top: 20px;">
            <div class="form-group" style="display: flex; flex-direction: column; flex: 1; margin-bottom: 0;">
              <label style="font-size: 14px; font-weight: 600; color: var(--text-primary); display: block; margin-bottom: 8px;">自定义模型提示词 (Prompt)</label>
              <textarea class="form-control" v-model="dialog.promptContent" @input="dialog.isPromptManuallyEdited = true" rows="6" style="width: 100%; flex: 1; min-height: 150px; padding: 10px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary); font-family: monospace; font-size: 12px; resize: vertical; box-sizing: border-box;"></textarea>
              <p style="font-size: 12px; color: #d97706; margin-top: 6px;" v-if="dialog.isPromptManuallyEdited">
                ⚠️ 您已手动修改过提示词。切换上面的“分析内容选择”会重新生成提示词并覆盖您的修改。
              </p>
              <p style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;" v-else>
                根据您勾选的分析内容，提示词模板会自动切换。您也可以在此处编辑本次运行 of 临时提示词。
              </p>
            </div>
          </div>
        </div>

        <!-- 阶段 2：执行进度与结果列表 -->
        <div v-else class="drawer-content" style="padding: 20px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 15px; min-height: 300px;">
          <!-- 顶部进度统计 -->
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: var(--text-primary); font-weight: 600;">
            <span>分析进度：{{ dialog.status.current_index }} / {{ dialog.status.total }}</span>
            <span v-if="dialog.status.status === 'running'" style="color: var(--primary-color);">
              <i class="fas fa-spinner fa-spin"></i> 正在分析：{{ dialog.status.current_file }}
            </span>
            <span v-else-if="dialog.status.status === 'completed'" style="color: var(--text-ok);">
              <i class="fas fa-check-circle"></i> 分析完成！
            </span>
            <span v-else style="color: var(--text-secondary);">已暂停/未开始</span>
          </div>

          <!-- 进度条 -->
          <div style="width: 100%; height: 10px; background: var(--bg-secondary); border-radius: 5px; overflow: hidden; position: relative;">
            <div :style="{ width: (dialog.status.total > 0 ? (dialog.status.current_index / dialog.status.total * 100) : 0) + '%' }" 
                 style="height: 100%; background: var(--primary-color); transition: width 0.3s ease-in-out;"></div>
          </div>

          <!-- 缩略图列表展示 -->
          <div style="flex: 1; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-secondary); max-height: 40vh; padding: 10px;">
            <div v-for="res in dialog.status.results" :key="res.filename" 
                 style="display: flex; gap: 12px; padding: 10px; border-bottom: 1px solid var(--border-color); background: #ffffff; border-radius: var(--radius-sm); margin-bottom: 8px;"
                 :style="{ opacity: res.status === 'waiting' ? 0.6 : 1 }">
              
              <!-- 表情缩略图 -->
              <div style="width: 60px; height: 60px; flex-shrink: 0; background-size: contain; background-position: center; background-repeat: no-repeat; background-color: rgba(0,0,0,0.02); border-radius: 4px; border: 1px solid var(--border-color);"
                   :style="{ backgroundImage: 'url(' + getImageUrl(res.filename) + ')' }"></div>
              
              <!-- 分析状态与详情 -->
              <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="font-size: 12px; font-weight: 600; color: var(--text-primary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 250px;">{{ res.filename }}</span>
                  <!-- 状态标签 -->
                  <span v-if="res.status === 'success'" style="font-size: 11px; background: rgba(16, 185, 129, 0.1); color: var(--text-ok); padding: 2px 6px; border-radius: 10px; font-weight: 500;">
                    <i class="fas fa-check"></i> 成功
                  </span>
                  <span v-else-if="res.status === 'running'" style="font-size: 11px; background: rgba(59, 130, 246, 0.1); color: var(--primary-color); padding: 2px 6px; border-radius: 10px; font-weight: 500;">
                    <i class="fas fa-spinner fa-spin"></i> 分析中
                  </span>
                  <span v-else-if="res.status === 'waiting'" style="font-size: 11px; background: var(--bg-secondary); color: var(--text-secondary); padding: 2px 6px; border-radius: 10px; font-weight: 500;">
                    等待中
                  </span>
                  <span v-else style="font-size: 11px; background: rgba(239, 68, 68, 0.1); color: var(--danger-color); padding: 2px 6px; border-radius: 10px; font-weight: 500;">
                    <i class="fas fa-exclamation-circle"></i> 失败
                  </span>
                </div>

                <!-- 结果详情 -->
                <div v-if="res.status === 'success'" style="font-size: 11px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 2px;">
                  <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                    <strong style="color: var(--text-primary);">标签:</strong>
                    <span v-for="tag in res.tags" :key="tag" class="tag-pill" style="font-size: 10px; padding: 1px 4px;">{{ tag }}</span>
                    <span v-if="res.tags.length === 0" style="color: var(--text-secondary); font-style: italic;">无标签</span>
                  </div>
                  <div style="text-overflow: ellipsis; overflow: hidden; white-space: nowrap;" :title="res.description">
                    <strong style="color: var(--text-primary);">描述:</strong> {{ res.description || '(空)' }}
                  </div>
                </div>
                <div v-else-if="res.status === 'error'" style="font-size: 11px; color: var(--danger-color);">
                  <strong>错误:</strong> {{ res.error }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部操作按钮 -->
        <div class="drawer-actions" style="padding: 16px 20px; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end; gap: 8px; background: rgba(0, 0, 0, 0.01); flex-shrink: 0;">
          <template v-if="dialog.step === 'config'">
            <button class="btn-secondary" @click="$emit('close')">取消</button>
            <button class="btn-primary" @click="$emit('start')" :disabled="!dialog.selectedProvider || (!dialog.analyzeTags && !dialog.analyzeDescription)">
              开始重新分析
            </button>
          </template>
          <template v-else>
            <button class="btn-secondary" @click="$emit('close')" :disabled="dialog.status.status === 'running'">
              关闭
            </button>
            <button class="btn-danger" @click="$emit('cancel')" :disabled="dialog.status.status !== 'running'">
              取消分析
            </button>
          </template>
        </div>

      </div>
    </div>
  `
};
