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
    },
    getEmojiTags: {
      type: Function,
      required: true
    },
    allCategories: {
      type: Array,
      required: true
    }
  },
  emits: ['close', 'submit', 'toggle-emoji'],
  data() {
    return {
      selectedFilterTags: [],
      tagSearchQuery: ''
    };
  },
  computed: {
    relevantTags() {
      const tagsSet = new Set();
      this.importableEmojisList.forEach(emoji => {
        const tags = this.getEmojiTags(emoji);
        tags.forEach(t => {
          if (t !== this.activeCategory) {
            tagsSet.add(t);
          }
        });
      });
      return Array.from(tagsSet).sort();
    },
    filteredRelevantTags() {
      const query = this.tagSearchQuery.trim().toLowerCase();
      if (!query) return this.relevantTags;
      return this.relevantTags.filter(t => t.toLowerCase().includes(query));
    },
    filteredImportableEmojisList() {
      if (this.selectedFilterTags.length === 0) {
        return this.importableEmojisList;
      }
      return this.importableEmojisList.filter(emoji => {
        const tags = this.getEmojiTags(emoji);
        return this.selectedFilterTags.every(tag => tags.includes(tag));
      });
    }
  },
  watch: {
    'dialog.visible'(newVal) {
      if (newVal) {
        this.selectedFilterTags = [];
        this.tagSearchQuery = '';
      }
    }
  },
  methods: {
    toggleFilterTag(tag) {
      const idx = this.selectedFilterTags.indexOf(tag);
      if (idx > -1) {
        this.selectedFilterTags.splice(idx, 1);
      } else {
        this.selectedFilterTags.push(tag);
      }
    },
    clearFilter() {
      this.selectedFilterTags = [];
      this.tagSearchQuery = '';
    }
  },
  template: `
    <div v-if="dialog.visible" class="emoji-detail-modal" role="dialog" aria-modal="true" @click.self="$emit('close')">
      <div class="emoji-detail-modal-card" style="max-width: 800px; width: 90%;">
        <div class="drawer-header">
          <span class="drawer-title">导入已存表情到标签「{{ activeCategory }}」</span>
          <button class="drawer-close-btn" @click="$emit('close')">&times;</button>
        </div>
        <div class="drawer-content" style="max-height: 50vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px;">
          <p style="margin-bottom: 5px; color: var(--text-secondary);">请选择要追加到当前分类的表情包（已选中 {{ dialog.selectedEmojis.size }} 个）：</p>
          
          <!-- 标签筛选及多选框 -->
          <div class="filter-section" style="margin-bottom: 10px;">
            <!-- 已选标签 Pills -->
            <div v-if="selectedFilterTags.length > 0" class="filter-active-tags" style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">
              <span v-for="tag in selectedFilterTags" :key="tag" class="active-tag-pill"
                style="display: inline-flex; align-items: center; gap: 4px; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.3); color: #2563eb; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                {{ tag }}
                <span @click.stop="toggleFilterTag(tag)"
                  style="cursor: pointer; font-weight: bold; font-size: 12px; color: #2563eb; line-height: 1; padding: 0 2px; transition: color 0.2s;"
                  onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#2563eb'">&times;</span>
              </span>
            </div>

            <!-- 搜索框与重置按钮 -->
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
              <div class="tags-search-wrapper" style="flex: 1; margin: 0; position: relative; display: flex; align-items: center;">
                <i class="fas fa-search search-icon" style="position: absolute; left: 10px; color: var(--text-secondary); font-size: 12px;"></i>
                <input type="text" v-model="tagSearchQuery" placeholder="搜索过滤标签..." class="form-control" 
                  style="width: 100%; height: 32px; font-size: 12.5px; padding: 4px 8px 4px 28px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: var(--bg-element); color: var(--text-primary);" />
                <button v-if="tagSearchQuery" @click="tagSearchQuery = ''" class="clear-btn" 
                  style="position: absolute; right: 8px; background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; height: 100%; width: 20px;">&times;</button>
              </div>
              <button v-if="selectedFilterTags.length > 0" class="btn-secondary" @click="clearFilter" 
                style="height: 32px; padding: 0 10px; font-size: 12px; display: flex; align-items: center; gap: 4px; white-space: nowrap; border-radius: var(--radius-sm);">
                <i class="fas fa-rotate-left"></i> 重置
              </button>
            </div>

            <!-- 可选标签列表 -->
            <div class="filter-tags-list" 
              style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 80px; overflow-y: auto; padding: 6px; border: 1px dashed var(--border-color); border-radius: var(--radius-sm); background: var(--bg-element-light, rgba(0,0,0,0.015));">
              <button v-for="tag in filteredRelevantTags" 
                :key="tag" 
                type="button"
                class="tag-chip-btn"
                @click="toggleFilterTag(tag)"
                :style="selectedFilterTags.includes(tag) ? {
                  background: 'var(--btn-primary-bg, #2563eb)',
                  color: '#ffffff',
                  borderColor: 'var(--btn-primary-bg, #2563eb)',
                  padding: '3px 8px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  display: 'inline-flex',
                  align-items: 'center',
                  border: '1px solid var(--btn-primary-bg, #2563eb)'
                } : {
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  borderColor: 'var(--border-color)',
                  padding: '3px 8px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  display: 'inline-flex',
                  align-items: 'center',
                  border: '1px solid var(--border-color)'
                }">
                {{ tag }}
              </button>
              <div v-if="filteredRelevantTags.length === 0" style="font-size: 11px; color: var(--text-secondary); padding: 4px; width: 100%; text-align: center;">
                没有找到匹配的标签
              </div>
            </div>
          </div>

          <div v-if="filteredImportableEmojisList.length === 0" style="padding: 40px; text-align: center; color: var(--text-secondary);">
            没有可导入的表情包。
          </div>
          <div v-else class="emoji-grid" style="grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px;">
            <div v-for="emoji in filteredImportableEmojisList" 
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
