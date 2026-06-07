export const EmojiDetailModal = {
  name: 'EmojiDetailModal',
  props: {
    activeEmoji: {
      type: String,
      required: true
    },
    metadata: {
      type: Object,
      required: true
    },
    description: {
      type: String,
      required: true
    },
    loading: {
      type: Boolean,
      required: true
    },
    selectedEmotions: {
      type: Array,
      required: true
    },
    selectedPersonas: {
      type: Array,
      required: true
    },
    systemPersonas: {
      type: Array,
      required: true
    },
    drawerTagSearchQuery: {
      type: String,
      required: true
    },
    filteredDrawerTags: {
      type: Array,
      required: true
    },
    hasPreviousEmoji: {
      type: Boolean,
      required: true
    },
    hasNextEmoji: {
      type: Boolean,
      required: true
    },
    getImageUrl: {
      type: Function,
      required: true
    },
    providers: {
      type: Array,
      default: () => []
    },
    selectedProvider: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:description',
    'update:drawer-tag-search-query',
    'update:selected-provider',
    'close',
    'toggle-tag',
    'toggle-persona',
    'backspace',
    'create-tag',
    'navigate',
    'save',
    'analyze'
  ],
  data() {
    return {
      isDrawerInputFocused: false
    };
  },
  computed: {
    localDescription: {
      get() {
        return this.description;
      },
      set(val) {
        this.$emit('update:description', val);
      }
    },
    localSearchQuery: {
      get() {
        return this.drawerTagSearchQuery;
      },
      set(val) {
        this.$emit('update:drawer-tag-search-query', val);
      }
    },
    localSelectedProvider: {
      get() {
        return this.selectedProvider;
      },
      set(val) {
        this.$emit('update:selected-provider', val);
      }
    }
  },
  template: `
    <div v-if="activeEmoji" class="emoji-detail-modal" role="dialog" aria-modal="true" @click.self="$emit('close')">
      <div class="emoji-detail-modal-card" :class="{ loading: loading }">
        <!-- Loading Overlay -->
        <div v-if="loading" class="loading-overlay">
          <i class="fas fa-circle-notch fa-spin fa-2x"></i>
        </div>

        <div class="drawer-header">
          <span class="drawer-title">编辑属性: {{ activeEmoji }}</span>
          <button class="drawer-close-btn" @click="$emit('close')">&times;</button>
        </div>
        <div class="drawer-body-layout">
          <!-- 左侧大图预览 + AI 助手 -->
          <div class="drawer-preview-column" style="display: flex; flex-direction: column; gap: 16px; align-items: stretch; justify-content: flex-start; height: 100%; overflow-y: auto;">
            <div style="flex: 1; display: flex; align-items: center; justify-content: center; min-height: 200px; max-height: 280px; background: var(--bg-app); border-radius: var(--radius-md); padding: 8px;">
              <img :src="getImageUrl(activeEmoji)" :alt="activeEmoji" style="max-height: 100%; max-width: 100%; object-fit: contain;" />
            </div>

            <!-- AI 助手板块 -->
            <div class="ai-assistant-section" style="border-top: 1px solid var(--border-color); padding-top: 12px; display: flex; flex-direction: column; gap: 10px;">
              <div style="font-size: 11px; font-weight: 600; color: var(--text-secondary); letter-spacing: 0.05em; text-transform: uppercase; display: flex; align-items: center; gap: 6px;">
                <i class="fas fa-magic" style="color: var(--primary-color);"></i> AI 助手
              </div>

              <!-- AI 供应商下拉选择 -->
              <div style="display: flex; flex-direction: column; gap: 4px;">
                <label style="font-size: 11px; color: var(--text-secondary); text-transform: none; letter-spacing: normal; font-weight: normal;">选择多模态 AI 供应商</label>
                <select v-model="localSelectedProvider" 
                        :disabled="providers.length === 0"
                        style="width: 100%; padding: 6px 8px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: #ffffff; color: var(--text-primary); font-size: 12px; outline: none;">
                  <option v-if="providers.length === 0" value="">加载中...</option>
                  <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
                </select>
              </div>

              <!-- AI 操作按钮 -->
              <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 4px;">
                <button class="btn-secondary" 
                        @click="$emit('analyze', 'tags')" 
                        style="width: 100%; padding: 7px 12px; font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer;">
                  <i class="fas fa-tags"></i> 分析标签
                </button>
                <button class="btn-secondary" 
                        @click="$emit('analyze', 'desc_by_tags')" 
                        style="width: 100%; padding: 7px 12px; font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer;">
                  <i class="fas fa-comment-dots"></i> 通过标签分析描述
                </button>
                <button class="btn-primary" 
                        @click="$emit('analyze', 'full')" 
                        style="width: 100%; padding: 7px 12px; font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer;">
                  <i class="fas fa-brain"></i> 完整分析
                </button>
              </div>
            </div>
          </div>

          <!-- 右侧编辑区域 -->
          <div class="drawer-edit-column">
            <!-- 标签多选 -->
            <div class="drawer-section">
              <label>分类标签 (点击进行选择/取消选择)</label>
              <div class="search-wrapper" 
                   @click="$refs.drawerTagInput.focus()"
                   :style="{ 
                     marginBottom: '8px', 
                     padding: '4px 8px', 
                     border: '1px solid ' + (isDrawerInputFocused ? 'var(--primary-color)' : 'var(--border-color)'), 
                     borderRadius: 'var(--radius-sm)', 
                     background: '#ffffff', 
                     display: 'flex', 
                     flexWrap: 'wrap', 
                     alignItems: 'center', 
                     gap: '6px', 
                     minHeight: '34px', 
                     cursor: 'text',
                     boxShadow: isDrawerInputFocused ? '0 0 0 2px rgba(59, 130, 246, 0.1)' : 'none',
                     transition: 'border-color 0.2s, box-shadow 0.2s'
                   }">
                <span v-for="cat in selectedEmotions" 
                      :key="cat" 
                      class="active-tag-pill" 
                      style="display: inline-flex; align-items: center; gap: 4px; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.3); color: #2563eb; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                  {{ cat }}
                  <span @click.stop="$emit('toggle-tag', cat)" style="cursor: pointer; font-weight: bold; font-size: 12px; color: #2563eb; line-height: 1; padding: 0 2px; transition: color 0.2s;" onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#2563eb'">&times;</span>
                </span>
                <input type="text" 
                       ref="drawerTagInput"
                       v-model="localSearchQuery" 
                       @focus="isDrawerInputFocused = true"
                       @blur="isDrawerInputFocused = false"
                       @keydown.backspace="$emit('backspace', $event)"
                       @keyup.enter="$emit('create-tag')" 
                       placeholder="搜索或输入后回车新建标签..." 
                       style="flex: 1; min-width: 120px; border: none; outline: none; background: transparent; height: 26px; font-size: 12px; padding: 0; color: var(--text-primary);" />
                <button v-if="drawerTagSearchQuery" 
                        @click.stop="localSearchQuery = ''" 
                        style="background: transparent; border: none; color: var(--text-secondary); font-size: 14px; cursor: pointer; padding: 0 4px; display: flex; align-items: center; margin-left: auto;">&times;</button>
              </div>
              <div class="drawer-tags-picker">
                <span v-for="cat in filteredDrawerTags" 
                      :key="cat" 
                      class="picker-tag-pill" 
                      :class="{ active: selectedEmotions.includes(cat) }" 
                      @click="$emit('toggle-tag', cat)">
                  {{ cat }}
                </span>
              </div>
            </div>

            <!-- 表情包描述 -->
            <div class="drawer-section">
              <label for="drawer-description-input">表情描述</label>
              <textarea id="drawer-description-input" 
                        v-model="localDescription" 
                        class="form-control" 
                        style="width: 100%; height: 60px; padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: #ffffff; color: var(--text-primary); resize: vertical; font-family: inherit; font-size: 13px;" 
                        placeholder="请输入表情包的简短描述..."></textarea>
            </div>

            <!-- 人格可用性多选 -->
            <div class="drawer-section">
              <label>允许的人格限制 (留空或勾选全部表示全局可用)</label>
              <div class="drawer-personas-list">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary); text-transform: none; letter-spacing: normal;">
                  <input type="checkbox" value="*" :checked="selectedPersonas.includes('*')" @change="$emit('toggle-persona', '*')" style="width: 14px; height: 14px;" />
                  <span>全局可用 (*)</span>
                </label>
                <label v-for="p in systemPersonas" :key="p.id" style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-primary); text-transform: none; letter-spacing: normal;">
                  <input type="checkbox" :value="p.id" :checked="selectedPersonas.includes(p.id) && !selectedPersonas.includes('*')" @change="$emit('toggle-persona', p.id)" style="width: 14px; height: 14px;" />
                  <span>{{ p.name }} ({{ p.id }})</span>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="drawer-actions">
          <div class="navigation-group">
            <button class="btn-secondary icon-only-btn" 
                    :disabled="!hasPreviousEmoji" 
                    @click="$emit('navigate', -1)"
                    title="上一张">
              <i class="fas fa-chevron-left"></i>
            </button>
            <button class="btn-secondary icon-only-btn" 
                    :disabled="!hasNextEmoji" 
                    @click="$emit('navigate', 1)"
                    title="下一张">
              <i class="fas fa-chevron-right"></i>
            </button>
            <button class="btn-secondary" 
                    @click="$emit('save', false)">
              保存修改
            </button>
          </div>
          <div class="action-group">
            <button class="btn-secondary" @click="$emit('close')">取消</button>
            <button class="btn-primary" @click="$emit('save', true)">保存并关闭</button>
          </div>
        </div>
      </div>
    </div>
  `
};
