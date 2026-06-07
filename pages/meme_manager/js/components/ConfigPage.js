const { ref, computed, watch } = window.Vue;

export const ConfigPage = {
  name: 'ConfigPage',
  props: {
    systemPersonas: {
      type: Array,
      required: true
    },
    personaTags: {
      type: Object,
      required: true
    },
    allCategories: {
      type: Array,
      required: true
    },
    configSchema: {
      type: Object,
      required: false,
      default: null
    },
    configValues: {
      type: Object,
      required: false,
      default: null
    },
    loading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['save-config', 'save-persona-settings'],
  setup(props, { emit }) {
    const activeSubTab = ref('persona');
    const selectedPersonaId = ref('');
    const showNewTagInput = ref(false);
    const newTagValue = ref('');

    // Local copy of plugin configuration values for editing
    const localConfig = ref({});

    // Watch for configValues change and copy to localConfig safely
    watch(() => [props.configValues, props.configSchema], ([newVal, newSchema]) => {
      if (newVal) {
        const copy = JSON.parse(JSON.stringify(newVal));
        if (newSchema) {
          for (const [key, field] of Object.entries(newSchema)) {
            if (copy[key] === undefined) {
              copy[key] = field.type === 'object' ? {} : (field.default !== undefined ? field.default : (field.type === 'list' ? [] : ''));
            }
            if (field.type === 'object' && field.items) {
              for (const [subKey, subField] of Object.entries(field.items)) {
                if (copy[key][subKey] === undefined) {
                  copy[key][subKey] = subField.type === 'object' ? {} : (subField.default !== undefined ? subField.default : '');
                }
                if (subField.type === 'object' && subField.items) {
                  for (const [nestedKey, nestedField] of Object.entries(subField.items)) {
                    if (copy[key][subKey][nestedKey] === undefined) {
                      copy[key][subKey][nestedKey] = nestedField.default !== undefined ? nestedField.default : '';
                    }
                  }
                }
              }
            }
          }
        }
        localConfig.value = copy;
      }
    }, { immediate: true, deep: true });

    // Watch systemPersonas to select the first one by default if none is selected
    watch(() => props.systemPersonas, (newVal) => {
      if (newVal && newVal.length > 0 && !selectedPersonaId.value) {
        selectedPersonaId.value = newVal[0].id;
      }
    }, { immediate: true });

    // Active persona computation
    const activePersona = computed(() => {
      return props.systemPersonas.find(p => p.id === selectedPersonaId.value) || null;
    });

    // Computed properties for selected persona's settings
    const activePersonaTags = computed(() => {
      if (!selectedPersonaId.value) return { meme_use_preference: '', meme_preference: '' };
      return props.personaTags[selectedPersonaId.value] || { meme_use_preference: '', meme_preference: '' };
    });

    const activePersonaUseList = computed(() => {
      const pref = activePersonaTags.value.meme_use_preference || activePersonaTags.value.tag || '';
      if (!pref) return [];
      return pref.split(',').map(s => s.trim()).filter(Boolean);
    });

    const activePersonaCollectPref = computed({
      get() {
        return activePersonaTags.value.meme_preference || '';
      },
      set(val) {
        emit('save-persona-settings', {
          persona_id: selectedPersonaId.value,
          meme_use_preference: activePersonaTags.value.meme_use_preference || '',
          meme_preference: val
        });
      }
    });

    // Methods for persona tags
    const togglePersonaTag = (tag) => {
      const list = [...activePersonaUseList.value];
      const idx = list.indexOf(tag);
      if (idx > -1) {
        list.splice(idx, 1);
      } else {
        list.push(tag);
      }
      
      emit('save-persona-settings', {
        persona_id: selectedPersonaId.value,
        meme_use_preference: list.join(', '),
        meme_preference: activePersonaCollectPref.value
      });
    };

    const addCustomPersonaTag = () => {
      const tag = newTagValue.value.trim();
      if (tag) {
        const list = [...activePersonaUseList.value];
        if (!list.includes(tag)) {
          list.push(tag);
          emit('save-persona-settings', {
            persona_id: selectedPersonaId.value,
            meme_use_preference: list.join(', '),
            meme_preference: activePersonaCollectPref.value
          });
        }
        newTagValue.value = '';
        showNewTagInput.value = false;
      }
    };

    // Helper to check if a category is active for the current persona
    const isPersonaTagActive = (tag) => {
      return activePersonaUseList.value.includes(tag);
    };

    // Dynamic config form saving
    const savePluginConfig = () => {
      emit('save-config', localConfig.value);
    };

    const resetPluginConfig = () => {
      if (props.configValues) {
        localConfig.value = JSON.parse(JSON.stringify(props.configValues));
      }
    };

    // Filter categories to exclude 'all'
    const filteredCategories = computed(() => {
      return props.allCategories.filter(c => c !== 'all');
    });

    // Helper to get preference tags list for a persona safely
    const getPersonaTagsList = (personaId) => {
      const tagsObj = props.personaTags[personaId];
      const pref = tagsObj ? (tagsObj.meme_use_preference || tagsObj.tag || '') : '';
      if (!pref) return [];
      return pref.split(',').map(s => s.trim()).filter(Boolean);
    };

    // Helper functions for rendering forms
    const getFieldType = (field) => {
      if (field.type === 'object') return 'object';
      if (field.type === 'bool') return 'switch';
      if (field.type === 'int' || field.type === 'float') {
        return field.slider ? 'slider' : 'number';
      }
      if (field.type === 'text') return 'textarea';
      if (field.type === 'list') return 'list';
      if (field.type === 'string' && field.options) return 'select';
      return 'text';
    };

    return {
      activeSubTab,
      selectedPersonaId,
      showNewTagInput,
      newTagValue,
      localConfig,
      activePersona,
      activePersonaUseList,
      activePersonaCollectPref,
      togglePersonaTag,
      addCustomPersonaTag,
      isPersonaTagActive,
      savePluginConfig,
      resetPluginConfig,
      getFieldType,
      filteredCategories,
      getPersonaTagsList
    };
  },
  template: `
    <div class="config-container">
      <!-- 二级 Tab 导航栏 -->
      <div class="secondary-tabs-container">
        <button class="secondary-tab" :class="{ active: activeSubTab === 'persona' }" @click="activeSubTab = 'persona'">
          <i class="fas fa-user-gear"></i> 人设管理
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'plugin' }" @click="activeSubTab = 'plugin'">
          <i class="fas fa-sliders"></i> 插件配置
        </button>
      </div>

      <!-- Tab 1: 人设管理 -->
      <div v-if="activeSubTab === 'persona'" class="tab-content">
        <div v-if="systemPersonas.length === 0" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <i class="fas fa-user-slash fa-2x" style="margin-bottom: 12px; color: var(--border-color);"></i>
          <p>未在系统检测到任何注册人格，请前往主系统“人格管理”页面添加人格。</p>
        </div>
        
        <div v-else style="display: flex; flex-direction: column; gap: 24px;">
          <!-- Left: Persona Cards Grid -->
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
            <div 
              v-for="p in systemPersonas" 
              :key="p.id" 
              class="persona-card" 
              :style="{ 
                cursor: 'pointer', 
                border: selectedPersonaId === p.id ? '2px solid var(--primary-color)' : '1px solid var(--border-color)',
                background: selectedPersonaId === p.id ? 'var(--bg-hover)' : 'var(--bg-card)'
              }"
              @click="selectedPersonaId = p.id"
            >
              <div class="persona-header" style="border: none; padding-bottom: 0;">
                <div class="persona-avatar">
                  {{ p.name.substring(0, 1) }}
                </div>
                <div class="persona-info">
                  <span class="persona-name">{{ p.name }}</span>
                  <span class="persona-id">ID: {{ p.id }}</span>
                </div>
              </div>
              
              <div style="margin-top: 8px;">
                <span style="font-size: 11px; color: var(--text-secondary);">专属发图偏好标签:</span>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; max-height: 52px; overflow: hidden;">
                  <span 
                    v-for="tag in getPersonaTagsList(p.id)" 
                    :key="tag"
                    style="font-size: 10px; background: rgba(59, 130, 246, 0.06); color: var(--primary-color); border: 1px solid rgba(59, 130, 246, 0.15); padding: 1px 6px; border-radius: 4px;"
                  >
                    {{ tag }}
                  </span>
                  <span v-if="!getPersonaTagsList(p.id).length" style="font-size: 10px; color: var(--text-secondary); font-style: italic;">暂未配置发图偏好</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Active Persona Editing Card -->
          <div v-if="activePersona" class="config-card">
            <div class="persona-header">
              <div class="persona-avatar" style="width: 44px; height: 44px; font-size: 20px;">
                {{ activePersona.name.substring(0, 1) }}
              </div>
              <div class="persona-info">
                <span class="persona-name" style="font-size: 16px;">{{ activePersona.name }}</span>
                <span class="persona-id">人格 ID: {{ activePersona.id }}</span>
              </div>
            </div>

            <!-- System Prompt Preview -->
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <span class="form-label" style="font-size: 12.5px;"><i class="fas fa-terminal"></i> 人格提示词预设</span>
              <div class="persona-prompt-preview">{{ activePersona.prompt || '暂无系统提示词内容' }}</div>
            </div>

            <!-- Tags selection (Checkbox capsules) -->
            <div class="persona-tags-select">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="form-label" style="font-size: 12.5px;">
                  <i class="fas fa-tags"></i> 专属发图偏好 (标签多选)
                </span>
                <div style="position: relative;">
                  <button v-if="!showNewTagInput" class="btn-secondary" style="padding: 2px 8px; font-size: 11px;" @click="showNewTagInput = true">
                    <i class="fas fa-plus"></i> 添加自定义标签
                  </button>
                  <div v-else style="display: flex; gap: 4px; align-items: center;">
                    <input 
                      type="text" 
                      v-model="newTagValue" 
                      placeholder="标签名称..." 
                      style="font-size: 11px; padding: 2px 6px; border: 1px solid var(--border-color); border-radius: 4px; outline: none; background: var(--input-bg); color: var(--text-primary);" 
                      @keyup.enter="addCustomPersonaTag"
                    />
                    <button class="btn-primary" style="padding: 2px 8px; font-size: 11px;" @click="addCustomPersonaTag">确认</button>
                    <button class="btn-secondary" style="padding: 2px 8px; font-size: 11px;" @click="showNewTagInput = false">&times;</button>
                  </div>
                </div>
              </div>
              <p class="form-hint" style="margin-top: -4px;">勾选表情分类标签，被勾选的表情会在该人格发言时，以更高的权重被大模型优先推荐发送。</p>
              
              <div class="tags-capsule-grid" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 12px; background: var(--bg-element); max-height: 160px;">
                <button 
                  v-for="cat in filteredCategories" 
                  :key="cat"
                  class="tag-capsule-btn"
                  :class="{ active: isPersonaTagActive(cat) }"
                  @click="togglePersonaTag(cat)"
                >
                  <i v-if="isPersonaTagActive(cat)" class="fas fa-check" style="margin-right: 2px;"></i>
                  {{ cat }}
                </button>
                <div v-if="filteredCategories.length === 0" style="color: var(--text-secondary); font-size: 12px; width: 100%; text-align: center; font-style: italic;">
                  暂无可用表情标签，请先去表情管理页添加表情并打上标签
                </div>
              </div>
            </div>

            <!-- Collect preference description (textarea) -->
            <div class="form-group">
              <span class="form-label" style="font-size: 12.5px;"><i class="fas fa-eye"></i> 专属收集偏好 (描述)</span>
              <p class="form-hint" style="margin-top: -4px;">配置此人格偷取表情包时的偏好逻辑。支持输入自然语言（例如：“只收集沙雕熊猫头，或者带猫咪的表情，其他表情包不保存”）。</p>
              <textarea 
                v-model="activePersonaCollectPref"
                class="form-control" 
                placeholder="（可选）留空则使用默认配置。输入自然语言描述，系统将自动使用多模态大模型对聊天内容中出现的表情进行分类过滤与匹配。"
                style="min-height: 80px;"
              ></textarea>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 2: 插件配置 -->
      <div v-if="activeSubTab === 'plugin'" class="tab-content">
        <div v-if="loading" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); gap: 12px;">
          <i class="fas fa-spinner fa-spin fa-2x" style="color: var(--primary-color);"></i>
          <p style="font-size: 14px;">正在加载配置数据...</p>
        </div>
        
        <div v-else-if="!configSchema || !configValues" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <i class="fas fa-triangle-exclamation fa-2x" style="margin-bottom: 12px; color: var(--warn-color);"></i>
          <p>无法载入配置 Schema 或配置值，请检查后端服务是否正常运行。</p>
        </div>

        <div v-else style="display: flex; flex-direction: column; gap: 24px;">
          <!-- Loop through top level keys in Schema -->
          <div v-for="(field, key) in configSchema" :key="key" class="config-card">
            <div class="config-card-title">
              {{ field.description || key }}
            </div>
            <p v-if="field.hint" class="form-hint" style="margin-top: -12px;">
              {{ field.hint }}
            </p>

            <!-- Object layout (grouped fields) -->
            <div v-if="getFieldType(field) === 'object' && field.items" class="config-form-grid">
              <div v-for="(subField, subKey) in field.items" :key="subKey" class="form-group" :class="{ 'full-width': subField.type === 'text' || subField.type === 'object' }">
                
                <!-- If nested object (like stardots, cloudflare_r2 config) -->
                <div v-if="getFieldType(subField) === 'object' && subField.items" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; background: var(--bg-element); width: 100%;">
                  <span style="font-size: 13px; font-weight: 700; display: block; margin-bottom: 12px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px;">
                    {{ subField.description || subKey }}
                  </span>
                  <div class="config-form-grid" style="grid-template-columns: 1fr;">
                    <div v-for="(nestedField, nestedKey) in subField.items" :key="nestedKey" class="form-group">
                      <label class="form-label">{{ nestedField.description || nestedKey }}</label>
                      
                      <!-- Render control -->
                      <input 
                        v-if="getFieldType(nestedField) === 'text'"
                        type="text" 
                        v-model="localConfig[key][subKey][nestedKey]" 
                        class="form-control"
                      />
                      <input 
                        v-else-if="getFieldType(nestedField) === 'number'"
                        type="number" 
                        v-model.number="localConfig[key][subKey][nestedKey]" 
                        class="form-control"
                      />
                      
                      <p v-if="nestedField.hint" class="form-hint">{{ nestedField.hint }}</p>
                    </div>
                  </div>
                </div>

                <!-- Regular sub-fields -->
                <template v-else>
                  <label class="form-label" v-if="getFieldType(subField) !== 'switch'">
                    {{ subField.description || subKey }}
                  </label>

                  <!-- Switch/Toggle (Inline label) -->
                  <div v-if="getFieldType(subField) === 'switch'" class="switch-container">
                    <div class="switch-label-group">
                      <span class="form-label" style="font-size: 13px;">{{ subField.description || subKey }}</span>
                      <span v-if="subField.hint" class="form-hint">{{ subField.hint }}</span>
                    </div>
                    <label class="switch">
                      <input type="checkbox" v-model="localConfig[key][subKey]" />
                      <span class="slider-switch"></span>
                    </label>
                  </div>

                  <!-- Slider -->
                  <div v-else-if="getFieldType(subField) === 'slider'" class="slider-container">
                    <input 
                      type="range" 
                      :min="subField.slider.min || 1" 
                      :max="subField.slider.max || 100" 
                      step="1" 
                      v-model.number="localConfig[key][subKey]" 
                      class="slider-input"
                    />
                    <span class="slider-value">{{ localConfig[key][subKey] }}%</span>
                  </div>

                  <!-- Dropdown / Select -->
                  <select v-else-if="getFieldType(subField) === 'select'" v-model="localConfig[key][subKey]" class="form-control">
                    <option v-for="opt in subField.options" :key="opt" :value="opt">{{ opt }}</option>
                  </select>

                  <!-- Number -->
                  <input v-else-if="getFieldType(subField) === 'number'" type="number" v-model.number="localConfig[key][subKey]" class="form-control" />

                  <!-- Textarea -->
                  <textarea v-else-if="getFieldType(subField) === 'textarea'" v-model="localConfig[key][subKey]" class="form-control"></textarea>

                  <!-- Hint -->
                  <p v-if="subField.hint && getFieldType(subField) !== 'switch'" class="form-hint">{{ subField.hint }}</p>
                </template>

              </div>
            </div>

            <!-- Top-level Non-Object controls -->
            <div v-else class="config-form-grid" style="grid-template-columns: 1fr;">
              <div class="form-group" style="width: 100%;">
                <!-- Switch -->
                <div v-if="getFieldType(field) === 'switch'" class="switch-container">
                  <div class="switch-label-group">
                    <span class="form-label" style="font-size: 13px;">{{ field.description || key }}</span>
                    <span v-if="field.hint" class="form-hint">{{ field.hint }}</span>
                  </div>
                  <label class="switch">
                    <input type="checkbox" v-model="localConfig[key]" />
                    <span class="slider-switch"></span>
                  </label>
                </div>

                <!-- Textarea -->
                <textarea v-else-if="getFieldType(field) === 'textarea'" v-model="localConfig[key]" class="form-control" style="min-height: 140px;"></textarea>

                <!-- Select -->
                <select v-else-if="getFieldType(field) === 'select'" v-model="localConfig[key]" class="form-control">
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>

                <!-- List (Blacklist / Array of strings) -->
                <div v-else-if="getFieldType(field) === 'list'" class="list-editor">
                  <div v-for="(item, idx) in localConfig[key]" :key="idx" class="list-editor-item">
                    <input type="text" v-model="localConfig[key][idx]" class="form-control" />
                    <button class="btn-danger-outline" style="padding: 0 12px;" @click="localConfig[key].splice(idx, 1)">&times;</button>
                  </div>
                  <button class="btn-secondary" style="align-self: flex-start; margin-top: 4px;" @click="localConfig[key].push('')">
                    <i class="fas fa-plus"></i> 添加条目
                  </button>
                </div>

                <!-- Regular Inputs -->
                <input v-else type="text" v-model="localConfig[key]" class="form-control" />
              </div>
            </div>

          </div>

          <!-- Save and Reset Action buttons sticky bar -->
          <div class="form-actions-bar">
            <button class="btn-secondary" @click="resetPluginConfig" :disabled="loading">重置</button>
            <button class="btn-primary" @click="savePluginConfig" :disabled="loading">
              <i class="fas fa-circle-check"></i> 保存设置
            </button>
          </div>
        </div>
      </div>
    </div>
  `
};
