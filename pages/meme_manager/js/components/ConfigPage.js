const { ref, computed, watch, onMounted } = window.Vue;

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
    const newPreferenceTagInput = ref('');
    const showUsePreferenceDropdown = ref(false);

    const blacklistSearchQuery = ref('');
    const showBlacklistDropdown = ref(false);

    const localPersonaUseList = ref([]);
    const localPersonaCollectPref = ref('');

    const providers = ref([]);
    const embeddingProviders = ref([]);

    const tabKeys = {
      basic: ['enable_llm_tool', 'persona_blacklist', 'meme_prompt'],
      interaction: ['interaction_config'],
      auto_steal: ['auto_steal_config', 'multimodal_config'],
      emotion: ['emotion_llm_config'],
      embedding: ['embedding_config', 'similarity_dedup_config'],
      compression: ['compression_config'],
      image_host: ['image_host', 'image_host_config']
    };

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

    // Watch selectedPersonaId and props.personaTags to sync local values
    watch(() => [selectedPersonaId.value, props.personaTags], () => {
      if (selectedPersonaId.value) {
        const tagsObj = props.personaTags[selectedPersonaId.value] || { meme_use_preference: '', meme_preference: '' };
        const pref = tagsObj.meme_use_preference || tagsObj.tag || '';
        localPersonaUseList.value = pref ? pref.split(',').map(s => s.trim()).filter(Boolean) : [];
        localPersonaCollectPref.value = tagsObj.meme_preference || '';
      } else {
        localPersonaUseList.value = [];
        localPersonaCollectPref.value = '';
      }
    }, { immediate: true, deep: true });

    // Active persona computation
    const activePersona = computed(() => {
      return props.systemPersonas.find(p => p.id === selectedPersonaId.value) || null;
    });

    // Methods for persona tags
    const togglePersonaTag = (tag) => {
      const list = [...localPersonaUseList.value];
      const idx = list.indexOf(tag);
      if (idx > -1) {
        list.splice(idx, 1);
      } else {
        list.push(tag);
      }
      localPersonaUseList.value = list;
    };

    const addNewPreferenceTag = () => {
      const tag = newPreferenceTagInput.value.trim();
      if (tag) {
        const list = [...localPersonaUseList.value];
        if (!list.includes(tag)) {
          list.push(tag);
          localPersonaUseList.value = list;
        }
        newPreferenceTagInput.value = '';
      }
    };

    const handleInputBlur = () => {
      setTimeout(() => {
        showUsePreferenceDropdown.value = false;
      }, 200);
    };

    const filteredPreferenceCategories = computed(() => {
      const query = newPreferenceTagInput.value.trim().toLowerCase();
      const categories = props.allCategories.filter(c => c !== 'all');
      if (!query) return categories;
      return categories.filter(cat => cat.toLowerCase().includes(query));
    });

    // Manual Save / Reset for persona configuration
    const savePersonaConfig = () => {
      emit('save-persona-settings', {
        persona_id: selectedPersonaId.value,
        meme_use_preference: localPersonaUseList.value.join(', '),
        meme_preference: localPersonaCollectPref.value
      });
    };

    const resetPersonaConfig = () => {
      if (selectedPersonaId.value) {
        const tagsObj = props.personaTags[selectedPersonaId.value] || { meme_use_preference: '', meme_preference: '' };
        const pref = tagsObj.meme_use_preference || tagsObj.tag || '';
        localPersonaUseList.value = pref ? pref.split(',').map(s => s.trim()).filter(Boolean) : [];
        localPersonaCollectPref.value = tagsObj.meme_preference || '';
      }
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
    const getFieldType = (field, key) => {
      if (field.type === 'object') return 'object';
      if (field.type === 'bool') return 'switch';
      if (field.type === 'int' || field.type === 'float') {
        return field.slider ? 'slider' : 'number';
      }
      if (field.type === 'text') return 'textarea';
      if (field.type === 'list') {
        if (key === 'persona_blacklist') return 'persona_blacklist_select';
        return 'list';
      }
      if (field.type === 'string' && field.options) return 'select';
      if (field.type === 'string' && field._special === 'select_provider') return 'provider_select';
      if (field.type === 'string' && field._special === 'select_embedding_provider') return 'embedding_provider_select';
      return 'text';
    };

    const fetchProviders = async () => {
      try {
        const res = await fetch("providers");
        if (res.ok) {
          providers.value = await res.json();
        }
      } catch (e) {
        console.error("加载提供商列表失败:", e);
      }
    };

    const fetchEmbeddingProviders = async () => {
      try {
        const res = await fetch("embedding_providers");
        if (res.ok) {
          embeddingProviders.value = await res.json();
        }
      } catch (e) {
        console.error("加载 Embedding 提供商列表失败:", e);
      }
    };

    onMounted(() => {
      fetchProviders();
      fetchEmbeddingProviders();
    });

    const generatingThumbnails = ref(false);
    const generationResult = ref(null);

    const triggerThumbnailGeneration = async () => {
      generatingThumbnails.value = true;
      generationResult.value = null;
      try {
        const res = await fetch("/api/emoji/generate_thumbnails", {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        });
        if (!res.ok) throw new Error("生成请求失败");
        generationResult.value = await res.json();
      } catch (e) {
        console.error(e);
        generationResult.value = {
          status: "error",
          failed: 1,
          errors: [{ filename: "System Error", error: e.message }]
        };
      } finally {
        generatingThumbnails.value = false;
      }
    };

    // Persona Blacklist Multiselect Helpers
    const getPersonaName = (pId) => {
      const p = props.systemPersonas.find(p => p.id === pId);
      return p ? `${p.name} (${pId})` : pId;
    };

    const filteredBlacklistPersonas = computed(() => {
      const query = blacklistSearchQuery.value.trim().toLowerCase();
      if (!query) return props.systemPersonas;
      return props.systemPersonas.filter(p => 
        p.name.toLowerCase().includes(query) || p.id.toLowerCase().includes(query)
      );
    });

    const handleBlacklistBlur = () => {
      setTimeout(() => {
        showBlacklistDropdown.value = false;
      }, 200);
    };

    const toggleBlacklistPersona = (pId) => {
      if (!localConfig.value.persona_blacklist) {
        localConfig.value.persona_blacklist = [];
      }
      const list = [...localConfig.value.persona_blacklist];
      const idx = list.indexOf(pId);
      if (idx > -1) {
        list.splice(idx, 1);
      } else {
        list.push(pId);
      }
      localConfig.value.persona_blacklist = list;
    };

    return {
      activeSubTab,
      selectedPersonaId,
      localConfig,
      activePersona,
      localPersonaUseList,
      localPersonaCollectPref,
      togglePersonaTag,
      savePersonaConfig,
      resetPersonaConfig,
      savePluginConfig,
      resetPluginConfig,
      getFieldType,
      filteredCategories,
      getPersonaTagsList,
      newPreferenceTagInput,
      showUsePreferenceDropdown,
      addNewPreferenceTag,
      handleInputBlur,
      filteredPreferenceCategories,
      tabKeys,
      providers,
      embeddingProviders,
      blacklistSearchQuery,
      showBlacklistDropdown,
      getPersonaName,
      filteredBlacklistPersonas,
      handleBlacklistBlur,
      toggleBlacklistPersona,
      generatingThumbnails,
      generationResult,
      triggerThumbnailGeneration
    };
  },
  template: `
    <div class="config-container">
      <!-- 二级 Tab 导航栏 -->
      <div class="secondary-tabs-container" style="flex-wrap: wrap; gap: 8px 16px;">
        <button class="secondary-tab" :class="{ active: activeSubTab === 'persona' }" @click="activeSubTab = 'persona'">
          <i class="fas fa-user-gear"></i> 人设管理
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'basic' }" @click="activeSubTab = 'basic'">
          <i class="fas fa-sliders"></i> 基础设置
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'interaction' }" @click="activeSubTab = 'interaction'">
          <i class="fas fa-message"></i> 交互设置
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'auto_steal' }" @click="activeSubTab = 'auto_steal'">
          <i class="fas fa-download"></i> 偷图与分类
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'emotion' }" @click="activeSubTab = 'emotion'">
          <i class="fas fa-heart"></i> 情感分析
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'embedding' }" @click="activeSubTab = 'embedding'">
          <i class="fas fa-magnifying-glass"></i> 检索与去重
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'compression' }" @click="activeSubTab = 'compression'">
          <i class="fas fa-compress-arrows-alt"></i> 压缩设置
        </button>
        <button class="secondary-tab" :class="{ active: activeSubTab === 'image_host' }" @click="activeSubTab = 'image_host'">
          <i class="fas fa-cloud-arrow-up"></i> 图床设置
        </button>
      </div>

      <!-- Tab 1: 人设管理 -->
      <div v-if="activeSubTab === 'persona'" class="tab-content">
        <div v-if="systemPersonas.length === 0" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <i class="fas fa-user-slash fa-2x" style="margin-bottom: 12px; color: var(--border-color);"></i>
          <p>未在系统检测到任何注册人格，请前往主系统“人格管理”页面添加人格。</p>
        </div>
        
        <div v-else style="display: flex; flex-direction: column; gap: 20px;">
          <!-- 核心选择器及配置卡片 -->
          <div class="config-card" :style="{ zIndex: showUsePreferenceDropdown ? 100 : 'auto', position: showUsePreferenceDropdown ? 'relative' : 'static' }">
            <!-- 选择人格 -->
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label" for="persona-select">选择人格</label>
              <select id="persona-select" v-model="selectedPersonaId" class="form-control" style="max-width: 300px;">
                <option v-for="p in systemPersonas" :key="p.id" :value="p.id">{{ p.name }} (ID: {{ p.id }})</option>
              </select>
            </div>

            <!-- 具体配置 (若有选中的人格) -->
            <div v-if="activePersona" style="display: flex; flex-direction: column; gap: 20px; border-top: 1px solid var(--border-color); padding-top: 20px; margin-top: 20px;">
              <!-- Tags selection (Search & Select Dropdown) -->
              <div class="persona-tags-select" style="position: relative;">
                <span class="form-label" style="font-size: 12.5px;">
                  <i class="fas fa-tags"></i> 专属发图偏好 (标签多选)
                </span>
                <p class="form-hint" style="margin-top: -4px;">配置该人格发言时，以更高权重优先推荐发送的表情分类标签。</p>
                
                <div class="multiselect-tag-container" style="display: flex; align-items: center; gap: 8px; background: var(--bg-element); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: var(--radius-md); min-height: 42px; width: 100%; flex-wrap: wrap; box-sizing: border-box; position: relative;">
                  <!-- Active pills -->
                  <span v-for="tag in localPersonaUseList" :key="tag" class="active-tag-pill" style="display: inline-flex; align-items: center; gap: 4px; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.3); color: var(--primary-color); padding: 2px 8px; border-radius: 4px; font-size: 12.5px; font-weight: 500; user-select: none;">
                    {{ tag }}
                    <span @click.stop="togglePersonaTag(tag)" style="cursor: pointer; font-weight: bold; font-size: 13px; color: var(--primary-color); line-height: 1; padding-left: 2px;" onmouseover="this.style.color='var(--danger-color)'" onmouseout="this.style.color='var(--primary-color)'">&times;</span>
                  </span>
                  
                  <!-- Dropdown Input -->
                  <div style="position: relative; display: inline-flex; align-items: center; flex: 1; min-width: 160px;">
                    <input 
                      type="text" 
                      v-model="newPreferenceTagInput" 
                      @focus="showUsePreferenceDropdown = true"
                      @blur="handleInputBlur"
                      @keyup.enter="addNewPreferenceTag" 
                      placeholder="输入以检索或回车添加新标签..." 
                      style="width: 100%; border: none; background: transparent; color: var(--text-primary); outline: none; font-size: 13px;"
                    />
                    
                    <!-- Dropdown Menu -->
                    <div v-show="showUsePreferenceDropdown" class="dropdown-menu" style="position: absolute; top: 100%; left: 0; margin-top: 6px; z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); box-shadow: var(--shadow-md); max-height: 200px; overflow-y: auto; min-width: 220px; padding: 4px 0; display: flex; flex-direction: column; gap: 2px;" @mousedown.prevent>
                      <div 
                        v-for="cat in filteredPreferenceCategories" 
                        :key="cat"
                        style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; cursor: pointer; color: var(--text-primary); font-size: 13.5px; margin: 0; user-select: none; transition: background 0.2s;" 
                        :style="{ background: localPersonaUseList.includes(cat) ? 'rgba(59, 130, 246, 0.08)' : 'transparent', color: localPersonaUseList.includes(cat) ? 'var(--primary-color)' : 'var(--text-primary)' }"
                        @mouseover="$event.currentTarget.style.background = 'var(--bg-hover)'"
                        @mouseleave="$event.currentTarget.style.background = localPersonaUseList.includes(cat) ? 'rgba(59, 130, 246, 0.08)' : 'transparent'"
                        @click="togglePersonaTag(cat)"
                      >
                        <span style="flex: 1;">{{ cat }}</span>
                        <i v-if="localPersonaUseList.includes(cat)" class="fas fa-check" style="color: var(--primary-color); font-size: 12px;"></i>
                      </div>
                      <div v-if="filteredPreferenceCategories.length === 0" style="padding: 8px 12px; color: var(--text-secondary); font-size: 12.5px; text-align: center;">暂无匹配标签，按回车直接新增</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Collect preference description (textarea) -->
              <div class="form-group" style="margin-bottom: 0;">
                <span class="form-label" style="font-size: 12.5px;"><i class="fas fa-eye"></i> 专属收集偏好 (描述)</span>
                <p class="form-hint" style="margin-top: -4px;">配置此人格偷取表情包时的偏好逻辑。支持输入自然语言（例如：“只收集沙雕熊猫头，或者带猫咪的表情，其他表情包不保存”）。</p>
                <textarea 
                  v-model="localPersonaCollectPref"
                  class="form-control" 
                  placeholder="（可选）留空则使用默认配置。输入自然语言描述，系统将自动使用多模态大模型对聊天内容中出现的表情进行分类过滤与匹配。"
                  style="min-height: 80px;"
                ></textarea>
              </div>

              <!-- Manual save/reset actions bar for persona settings -->
              <div class="form-actions-bar" style="margin-top: 10px; position: static; box-shadow: none; border-radius: var(--radius-md); padding: 12px 0; background: transparent;">
                <button class="btn-secondary" @click="resetPersonaConfig" :disabled="loading">重置</button>
                <button class="btn-primary" @click="savePersonaConfig" :disabled="loading || !selectedPersonaId">
                  <i class="fas fa-circle-check"></i> 保存人设设置
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: 其它配置页签 -->
      <div v-if="activeSubTab !== 'persona'" class="tab-content">
        <div v-if="loading" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 0; color: var(--text-secondary); gap: 12px;">
          <i class="fas fa-spinner fa-spin fa-2x" style="color: var(--primary-color);"></i>
          <p style="font-size: 14px;">正在加载配置数据...</p>
        </div>
        
        <div v-else-if="!configSchema || !configValues" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <i class="fas fa-triangle-exclamation fa-2x" style="margin-bottom: 12px; color: var(--warn-color);"></i>
          <p>无法载入配置 Schema 或配置值，请检查后端服务是否正常运行。</p>
        </div>

        <div v-else style="display: flex; flex-direction: column; gap: 24px;">
          <!-- Loop through keys mapped to current activeSubTab -->
          <template v-for="key in tabKeys[activeSubTab]" :key="key">
            <div v-if="configSchema[key]" class="config-card" :style="{ zIndex: (key === 'persona_blacklist' && showBlacklistDropdown) ? 100 : 'auto', position: (key === 'persona_blacklist' && showBlacklistDropdown) ? 'relative' : 'static' }">
              <div class="config-card-title">
                {{ configSchema[key].description || key }}
              </div>
              <p v-if="configSchema[key].hint" class="form-hint" style="margin-top: -12px;">
                {{ configSchema[key].hint }}
              </p>

              <!-- Object layout (grouped fields) -->
              <div v-if="getFieldType(configSchema[key], key) === 'object' && configSchema[key].items" class="config-form-grid">
                <div v-for="(subField, subKey) in configSchema[key].items" :key="subKey" class="form-group" :class="{ 'full-width': subField.type === 'text' || subField.type === 'object' }">
                  
                  <!-- If nested object (like stardots, cloudflare_r2 config) -->
                  <div v-if="getFieldType(subField, subKey) === 'object' && subField.items" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; background: var(--bg-element); width: 100%;">
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
                    <label class="form-label" v-if="getFieldType(subField, subKey) !== 'switch'">
                      {{ subField.description || subKey }}
                    </label>

                    <!-- Switch/Toggle (Inline label) -->
                    <div v-if="getFieldType(subField, subKey) === 'switch'" class="switch-container">
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
                    <div v-else-if="getFieldType(subField, subKey) === 'slider'" class="slider-container">
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
                    <select v-else-if="getFieldType(subField, subKey) === 'select'" v-model="localConfig[key][subKey]" class="form-control">
                      <option v-for="opt in subField.options" :key="opt" :value="opt">{{ opt }}</option>
                    </select>

                    <!-- Provider ID Dropdown -->
                    <select v-else-if="getFieldType(subField, subKey) === 'provider_select'" v-model="localConfig[key][subKey]" class="form-control">
                      <option value="">-- 请选择供应商 (留空默认) --</option>
                      <option v-for="prov in providers" :key="prov.id" :value="prov.id">
                        {{ prov.name }} ({{ prov.id }})
                      </option>
                    </select>

                    <!-- Embedding Provider ID Dropdown or Input fallback -->
                    <template v-else-if="getFieldType(subField, subKey) === 'embedding_provider_select'">
                      <select v-if="embeddingProviders.length > 0" v-model="localConfig[key][subKey]" class="form-control">
                        <option value="">-- 请选择 Embedding 供应商 (留空默认) --</option>
                        <option v-for="prov in embeddingProviders" :key="prov.id" :value="prov.id">
                          {{ prov.name }} ({{ prov.id }})
                        </option>
                      </select>
                      <input v-else type="text" v-model="localConfig[key][subKey]" class="form-control" placeholder="无法查找到 Embedding 供应商，请输入 Provider ID" />
                    </template>

                    <!-- Number -->
                    <input v-else-if="getFieldType(subField, subKey) === 'number'" type="number" v-model.number="localConfig[key][subKey]" class="form-control" />

                    <!-- Textarea -->
                    <textarea v-else-if="getFieldType(subField, subKey) === 'textarea'" v-model="localConfig[key][subKey]" class="form-control"></textarea>

                    <!-- Hint -->
                    <p v-if="subField.hint && getFieldType(subField, subKey) !== 'switch'" class="form-hint">{{ subField.hint }}</p>
                  </template>

                </div>
              </div>

              <!-- Top-level Non-Object controls -->
              <div v-else class="config-form-grid" style="grid-template-columns: 1fr;">
                <div class="form-group" style="width: 100%;">
                  <!-- Switch -->
                  <div v-if="getFieldType(configSchema[key], key) === 'switch'" class="switch-container">
                    <div class="switch-label-group">
                      <span class="form-label" style="font-size: 13px;">{{ configSchema[key].description || key }}</span>
                      <span v-if="configSchema[key].hint" class="form-hint">{{ configSchema[key].hint }}</span>
                    </div>
                    <label class="switch">
                      <input type="checkbox" v-model="localConfig[key]" />
                      <span class="slider-switch"></span>
                    </label>
                  </div>

                  <!-- Textarea -->
                  <textarea v-else-if="getFieldType(configSchema[key], key) === 'textarea'" v-model="localConfig[key]" class="form-control" style="min-height: 140px;"></textarea>

                  <!-- Select -->
                  <select v-else-if="getFieldType(configSchema[key], key) === 'select'" v-model="localConfig[key]" class="form-control">
                    <option v-for="opt in configSchema[key].options" :key="opt" :value="opt">{{ opt }}</option>
                  </select>

                  <!-- Provider ID Dropdown -->
                  <select v-else-if="getFieldType(configSchema[key], key) === 'provider_select'" v-model="localConfig[key]" class="form-control">
                    <option value="">-- 请选择供应商 (留空默认) --</option>
                    <option v-for="prov in providers" :key="prov.id" :value="prov.id">
                      {{ prov.name }} ({{ prov.id }})
                    </option>
                  </select>

                  <!-- Embedding Provider ID Dropdown or Input fallback -->
                  <template v-else-if="getFieldType(configSchema[key], key) === 'embedding_provider_select'">
                    <select v-if="embeddingProviders.length > 0" v-model="localConfig[key]" class="form-control">
                      <option value="">-- 请选择 Embedding 供应商 (留空默认) --</option>
                      <option v-for="prov in embeddingProviders" :key="prov.id" :value="prov.id">
                        {{ prov.name }} ({{ prov.id }})
                      </option>
                    </select>
                    <input v-else type="text" v-model="localConfig[key]" class="form-control" placeholder="无法查找到 Embedding 供应商，请输入 Provider ID" />
                  </template>

                  <!-- List (Blacklist / Array of strings) -->
                  <div v-else-if="getFieldType(configSchema[key], key) === 'list'" class="list-editor">
                    <div v-for="(item, idx) in localConfig[key]" :key="idx" class="list-editor-item">
                      <input type="text" v-model="localConfig[key][idx]" class="form-control" />
                      <button class="btn-danger-outline" style="padding: 0 12px;" @click="localConfig[key].splice(idx, 1)">&times;</button>
                    </div>
                    <button class="btn-secondary" style="align-self: flex-start; margin-top: 4px;" @click="localConfig[key].push('')">
                      <i class="fas fa-plus"></i> 添加条目
                    </button>
                  </div>

                  <!-- Persona Blacklist Multiselect Dropdown -->
                  <div v-else-if="getFieldType(configSchema[key], key) === 'persona_blacklist_select'" class="persona-tags-select" style="position: relative; width: 100%;">
                    <div class="multiselect-tag-container" style="display: flex; align-items: center; gap: 8px; background: var(--bg-element); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: var(--radius-md); min-height: 42px; width: 100%; flex-wrap: wrap; box-sizing: border-box; position: relative;">
                      <!-- Active pills -->
                      <span v-for="pId in localConfig[key]" :key="pId" class="active-tag-pill" style="display: inline-flex; align-items: center; gap: 4px; background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.3); color: var(--primary-color); padding: 2px 8px; border-radius: 4px; font-size: 12.5px; font-weight: 500; user-select: none;">
                        {{ getPersonaName(pId) }}
                        <span @click.stop="toggleBlacklistPersona(pId)" style="cursor: pointer; font-weight: bold; font-size: 13px; color: var(--primary-color); line-height: 1; padding-left: 2px;" onmouseover="this.style.color='var(--danger-color)'" onmouseout="this.style.color='var(--primary-color)'">&times;</span>
                      </span>
                      
                      <!-- Dropdown Input -->
                      <div style="position: relative; display: inline-flex; align-items: center; flex: 1; min-width: 160px;">
                        <input 
                          type="text" 
                          v-model="blacklistSearchQuery" 
                          @focus="showBlacklistDropdown = true"
                          @blur="handleBlacklistBlur"
                          placeholder="点击或检索选择禁用的人格..." 
                          style="width: 100%; border: none; background: transparent; color: var(--text-primary); outline: none; font-size: 13px;"
                        />
                        
                        <!-- Dropdown Menu -->
                        <div v-show="showBlacklistDropdown" class="dropdown-menu" style="position: absolute; top: 100%; left: 0; margin-top: 6px; z-index: 1000; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); box-shadow: var(--shadow-md); max-height: 200px; overflow-y: auto; min-width: 220px; padding: 4px 0; display: flex; flex-direction: column; gap: 2px;" @mousedown.prevent>
                          <div 
                            v-for="p in filteredBlacklistPersonas" 
                            :key="p.id"
                            style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; cursor: pointer; color: var(--text-primary); font-size: 13.5px; margin: 0; user-select: none; transition: background 0.2s;" 
                            :style="{ background: (localConfig[key] && localConfig[key].includes(p.id)) ? 'rgba(59, 130, 246, 0.08)' : 'transparent', color: (localConfig[key] && localConfig[key].includes(p.id)) ? 'var(--primary-color)' : 'var(--text-primary)' }"
                            @mouseover="$event.currentTarget.style.background = 'var(--bg-hover)'"
                            @mouseleave="$event.currentTarget.style.background = (localConfig[key] && localConfig[key].includes(p.id)) ? 'rgba(59, 130, 246, 0.08)' : 'transparent'"
                            @click="toggleBlacklistPersona(p.id)"
                          >
                            <span style="flex: 1;">{{ p.name }} ({{ p.id }})</span>
                            <i v-if="localConfig[key] && localConfig[key].includes(p.id)" class="fas fa-check" style="color: var(--primary-color); font-size: 12px;"></i>
                          </div>
                          <div v-if="filteredBlacklistPersonas.length === 0" style="padding: 8px 12px; color: var(--text-secondary); font-size: 12.5px; text-align: center;">暂无匹配人格</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Regular Inputs -->
                  <input v-else type="text" v-model="localConfig[key]" class="form-control" />
                </div>
              </div>

            </div>
          </template>

          <!-- Manual Thumbnail generation section (only under compression tab) -->
          <div v-if="activeSubTab === 'compression'" class="config-card">
            <div class="config-card-title">
              缩略图预生成 & 调试
            </div>
            <p class="form-hint" style="margin-top: -12px;">
              手动扫描全库并生成表情包的缩略图缓存。这对于在新服务器上预先缓存表情，或者调试缩略图生成异常非常有用。
            </p>
            <div style="display: flex; flex-direction: column; gap: 15px; background: var(--bg-element); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px;">
              <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div style="font-size: 13.5px; color: var(--text-primary); margin: 0;">
                  <strong>缩略图状态：</strong>
                  <span v-if="generationResult" style="color: var(--primary-color); font-weight: bold;">
                    总数 {{ generationResult.total }} | 成功 {{ generationResult.generated }} | 已存在 {{ generationResult.existed }} | 失败 {{ generationResult.failed }} (AVIF 支持: {{ generationResult.avif_supported ? '是' : '否' }})
                  </span>
                  <span v-else style="color: var(--text-secondary);">尚未进行手动预生成。</span>
                </div>
                <button type="button" class="btn-primary" :disabled="generatingThumbnails" @click="triggerThumbnailGeneration" style="display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
                  <i class="fas" :class="generatingThumbnails ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'"></i>
                  {{ generatingThumbnails ? '正在生成...' : '立即预生成全部缩略图' }}
                </button>
              </div>

              <!-- Error details if any failed -->
              <div v-if="generationResult && generationResult.errors && generationResult.errors.length > 0" style="margin-top: 10px; border-top: 1px dashed var(--border-color); padding-top: 12px;">
                <div style="font-size: 12.5px; font-weight: bold; color: var(--danger-color); margin-bottom: 8px;">
                  生成失败列表 (共 {{ generationResult.failed }} 个)：
                </div>
                <div style="max-height: 150px; overflow-y: auto; background: rgba(239, 68, 68, 0.03); border: 1px solid rgba(239, 68, 68, 0.15); border-radius: var(--radius-sm); padding: 8px; display: flex; flex-direction: column; gap: 4px;">
                  <div v-for="err in generationResult.errors" :key="err.filename" style="font-size: 11.5px; color: var(--text-primary); display: flex; gap: 8px; margin: 0;">
                    <span style="font-family: monospace; font-weight: bold; color: var(--danger-color); flex-shrink: 0;">{{ err.filename }}:</span>
                    <span style="color: var(--text-secondary); word-break: break-all;">{{ err.error }}</span>
                  </div>
                </div>
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
