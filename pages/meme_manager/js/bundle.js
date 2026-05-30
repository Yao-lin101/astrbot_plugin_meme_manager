(() => {
  // modules/toasts.js
  var { ref } = window.Vue;
  function useToasts() {
    const toasts = ref([]);
    let toastIdCounter = 0;
    const showToast = (message, type = "info", title = "\u7CFB\u7EDF\u63D0\u793A", duration = 3e3) => {
      const id = toastIdCounter++;
      toasts.value.push({ id, message, type, title });
      setTimeout(() => {
        removeToast(id);
      }, duration);
    };
    const removeToast = (id) => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    };
    return {
      toasts,
      showToast,
      removeToast
    };
  }

  // modules/modals.js
  var { ref: ref2, reactive, nextTick } = window.Vue;
  function useModals(showToast) {
    const confirmDialog = reactive({
      visible: false,
      title: "",
      description: "",
      confirmLabel: "\u786E\u8BA4",
      confirmClass: "",
      resolve: null
    });
    const dangerConfirmDialog = reactive({
      visible: false,
      title: "",
      description: "",
      actionLabel: "\u786E\u8BA4",
      countdown: 0,
      stage: "ack",
      // 'ack', 'countdown', 'input'
      timer: null,
      resolve: null
    });
    const moveModal = reactive({
      visible: false,
      resolve: null
    });
    const batchPersonaModal = reactive({
      visible: false,
      personas: []
    });
    const addCategoryForm = reactive({
      visible: false,
      name: ""
    });
    const renameCategoryModal = reactive({
      visible: false,
      category: "",
      originalCategory: ""
    });
    const importModal = reactive({
      visible: false,
      selectedEmojis: /* @__PURE__ */ new Set()
    });
    const confirm = (title, description, confirmLabel = "\u786E\u8BA4", confirmClass = "") => {
      return new Promise((resolve) => {
        confirmDialog.title = title;
        confirmDialog.description = description;
        confirmDialog.confirmLabel = confirmLabel;
        confirmDialog.confirmClass = confirmClass;
        confirmDialog.resolve = resolve;
        confirmDialog.visible = true;
      });
    };
    const handleConfirm = (value) => {
      confirmDialog.visible = false;
      if (confirmDialog.resolve) confirmDialog.resolve(value);
    };
    const showDangerConfirm = (title, description, actionLabel = "\u786E\u8BA4\u64CD\u4F5C") => {
      return new Promise((resolve) => {
        dangerConfirmDialog.title = title;
        dangerConfirmDialog.description = description;
        dangerConfirmDialog.actionLabel = actionLabel;
        dangerConfirmDialog.stage = "ack";
        dangerConfirmDialog.countdown = 5;
        dangerConfirmDialog.resolve = resolve;
        dangerConfirmDialog.visible = true;
      });
    };
    const startDangerCountdown = () => {
      dangerConfirmDialog.stage = "countdown";
      dangerConfirmDialog.timer = setInterval(() => {
        if (dangerConfirmDialog.countdown > 1) {
          dangerConfirmDialog.countdown--;
        } else {
          clearInterval(dangerConfirmDialog.timer);
          dangerConfirmDialog.stage = "input";
          nextTick(() => {
            const input = document.getElementById("danger-modal-ack");
            if (input) input.focus();
          });
        }
      }, 1e3);
    };
    const handleDangerConfirm = () => {
      const input = document.getElementById("danger-modal-ack");
      if (input && input.value.trim() === "CONFIRM") {
        dangerConfirmDialog.visible = false;
        if (dangerConfirmDialog.resolve) dangerConfirmDialog.resolve(true);
      } else {
        showToast("\u8BF7\u8F93\u5165\u5927\u5199\u7684 CONFIRM \u786E\u8BA4\u6B64\u64CD\u4F5C\uFF01", "warning", "\u8F93\u5165\u9519\u8BEF");
      }
    };
    const cancelDangerConfirm = () => {
      if (dangerConfirmDialog.timer) {
        clearInterval(dangerConfirmDialog.timer);
      }
      dangerConfirmDialog.visible = false;
      if (dangerConfirmDialog.resolve) dangerConfirmDialog.resolve(false);
    };
    const openBatchPersonaModal = () => {
      batchPersonaModal.personas = ["*"];
      batchPersonaModal.visible = true;
    };
    const closeBatchPersonaModal = () => {
      batchPersonaModal.visible = false;
      batchPersonaModal.personas = [];
    };
    const togglePersonaInBatch = (personaId) => {
      if (personaId === "*") {
        if (batchPersonaModal.personas.includes("*")) {
          batchPersonaModal.personas = [];
        } else {
          batchPersonaModal.personas = ["*"];
        }
      } else {
        const gIdx = batchPersonaModal.personas.indexOf("*");
        if (gIdx > -1) batchPersonaModal.personas.splice(gIdx, 1);
        const idx = batchPersonaModal.personas.indexOf(personaId);
        if (idx > -1) {
          batchPersonaModal.personas.splice(idx, 1);
        } else {
          batchPersonaModal.personas.push(personaId);
        }
      }
    };
    const openMoveModal = () => {
      moveModal.visible = true;
    };
    const closeMoveModal = () => {
      moveModal.visible = false;
    };
    const openImportModal = () => {
      importModal.selectedEmojis = /* @__PURE__ */ new Set();
      importModal.visible = true;
    };
    const closeImportModal = () => {
      importModal.visible = false;
      importModal.selectedEmojis = /* @__PURE__ */ new Set();
    };
    const toggleImportEmoji = (emoji) => {
      if (importModal.selectedEmojis.has(emoji)) {
        importModal.selectedEmojis.delete(emoji);
      } else {
        importModal.selectedEmojis.add(emoji);
      }
    };
    return {
      confirmDialog,
      dangerConfirmDialog,
      moveModal,
      batchPersonaModal,
      addCategoryForm,
      renameCategoryModal,
      importModal,
      confirm,
      handleConfirm,
      showDangerConfirm,
      startDangerCountdown,
      handleDangerConfirm,
      cancelDangerConfirm,
      openBatchPersonaModal,
      closeBatchPersonaModal,
      togglePersonaInBatch,
      openMoveModal,
      closeMoveModal,
      openImportModal,
      closeImportModal,
      toggleImportEmoji
    };
  }

  // modules/api.js
  var { ref: ref3, computed } = window.Vue;
  function useApi(showToast, pruneSelections) {
    const emojiData = ref3({});
    const emojiMtimes = ref3({});
    const tagDescriptions = ref3({});
    const systemPersonas = ref3([]);
    const personaTags = ref3({});
    const personaDedicatedTag = ref3("");
    const personaFilter = ref3("");
    const activeCategories = ref3(["all"]);
    const tabSearchQuery = ref3("");
    const drawerTagSearchQuery = ref3("");
    const selectedEmotions = ref3([]);
    const visibleLimit = ref3(40);
    const fetchEmojis = async () => {
      visibleLimit.value = 40;
      try {
        const personaId = personaFilter.value;
        personaDedicatedTag.value = personaTags.value[personaId] || "";
        const url = personaId ? `/api/emoji?persona_id=${encodeURIComponent(personaId)}` : "/api/emoji";
        const [emojiRes, tagRes] = await Promise.all([
          fetch(url).then((res) => {
            if (!res.ok) throw new Error("\u83B7\u53D6\u8868\u60C5\u5305\u6570\u636E\u5931\u8D25");
            return res.json();
          }),
          fetch("/api/emotions").then((res) => {
            if (!res.ok) throw new Error("\u83B7\u53D6\u7C7B\u522B\u63CF\u8FF0\u5931\u8D25");
            return res.json();
          })
        ]);
        emojiData.value = emojiRes.categories || {};
        emojiMtimes.value = emojiRes.mtimes || {};
        tagDescriptions.value = tagRes;
        if (pruneSelections) pruneSelections();
        const categories = Object.keys(emojiData.value);
        if (activeCategories.value.length === 0) {
          activeCategories.value = ["all"];
        } else {
          activeCategories.value = activeCategories.value.filter(
            (cat) => cat === "all" || categories.includes(cat)
          );
          if (activeCategories.value.length === 0) {
            activeCategories.value = ["all"];
          }
        }
      } catch (e) {
        console.error(e);
        showToast(e.message, "error", "\u52A0\u8F7D\u6570\u636E\u5931\u8D25");
      }
    };
    const fetchPersonas = async () => {
      try {
        const res = await fetch("/api/personas");
        if (!res.ok) throw new Error("\u83B7\u53D6\u7CFB\u7EDF\u4EBA\u683C\u5931\u8D25");
        systemPersonas.value = await res.json();
      } catch (e) {
        console.error(e);
      }
    };
    const fetchPersonaTags = async () => {
      try {
        const res = await fetch("/api/persona_tags");
        if (!res.ok) throw new Error("\u83B7\u53D6\u4EBA\u683C\u4E13\u5C5E\u6807\u7B7E\u5931\u8D25");
        personaTags.value = await res.json();
      } catch (e) {
        console.error(e);
      }
    };
    const savePersonaDedicatedTag = async () => {
      const personaId = personaFilter.value;
      if (!personaId) return;
      const tag = personaDedicatedTag.value;
      try {
        const res = await fetch("/api/persona_tags", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            persona_id: personaId,
            tag
          })
        });
        if (!res.ok) throw new Error("\u4FDD\u5B58\u4E13\u5C5E\u6807\u7B7E\u5931\u8D25");
        if (!tag || !tag.trim()) {
          delete personaTags.value[personaId];
        } else {
          personaTags.value[personaId] = tag.trim();
        }
        showToast("\u4E13\u5C5E\u6807\u7B7E\u5DF2\u4FDD\u5B58\uFF01", "success", "\u4FDD\u5B58\u6210\u529F");
      } catch (e) {
        showToast(e.message, "error", "\u4FDD\u5B58\u5931\u8D25");
      }
    };
    const filteredCategories = computed(() => {
      const query = tabSearchQuery.value.trim().toLowerCase();
      const categories = Object.keys(emojiData.value);
      if (!query) return categories;
      return categories.filter((category) => category.toLowerCase().includes(query));
    });
    const filteredDrawerTags = computed(() => {
      const query = drawerTagSearchQuery.value.trim().toLowerCase();
      const tags = Object.keys(emojiData.value);
      const unselectedTags = tags.filter((tag) => !selectedEmotions.value.includes(tag));
      if (!query) return unselectedTags;
      return unselectedTags.filter((tag) => tag.toLowerCase().includes(query));
    });
    const emojiTagsMap = computed(() => {
      const map = /* @__PURE__ */ new Map();
      Object.entries(emojiData.value).forEach(([cat, emos]) => {
        if (Array.isArray(emos)) {
          emos.forEach((emo) => {
            if (!map.has(emo)) map.set(emo, /* @__PURE__ */ new Set());
            map.get(emo).add(cat);
          });
        }
      });
      return map;
    });
    const allEmojisList = computed(() => {
      const allSet = /* @__PURE__ */ new Set();
      Object.values(emojiData.value).forEach((list) => {
        if (Array.isArray(list)) {
          list.forEach((emoji) => allSet.add(emoji));
        }
      });
      return Array.from(allSet).sort();
    });
    const activeCategoryEmojisList = computed(() => {
      if (activeCategories.value.includes("all") || activeCategories.value.length === 0) {
        return allEmojisList.value;
      }
      const firstCat = activeCategories.value[0];
      let intersection = new Set(emojiData.value[firstCat] || []);
      for (let i = 1; i < activeCategories.value.length; i++) {
        const cat = activeCategories.value[i];
        const emojisInCat = new Set(emojiData.value[cat] || []);
        intersection = new Set([...intersection].filter((x) => emojisInCat.has(x)));
      }
      return Array.from(intersection).sort();
    });
    const importableEmojisList = computed(() => {
      if (activeCategories.value.includes("all") || activeCategories.value.length === 0) return [];
      if (activeCategories.value.length > 1) return [];
      const currentList = emojiData.value[activeCategories.value[0]] || [];
      return allEmojisList.value.filter((emoji) => !currentList.includes(emoji));
    });
    const activeCategoryTimeGroups = computed(() => {
      if (activeCategories.value.length === 0) return [];
      const list = activeCategoryEmojisList.value;
      const now = /* @__PURE__ */ new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      const yesterdayStart = todayStart - 24 * 60 * 60 * 1e3;
      const sevenDaysAgoStart = todayStart - 7 * 24 * 60 * 60 * 1e3;
      const groups = [
        { title: "\u4ECA\u5929 (Today)", list: [] },
        { title: "\u6628\u5929 (Yesterday)", list: [] },
        { title: "\u6700\u8FD1\u4E00\u5468 (Last 7 Days)", list: [] },
        { title: "\u66F4\u65E9\u4EE5\u524D (Earlier)", list: [] }
      ];
      list.forEach((emoji) => {
        const mtimeSec = emojiMtimes.value[emoji] || 0;
        const mtimeMs = mtimeSec * 1e3;
        if (mtimeMs >= todayStart) {
          groups[0].list.push(emoji);
        } else if (mtimeMs >= yesterdayStart) {
          groups[1].list.push(emoji);
        } else if (mtimeMs >= sevenDaysAgoStart) {
          groups[2].list.push(emoji);
        } else {
          groups[3].list.push(emoji);
        }
      });
      groups.forEach((g) => {
        g.list.sort((a, b) => {
          const ta = emojiMtimes.value[a] || 0;
          const tb = emojiMtimes.value[b] || 0;
          return tb - ta;
        });
      });
      let count = 0;
      const limitedGroups = [];
      for (const g of groups) {
        if (g.list.length === 0) continue;
        const remaining = visibleLimit.value - count;
        if (remaining <= 0) break;
        if (g.list.length <= remaining) {
          limitedGroups.push(g);
          count += g.list.length;
        } else {
          limitedGroups.push({
            title: g.title,
            list: g.list.slice(0, remaining)
          });
          count += remaining;
          break;
        }
      }
      return limitedGroups;
    });
    const getEmojiTags = (emoji) => {
      const tags = emojiTagsMap.value.get(emoji);
      return tags ? Array.from(tags).sort() : [];
    };
    return {
      emojiData,
      emojiMtimes,
      tagDescriptions,
      systemPersonas,
      personaTags,
      personaDedicatedTag,
      personaFilter,
      activeCategories,
      activeCategoryEmojisList,
      activeEmojisCount: computed(() => activeCategoryEmojisList.value.length),
      tabSearchQuery,
      drawerTagSearchQuery,
      fetchEmojis,
      fetchPersonas,
      fetchPersonaTags,
      savePersonaDedicatedTag,
      filteredCategories,
      filteredDrawerTags,
      emojiTagsMap,
      allEmojisList,
      importableEmojisList,
      activeCategoryTimeGroups,
      getEmojiTags,
      visibleLimit,
      selectedEmotions
    };
  }

  // modules/selection.js
  var { ref: ref4, computed: computed2 } = window.Vue;
  function useSelection(emojiData, allEmojisList) {
    const selectedEmojis = ref4(/* @__PURE__ */ new Map());
    const selectionEnabled = computed2(() => selectedEmojis.value.size > 0);
    const pruneSelections = () => {
      for (const [key, item] of selectedEmojis.value.entries()) {
        const list = emojiData.value[item.category];
        if (!list || !list.includes(item.emoji)) {
          selectedEmojis.value.delete(key);
        }
      }
    };
    const toggleSelectionMode = () => {
      selectedEmojis.value.clear();
    };
    const isEmojiSelected = (category, emoji) => {
      return selectedEmojis.value.has(`${category}:${emoji}`);
    };
    const toggleEmojiSelection = (category, emoji) => {
      const key = `${category}:${emoji}`;
      if (selectedEmojis.value.has(key)) {
        selectedEmojis.value.delete(key);
      } else {
        selectedEmojis.value.set(key, { category, emoji });
      }
    };
    const getCategorySelectedCount = (category) => {
      let count = 0;
      for (const item of selectedEmojis.value.values()) {
        if (item.category === category) count++;
      }
      return count;
    };
    const getVisibleSelectedCount = (visibleList, category) => {
      let count = 0;
      if (!visibleList) return 0;
      visibleList.forEach((emoji) => {
        if (selectedEmojis.value.has(`${category}:${emoji}`)) count++;
      });
      return count;
    };
    const isAllSelectedInCategory = (category, visibleList) => {
      const list = visibleList || (category === "all" ? allEmojisList.value : emojiData.value[category] || []);
      if (list.length === 0) return false;
      return list.every((emoji) => isEmojiSelected(category, emoji));
    };
    const toggleCategorySelection = (category, visibleList) => {
      const list = visibleList || (category === "all" ? allEmojisList.value : emojiData.value[category] || []);
      if (isAllSelectedInCategory(category, list)) {
        list.forEach((emoji) => {
          selectedEmojis.value.delete(`${category}:${emoji}`);
        });
      } else {
        list.forEach((emoji) => {
          selectedEmojis.value.set(`${category}:${emoji}`, { category, emoji });
        });
      }
    };
    return {
      selectedEmojis,
      selectionEnabled,
      pruneSelections,
      toggleSelectionMode,
      isEmojiSelected,
      toggleEmojiSelection,
      getCategorySelectedCount,
      getVisibleSelectedCount,
      isAllSelectedInCategory,
      toggleCategorySelection
    };
  }

  // modules/sync.js
  var { ref: ref5 } = window.Vue;
  function useSync(showToast, fetchEmojis) {
    const syncChecking = ref5(false);
    const syncStatus = ref5({
      inSync: true,
      missingInConfig: [],
      deletedCategories: []
    });
    const imgHostSyncing = ref5(false);
    const imgHostStatus = ref5({
      provider: "--",
      remoteImageCount: "--",
      remoteStorageSize: "--",
      uploadCount: 0,
      downloadCount: 0
    });
    const formatBytes = (bytes) => {
      if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes < 0) return "\u672A\u77E5";
      if (bytes === 0) return "0 B";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let value = bytes;
      let unitIndex = 0;
      while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex++;
      }
      return `${value.toFixed(1)} ${units[unitIndex]}`;
    };
    const checkSyncStatus = async (showAlert = true) => {
      syncChecking.value = true;
      try {
        const res = await fetch("/api/sync/status");
        if (!res.ok) throw new Error("\u83B7\u53D6\u72B6\u6001\u5931\u8D25");
        const data = await res.json();
        if (data.status === "error") throw new Error(data.message);
        const diffs = data.differences || data;
        syncStatus.value.missingInConfig = diffs.missing_in_config || [];
        syncStatus.value.deletedCategories = diffs.deleted_categories || [];
        syncStatus.value.inSync = syncStatus.value.missingInConfig.length === 0 && syncStatus.value.deletedCategories.length === 0;
        if (showAlert) {
          showToast("\u914D\u7F6E\u540C\u6B65\u72B6\u6001\u68C0\u67E5\u5B8C\u6BD5\u3002", "success", "\u5237\u65B0\u6210\u529F");
        }
      } catch (e) {
        showToast(e.message, "error", "\u540C\u6B65\u68C0\u67E5\u5931\u8D25");
      } finally {
        syncChecking.value = false;
      }
    };
    const syncConfig = async () => {
      try {
        const res = await fetch("/api/sync/config", { method: "POST" });
        if (!res.ok) throw new Error("\u540C\u6B65\u5931\u8D25");
        showToast("\u5DF2\u6210\u529F\u5C06\u78C1\u76D8\u6587\u4EF6\u5939\u540C\u6B65\u81F3\u7CFB\u7EDF\u914D\u7F6E", "success", "\u914D\u7F6E\u540C\u6B65\u5B8C\u6210");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u540C\u6B65\u5931\u8D25");
      }
    };
    const restoreCategory = async (category) => {
      try {
        const res = await fetch("/api/category/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, description: "\u8BF7\u6DFB\u52A0\u63CF\u8FF0" })
        });
        if (!res.ok) throw new Error("\u6062\u590D\u6807\u7B7E\u6587\u4EF6\u5939\u5931\u8D25");
        showToast(`\u6807\u7B7E\u300C${category}\u300D\u5BF9\u5E94\u6587\u4EF6\u5939\u5DF2\u6210\u529F\u91CD\u5EFA\u3002`, "success", "\u6062\u590D\u6210\u529F");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u6062\u590D\u5931\u8D25");
      }
    };
    const removeFromConfig = async (category) => {
      try {
        const res = await fetch("/api/category/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category })
        });
        if (!res.ok) throw new Error("\u79FB\u9664\u914D\u7F6E\u5931\u8D25");
        showToast(`\u5DF2\u4ECE\u914D\u7F6E\u4E2D\u79FB\u9664\u6807\u7B7E \u300C${category}\u300D`, "success", "\u79FB\u9664\u6210\u529F");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u5220\u9664\u914D\u7F6E\u5931\u8D25");
      }
    };
    const checkImgHostSyncStatus = async (showAlert = true) => {
      try {
        const res = await fetch("/api/img_host/sync/status");
        if (!res.ok) throw new Error("\u83B7\u53D6\u56FE\u5E8A\u72B6\u6001\u5931\u8D25");
        const data = await res.json();
        const uploadCount = data.upload_count ?? data.to_upload?.length ?? 0;
        const downloadCount = data.download_count ?? data.to_download?.length ?? 0;
        const remoteImageCount = data.remote_image_count ?? data.remote_count ?? data.remote_images?.length ?? 0;
        let remoteStorageText = "\u672A\u77E5";
        if (typeof data.remote_total_bytes === "number") {
          remoteStorageText = formatBytes(data.remote_total_bytes);
        } else if (typeof data.remote_total_bytes_estimated === "number") {
          remoteStorageText = `${formatBytes(data.remote_total_bytes_estimated)}\uFF08\u4F30\u7B97\uFF09`;
        }
        imgHostStatus.value.provider = data.provider_label || "\u672A\u77E5\u56FE\u5E8A";
        imgHostStatus.value.remoteImageCount = remoteImageCount;
        imgHostStatus.value.remoteStorageSize = remoteStorageText;
        imgHostStatus.value.uploadCount = uploadCount;
        imgHostStatus.value.downloadCount = downloadCount;
        if (showAlert) {
          showToast(
            `${data.provider_label || "\u56FE\u5E8A"}\u5DF2\u5237\u65B0\u3002\u4E91\u7AEF\uFF1A${remoteImageCount} \u5F20\uFF0C\u5F85\u4E0A\u4F20\uFF1A${uploadCount} \u4E2A\u3002`,
            "success",
            "\u5237\u65B0\u6210\u529F"
          );
        }
      } catch (e) {
        showToast(e.message, "error", "\u56FE\u5E8A\u540C\u6B65\u68C0\u67E5\u5931\u8D25");
      }
    };
    const syncToRemote = async () => {
      imgHostSyncing.value = true;
      showToast("\u6B63\u5728\u5C06\u5F85\u4E0A\u4F20\u6587\u4EF6\u540C\u6B65\u81F3\u4E91\u7AEF\u56FE\u5E8A...", "info", "\u4E0A\u4F20\u540C\u6B65\u4E2D", 5e3);
      try {
        const res = await fetch("/api/img_host/sync/upload", { method: "POST" });
        if (!res.ok) throw new Error("\u4E0A\u4F20\u540C\u6B65\u5931\u8D25");
        showToast("\u672C\u5730\u8868\u60C5\u5305\u6210\u529F\u5168\u91CF\u540C\u6B65\u81F3\u4E91\u7AEF\u56FE\u5E8A", "success", "\u540C\u6B65\u6210\u529F");
        await checkImgHostSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u540C\u6B65\u5931\u8D25");
      } finally {
        imgHostSyncing.value = false;
      }
    };
    const syncFromRemote = async () => {
      imgHostSyncing.value = true;
      showToast("\u6B63\u5728\u4ECE\u4E91\u7AEF\u4E0B\u8F7D\u8868\u60C5\u5305...", "info", "\u4E0B\u8F7D\u540C\u6B65\u4E2D", 5e3);
      try {
        const res = await fetch("/api/img_host/sync/download", { method: "POST" });
        if (!res.ok) throw new Error("\u4E0B\u8F7D\u540C\u6B65\u5931\u8D25");
        showToast("\u4E91\u7AEF\u56FE\u5E8A\u6210\u529F\u5168\u91CF\u62C9\u53D6\u540C\u6B65\u81F3\u672C\u5730", "success", "\u540C\u6B65\u6210\u529F");
        await fetchEmojis();
        await checkImgHostSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u540C\u6B65\u5931\u8D25");
      } finally {
        imgHostSyncing.value = false;
      }
    };
    return {
      syncChecking,
      syncStatus,
      imgHostSyncing,
      imgHostStatus,
      formatBytes,
      checkSyncStatus,
      syncConfig,
      restoreCategory,
      removeFromConfig,
      checkImgHostSyncStatus,
      syncToRemote,
      syncFromRemote
    };
  }

  // modules/categories.js
  var { ref: ref6 } = window.Vue;
  function useCategories(showToast, fetchEmojis, checkSyncStatus, renameCategoryModal, addCategoryForm, emojiData, activeCategories, confirm, showDangerConfirm) {
    const openRenameCategory = (category) => {
      renameCategoryModal.category = category;
      renameCategoryModal.originalCategory = category;
      renameCategoryModal.visible = true;
    };
    const saveRenameCategory = async () => {
      const oldName = renameCategoryModal.originalCategory;
      const newName = renameCategoryModal.category.trim();
      if (!newName) {
        showToast("\u6807\u7B7E\u540D\u79F0\u4E0D\u80FD\u4E3A\u7A7A", "warning");
        return;
      }
      if (oldName === newName) {
        renameCategoryModal.visible = false;
        return;
      }
      try {
        const res = await fetch("/api/category/rename", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            old_name: oldName,
            new_name: newName
          })
        });
        if (!res.ok) throw new Error("\u91CD\u547D\u540D\u7C7B\u522B\u5931\u8D25");
        showToast(`\u6807\u7B7E\u5DF2\u6210\u529F\u4ECE\u300C${oldName}\u300D\u91CD\u547D\u540D\u4E3A\u300C${newName}\u300D\u3002`, "success", "\u91CD\u547D\u540D\u6210\u529F");
        renameCategoryModal.visible = false;
        const idx = activeCategories.value.indexOf(oldName);
        if (idx > -1) {
          activeCategories.value[idx] = newName;
        }
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u91CD\u547D\u540D\u5931\u8D25");
      }
    };
    const saveNewCategory = async () => {
      const name = addCategoryForm.name.trim();
      if (!name) {
        showToast("\u8BF7\u8F93\u5165\u6807\u7B7E\u540D\u79F0\u518D\u4FDD\u5B58", "warning");
        return;
      }
      try {
        const res = await fetch("/api/category/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: name })
        });
        if (!res.ok) throw new Error("\u6DFB\u52A0\u6807\u7B7E\u5931\u8D25");
        showToast(`\u65B0\u6807\u7B7E\u300C${name}\u300D\u6DFB\u52A0\u6210\u529F\u3002`, "success", "\u4FDD\u5B58\u6210\u529F");
        addCategoryForm.name = "";
        addCategoryForm.visible = false;
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u6DFB\u52A0\u5931\u8D25");
      }
    };
    const clearCategory = async (category) => {
      const count = emojiData.value[category]?.length || 0;
      if (count === 0) {
        showToast("\u8BE5\u6807\u7B7E\u5F53\u524D\u4E3A\u7A7A\uFF0C\u65E0\u9700\u6E05\u7A7A", "info");
        return;
      }
      const confirmed = await showDangerConfirm(
        `\u6E05\u7A7A\u6807\u7B7E\u300C${category}\u300D`,
        `\u786E\u5B9A\u8981\u5220\u9664\u6807\u7B7E\u300C${category}\u300D\u4E0B\u7684\u5168\u90E8 ${count} \u4E2A\u8868\u60C5\u6587\u4EF6\u5417\uFF1F\u4FDD\u7559\u6807\u7B7E\u540D\u79F0\u548C\u63CF\u8FF0\u3002`
      );
      if (!confirmed) return;
      try {
        const res = await fetch("/api/category/clear", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category })
        });
        if (!res.ok) throw new Error("\u6E05\u7A7A\u5931\u8D25");
        const data = await res.json();
        showToast(`\u5DF2\u6E05\u7A7A\u6807\u7B7E ${category}\uFF0C\u5220\u9664\u4E86 ${data.deleted_count} \u4E2A\u8868\u60C5\u5305\u3002`, "success", "\u6E05\u7A7A\u6210\u529F");
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u6E05\u7A7A\u5931\u8D25");
      }
    };
    const deleteCategory = async (category) => {
      const confirmed = await confirm(
        `\u5220\u9664\u6807\u7B7E\u300C${category}\u300D`,
        `\u786E\u8BA4\u5220\u9664\u6807\u7B7E\u300C${category}\u300D\u5417\uFF1F\u6B64\u64CD\u4F5C\u5C06\u6E05\u9664\u8BE5\u6807\u7B7E\u7684\u6240\u6709\u8868\u60C5\u5305\u6807\u7B7E\uFF0C\u82E5\u8868\u60C5\u5305\u4E0D\u5C5E\u4E8E\u5176\u4ED6\u4EFB\u4F55\u6807\u7B7E\uFF0C\u5BF9\u5E94\u7684\u78C1\u76D8\u6587\u4EF6\u5C06\u88AB\u7269\u7406\u5220\u9664\u3002`,
        "\u786E\u8BA4\u5220\u9664",
        "danger"
      );
      if (!confirmed) return;
      try {
        const res = await fetch("/api/category/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category })
        });
        if (!res.ok) throw new Error("\u5220\u9664\u5931\u8D25");
        showToast(`\u5DF2\u6210\u529F\u5220\u9664\u6807\u7B7E ${category}`, "success", "\u5220\u9664\u6210\u529F");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "\u5220\u9664\u5931\u8D25");
      }
    };
    return {
      openRenameCategory,
      saveRenameCategory,
      saveNewCategory,
      clearCategory,
      deleteCategory
    };
  }

  // modules/emojiActions.js
  var { ref: ref7, reactive: reactive2, nextTick: nextTick2 } = window.Vue;
  function useEmojiActions({
    showToast,
    fetchEmojis,
    activeCategories,
    selectionEnabled,
    selectedEmojis,
    systemPersonas,
    emojiData,
    allEmojisList,
    getEmojiTags,
    confirm,
    showDangerConfirm,
    moveModal,
    batchPersonaModal,
    importModal,
    closeImportModal,
    drawerTagSearchQuery,
    selectedEmotions
  }) {
    const activeDetailEmoji = ref7(null);
    const detailMetadata = ref7(null);
    const selectedPersonas = ref7([]);
    const detailDrawerLoading = ref7(false);
    const uploadStateByCategory = ref7(/* @__PURE__ */ new Map());
    const contextMenu = reactive2({
      visible: false,
      x: 0,
      y: 0,
      targetCategory: null,
      targetEmoji: null,
      targetItems: [],
      pasteableItems: []
    });
    const clipboardItems = ref7([]);
    const toggleDetailDrawer = async (category, emoji) => {
      if (activeDetailEmoji.value === emoji) {
        closeDetailDrawer();
        return;
      }
      closeDetailDrawer();
      activeDetailEmoji.value = emoji;
      detailDrawerLoading.value = true;
      try {
        const res = await fetch(`/api/emoji/info/${encodeURIComponent(emoji)}`);
        if (!res.ok) throw new Error("\u83B7\u53D6\u5C5E\u6027\u5931\u8D25");
        const metadata = await res.json();
        if (activeDetailEmoji.value !== emoji) return;
        detailMetadata.value = metadata;
        selectedEmotions.value = metadata.emotions || [];
        selectedPersonas.value = metadata.personas || [];
      } catch (e) {
        showToast(e.message, "error", "\u52A0\u8F7D\u8868\u60C5\u5C5E\u6027\u5931\u8D25");
        closeDetailDrawer();
      } finally {
        detailDrawerLoading.value = false;
      }
    };
    const closeDetailDrawer = () => {
      activeDetailEmoji.value = null;
      detailMetadata.value = null;
      selectedEmotions.value = [];
      selectedPersonas.value = [];
      drawerTagSearchQuery.value = "";
    };
    const toggleTagInDrawer = (tag) => {
      const idx = selectedEmotions.value.indexOf(tag);
      if (idx > -1) {
        selectedEmotions.value.splice(idx, 1);
      } else {
        selectedEmotions.value.push(tag);
      }
    };
    const togglePersonaInDrawer = (personaId) => {
      if (personaId === "*") {
        if (selectedPersonas.value.includes("*")) {
          selectedPersonas.value = [];
        } else {
          selectedPersonas.value = ["*"];
        }
      } else {
        const gIdx = selectedPersonas.value.indexOf("*");
        if (gIdx > -1) selectedPersonas.value.splice(gIdx, 1);
        const idx = selectedPersonas.value.indexOf(personaId);
        if (idx > -1) {
          selectedPersonas.value.splice(idx, 1);
        } else {
          selectedPersonas.value.push(personaId);
        }
      }
    };
    const handleCreateTagInDrawer = async () => {
      const newTag = drawerTagSearchQuery.value.trim();
      if (!newTag) return;
      const allCategories = Object.keys(emojiData.value);
      const existingCat = allCategories.find((cat) => cat.toLowerCase() === newTag.toLowerCase());
      if (existingCat) {
        if (!selectedEmotions.value.includes(existingCat)) {
          selectedEmotions.value.push(existingCat);
        }
        drawerTagSearchQuery.value = "";
        return;
      }
      try {
        const res = await fetch("/api/category/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: newTag })
        });
        if (!res.ok) throw new Error("\u521B\u5EFA\u6807\u7B7E\u5931\u8D25");
        emojiData.value[newTag] = [];
        if (!selectedEmotions.value.includes(newTag)) {
          selectedEmotions.value.push(newTag);
        }
        showToast(`\u5DF2\u6210\u529F\u521B\u5EFA\u65B0\u6807\u7B7E\u300C${newTag}\u300D\u5E76\u6DFB\u52A0`, "success", "\u521B\u5EFA\u6210\u529F");
        drawerTagSearchQuery.value = "";
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u521B\u5EFA\u5931\u8D25");
      }
    };
    const handleBackspace = () => {
      if (drawerTagSearchQuery.value === "" && selectedEmotions.value.length > 0) {
        selectedEmotions.value.pop();
      }
    };
    const saveEmojiAttributes = async (closeAfterSave = true) => {
      if (selectedEmotions.value.length === 0) {
        showToast("\u8BF7\u81F3\u5C11\u9009\u62E9\u4E00\u4E2A\u6807\u7B7E\u3002", "warning", "\u4FDD\u5B58\u63D0\u793A");
        return;
      }
      const personas = selectedPersonas.value.length === 0 ? ["*"] : selectedPersonas.value;
      const emoji = activeDetailEmoji.value;
      try {
        const res = await fetch("/api/emoji/edit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: emoji,
            emotions: selectedEmotions.value,
            personas
          })
        });
        if (!res.ok) throw new Error("\u4FDD\u5B58\u5C5E\u6027\u5931\u8D25");
        showToast("\u5C5E\u6027\u4FDD\u5B58\u6210\u529F\uFF01", "success", "\u4FEE\u6539\u6210\u529F");
        if (closeAfterSave) {
          closeDetailDrawer();
        }
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u4FDD\u5B58\u5931\u8D25");
      }
    };
    const deleteEmoji = async (category, emoji) => {
      const isAll = category === "all";
      const title = isAll ? "\u7269\u7406\u5220\u9664\u8868\u60C5\u5305" : "\u5220\u9664\u6807\u7B7E / \u6587\u4EF6";
      const promptText = isAll ? "\u786E\u8BA4\u7269\u7406\u5220\u9664\u8BE5\u8868\u60C5\u5305\u5417\uFF1F\u6B64\u64CD\u4F5C\u5C06\u6C38\u4E45\u4ECE\u78C1\u76D8\u548C\u6240\u6709\u6807\u7B7E\u4E0B\u5220\u9664\u8BE5\u8868\u60C5\u6587\u4EF6\uFF01" : `\u786E\u8BA4\u4ECE\u6807\u7B7E\u300C${category}\u300D\u4E0B\u79FB\u9664\u8868\u60C5\u5305\uFF1F\u82E5\u8BE5\u8868\u60C5\u5305\u4E0D\u5C5E\u4E8E\u5176\u4ED6\u4EFB\u4F55\u6807\u7B7E\uFF0C\u5B83\u5C06\u88AB\u7269\u7406\u5220\u9664\u3002`;
      const confirmed = await confirm(
        title,
        promptText,
        "\u786E\u8BA4\u5220\u9664",
        "danger"
      );
      if (!confirmed) return;
      try {
        const res = await fetch("/api/emoji/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, image_file: emoji })
        });
        if (!res.ok) throw new Error("\u5220\u9664\u5931\u8D25");
        selectedEmojis.value.delete(`${category}:${emoji}`);
        showToast("\u8868\u60C5\u5305\u5DF2\u6210\u529F\u5220\u9664", "success", "\u5220\u9664\u6210\u529F");
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u5220\u9664\u5931\u8D25");
      }
    };
    const batchDeleteSelected = async () => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;
      const confirmed = await confirm(
        "\u6279\u91CF\u5220\u9664\u8868\u60C5\u5305",
        `\u786E\u8BA4\u5220\u9664\u5DF2\u9009\u4E2D\u7684 ${items.length} \u4E2A\u8868\u60C5\u5305\uFF1F\u8FD9\u4F1A\u79FB\u9664\u5176\u6807\u7B7E\uFF0C\u82E5\u8BE5\u8868\u60C5\u5305\u4E0D\u5C5E\u4E8E\u5176\u4ED6\u4EFB\u4F55\u6807\u7B7E\uFF0C\u5B83\u5C06\u88AB\u7269\u7406\u5220\u9664\u3002`,
        "\u786E\u8BA4\u6279\u91CF\u5220\u9664",
        "danger"
      );
      if (!confirmed) return;
      const grouped = {};
      items.forEach((item) => {
        const cats = item.category === "all" ? getEmojiTags(item.emoji) : [item.category];
        cats.forEach((cat) => {
          if (!grouped[cat]) grouped[cat] = [];
          if (!grouped[cat].includes(item.emoji)) {
            grouped[cat].push(item.emoji);
          }
        });
      });
      let successCount = 0;
      for (const [cat, files] of Object.entries(grouped)) {
        try {
          const res = await fetch("/api/emoji/batch_delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: cat, image_files: files })
          });
          if (res.ok) {
            const result = await res.json();
            successCount += result.deleted_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }
      showToast(`\u5DF2\u6210\u529F\u6279\u91CF\u5220\u9664 ${successCount} \u4E2A\u8868\u60C5\u5305\u3002`, "success", "\u6279\u91CF\u5220\u9664\u5B8C\u6210");
      selectedEmojis.value.clear();
      await fetchEmojis();
    };
    const batchConvertToGif = async () => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;
      const confirmed = await confirm(
        "\u8F6C\u6362\u4E3A GIF",
        `\u786E\u8BA4\u5C06\u9009\u4E2D\u7684 ${items.length} \u4E2A\u8868\u60C5\u5305\u8F6C\u6362\u4E3A GIF \u683C\u5F0F\u5417\uFF1F(\u79FB\u52A8\u7AEF QQ \u5BF9 WEBP \u52A8\u56FE\u652F\u6301\u4E0D\u4F73\uFF0C\u63A8\u8350\u8F6C\u6362)`,
        "\u786E\u8BA4\u8F6C\u6362",
        "primary"
      );
      if (!confirmed) return;
      const filenames = Array.from(new Set(items.map((item) => item.emoji)));
      try {
        const res = await fetch("/api/emoji/batch_convert_gif", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames })
        });
        if (res.ok) {
          const result = await res.json();
          showToast(
            `\u6210\u529F\u8F6C\u6362 ${result.converted_count} \u4E2A\uFF0C\u8DF3\u8FC7 ${result.skipped_count} \u4E2A\uFF0C\u5931\u8D25 ${result.failed_count} \u4E2A\u3002`,
            "success",
            "\u8F6C\u6362\u5B8C\u6210"
          );
        } else {
          throw new Error("\u8F6C\u6362\u8BF7\u6C42\u5931\u8D25");
        }
      } catch (e) {
        showToast(e.message, "error", "\u8F6C\u6362\u5931\u8D25");
      }
      selectedEmojis.value.clear();
      await fetchEmojis();
    };
    const saveBatchPersonas = async () => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;
      const filenames = items.map((item) => item.emoji);
      const personas = batchPersonaModal.personas.length === 0 ? ["*"] : batchPersonaModal.personas;
      try {
        const res = await fetch("/api/emoji/batch_edit_personas", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filenames,
            personas
          })
        });
        if (!res.ok) throw new Error("\u6279\u91CF\u66F4\u65B0\u4EBA\u683C\u9650\u5236\u5931\u8D25");
        showToast("\u6279\u91CF\u8BBE\u7F6E\u4EBA\u683C\u9650\u5236\u6210\u529F\uFF01", "success", "\u4FEE\u6539\u6210\u529F");
        batchPersonaModal.visible = false;
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u6279\u91CF\u8BBE\u7F6E\u5931\u8D25");
      }
    };
    const handleMoveTarget = async (targetCategory) => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;
      const grouped = {};
      items.forEach((item) => {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item.emoji);
      });
      let movedCount = 0;
      for (const [sourceCat, files] of Object.entries(grouped)) {
        try {
          const res = await fetch("/api/emoji/batch_move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              source_category: sourceCat,
              target_category: targetCategory,
              image_files: files
            })
          });
          if (res.ok) {
            const data = await res.json();
            movedCount += data.moved_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }
      showToast(`\u5DF2\u6210\u529F\u5C06 ${movedCount} \u4E2A\u8868\u60C5\u5305\u79FB\u52A8\u5230 ${targetCategory}`, "success", "\u79FB\u52A8\u6210\u529F");
      moveModal.visible = false;
      selectedEmojis.value.clear();
      await fetchEmojis();
    };
    const clearAllEmojiFiles = async () => {
      const totalCount = Object.values(emojiData.value).reduce((sum, list) => sum + (list?.length || 0), 0);
      if (totalCount === 0) {
        showToast("\u5E93\u4E2D\u6CA1\u6709\u4EFB\u4F55\u8868\u60C5\u5305\u53EF\u4EE5\u6E05\u7A7A", "warning");
        return;
      }
      const confirmed = await showDangerConfirm(
        "\u6E05\u7A7A\u6240\u6709\u8868\u60C5\u5305",
        `\u786E\u8BA4\u5F7B\u5E95\u6E05\u7A7A\u5E93\u4E2D\u7684\u6240\u6709 ${totalCount} \u4E2A\u8868\u60C5\u5305\uFF1F\u6B64\u64CD\u4F5C\u5C06\u5220\u9664\u6240\u6709\u78C1\u76D8\u6587\u4EF6\uFF0C\u4F46\u4FDD\u7559\u6807\u7B7E\u76EE\u5F55\u914D\u7F6E\u3002`
      );
      if (!confirmed) return;
      try {
        const res = await fetch("/api/emoji/clear_all", { method: "POST" });
        if (!res.ok) throw new Error("\u6E05\u7A7A\u5931\u8D25");
        const data = await res.json();
        showToast(`\u5DF2\u6E05\u7A7A\u5168\u90E8\u8868\u60C5\u5305\uFF0C\u5171\u5220\u9664 ${data.deleted_count} \u4E2A\u6587\u4EF6\u3002`, "success", "\u6E05\u7A7A\u6210\u529F");
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u6E05\u7A7A\u5931\u8D25");
      }
    };
    const submitImport = async () => {
      const category = activeCategories.value[0];
      if (!category || category === "all") return;
      const filenames = Array.from(importModal.selectedEmojis);
      if (filenames.length === 0) return;
      try {
        const res = await fetch("/api/emoji/batch_import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, filenames })
        });
        if (!res.ok) throw new Error("\u6279\u91CF\u5BFC\u5165\u5931\u8D25");
        showToast(`\u6210\u529F\u5BFC\u5165 ${filenames.length} \u4E2A\u8868\u60C5\u5230\u6807\u7B7E ${category}`, "success", "\u5BFC\u5165\u6210\u529F");
        closeImportModal();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u5BFC\u5165\u5931\u8D25");
      }
    };
    const onDragStart = (event, emoji, category) => {
      let dragItems = [];
      const key = `${category}:${emoji}`;
      if (selectionEnabled.value && selectedEmojis.value.has(key)) {
        dragItems = Array.from(selectedEmojis.value.values());
      } else {
        dragItems = [{ category, emoji }];
      }
      event.dataTransfer.setData("application/json", JSON.stringify({ items: dragItems, sourceCategory: category }));
      event.dataTransfer.effectAllowed = "move";
    };
    const onDropEmoji = async (event, targetCategory) => {
      try {
        const dataStr = event.dataTransfer.getData("application/json");
        if (!dataStr) return;
        const { items, sourceCategory } = JSON.parse(dataStr);
        if (sourceCategory === targetCategory) return;
        const res = await fetch("/api/emoji/batch_move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_category: sourceCategory,
            target_category: targetCategory,
            image_files: items.map((i) => i.emoji)
          })
        });
        if (!res.ok) throw new Error("\u79FB\u52A8\u5931\u8D25");
        const result = await res.json();
        showToast(`\u6210\u529F\u5C06 ${result.moved_count} \u4E2A\u8868\u60C5\u5305\u79FB\u52A8\u5230\u6807\u7B7E ${targetCategory}`, "success", "\u79FB\u52A8\u6210\u529F");
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "\u79FB\u52A8\u5931\u8D25");
      }
    };
    const triggerFileInput = (category) => {
      const input = document.getElementById(`file-input-${category}`);
      if (input) input.click();
    };
    const onFileSelected = (event, category) => {
      const files = event.target.files;
      if (files && files.length > 0) {
        uploadFiles(files, category);
      }
      event.target.value = "";
    };
    const onUploadDrop = (event, category) => {
      const files = event.dataTransfer.files;
      if (files && files.length > 0) {
        uploadFiles(files, category);
      }
    };
    const uploadFiles = async (files, category) => {
      if (uploadStateByCategory.value.has(category)) {
        showToast(`\u5F53\u524D\u6807\u7B7E ${category} \u6B63\u5728\u4E0A\u4F20\u4E2D\uFF0C\u8BF7\u7A0D\u5019\u3002`, "warning");
        return;
      }
      const total = files.length;
      uploadStateByCategory.value.set(category, { progress: 0, text: `\u51C6\u5907\u4E0A\u4F20 0/${total}` });
      let completed = 0;
      let failed = 0;
      let dups = 0;
      for (let i = 0; i < total; i++) {
        const file = files[i];
        uploadStateByCategory.value.set(category, {
          progress: Math.round(i / total * 100),
          text: `\u4E0A\u4F20\u4E2D: ${i + 1}/${total} (${file.name})`
        });
        const formData = new FormData();
        formData.append("category", category);
        formData.append("image_file", file);
        try {
          const res = await fetch("/api/emoji/add", {
            method: "POST",
            body: formData
          });
          if (res.status === 409) {
            dups++;
          } else if (!res.ok) {
            throw new Error();
          } else {
            completed++;
          }
        } catch (e) {
          failed++;
        }
      }
      uploadStateByCategory.value.delete(category);
      showToast(
        `\u4E0A\u4F20\u5B8C\u6210\uFF01\u6210\u529F ${completed} \u4E2A` + (dups > 0 ? `\uFF0C\u91CD\u590D\u8DF3\u8FC7 ${dups} \u4E2A` : "") + (failed > 0 ? `\uFF0C\u5931\u8D25 ${failed} \u4E2A` : ""),
        failed > 0 ? "warning" : "success",
        "\u4E0A\u4F20\u5B8C\u6BD5"
      );
      await fetchEmojis();
    };
    const openContextMenu = (event, category, emoji) => {
      const key = `${category}:${emoji}`;
      let targetItems = [];
      if (selectionEnabled.value && selectedEmojis.value.has(key)) {
        targetItems = Array.from(selectedEmojis.value.values());
      } else {
        targetItems = [{ category, emoji }];
      }
      const pasteableItems = clipboardItems.value.filter((i) => i.category !== category);
      contextMenu.x = event.clientX;
      contextMenu.y = event.clientY;
      contextMenu.targetCategory = category;
      contextMenu.targetEmoji = emoji;
      contextMenu.targetItems = targetItems;
      contextMenu.pasteableItems = pasteableItems;
      contextMenu.visible = true;
    };
    const closeContextMenu = () => {
      contextMenu.visible = false;
    };
    const contextMenuDelete = async () => {
      contextMenu.visible = false;
      const count = contextMenu.targetItems.length;
      if (count === 0) return;
      const confirmed = await confirm(
        "\u6279\u91CF\u5220\u9664\u8868\u60C5\u5305",
        `\u786E\u8BA4\u5220\u9664\u53F3\u952E\u9009\u4E2D\u7684 ${count} \u4E2A\u8868\u60C5\u5305\u5417\uFF1F\u6B64\u64CD\u4F5C\u4E0D\u53EF\u6062\u590D\u3002`,
        "\u786E\u8BA4\u5220\u9664",
        "danger"
      );
      if (!confirmed) return;
      const grouped = {};
      contextMenu.targetItems.forEach((item) => {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item.emoji);
      });
      let successCount = 0;
      for (const [cat, files] of Object.entries(grouped)) {
        try {
          const res = await fetch("/api/emoji/batch_delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: cat, image_files: files })
          });
          if (res.ok) {
            const data = await res.json();
            successCount += data.deleted_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }
      showToast(`\u6210\u529F\u5220\u9664\u4E86 ${successCount} \u4E2A\u8868\u60C5\u5305`, "success", "\u5220\u9664\u6210\u529F");
      contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
      await fetchEmojis();
    };
    const contextMenuMove = () => {
      contextMenu.visible = false;
      moveModal.visible = true;
    };
    const contextMenuCopy = () => {
      contextMenu.visible = false;
      clipboardItems.value = [...contextMenu.targetItems];
      showToast(`\u5DF2\u6210\u529F\u590D\u5236 ${clipboardItems.value.length} \u4E2A\u8868\u60C5\u5230\u526A\u8D34\u677F\uFF0C\u53EF\u5728\u5176\u4ED6\u6807\u7B7E\u53F3\u952E\u7C98\u8D34\u3002`, "success", "\u590D\u5236\u6210\u529F");
    };
    const contextMenuConvertToGif = async () => {
      contextMenu.visible = false;
      const count = contextMenu.targetItems.length;
      if (count === 0) return;
      const confirmed = await confirm(
        "\u8F6C\u6362\u4E3A GIF",
        `\u786E\u8BA4\u5C06\u9009\u4E2D\u7684 ${count} \u4E2A\u8868\u60C5\u5305\u8F6C\u6362\u4E3A GIF \u683C\u5F0F\u5417\uFF1F(\u79FB\u52A8\u7AEF QQ \u5BF9 WEBP \u52A8\u56FE\u652F\u6301\u4E0D\u4F73\uFF0C\u63A8\u8350\u8F6C\u6362)`,
        "\u786E\u8BA4\u8F6C\u6362",
        "primary"
      );
      if (!confirmed) return;
      const filenames = Array.from(new Set(contextMenu.targetItems.map((item) => item.emoji)));
      try {
        const res = await fetch("/api/emoji/batch_convert_gif", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames })
        });
        if (res.ok) {
          const result = await res.json();
          showToast(
            `\u6210\u529F\u8F6C\u6362 ${result.converted_count} \u4E2A\uFF0C\u8DF3\u8FC7 ${result.skipped_count} \u4E2A\uFF0C\u5931\u8D25 ${result.failed_count} \u4E2A\u3002`,
            "success",
            "\u8F6C\u6362\u5B8C\u6210"
          );
        } else {
          throw new Error("\u8F6C\u6362\u8BF7\u6C42\u5931\u8D25");
        }
      } catch (e) {
        showToast(e.message, "error", "\u8F6C\u6362\u5931\u8D25");
      }
      contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
      await fetchEmojis();
    };
    const contextMenuPaste = async () => {
      contextMenu.visible = false;
      const targetCategory = contextMenu.targetCategory;
      const pasteable = contextMenu.pasteableItems;
      if (pasteable.length === 0) return;
      const grouped = {};
      pasteable.forEach((item) => {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item.emoji);
      });
      let copiedCount = 0;
      for (const [sourceCat, files] of Object.entries(grouped)) {
        try {
          const res = await fetch("/api/emoji/batch_copy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              source_category: sourceCat,
              target_category: targetCategory,
              image_files: files
            })
          });
          if (res.ok) {
            const data = await res.json();
            copiedCount += data.copied_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }
      showToast(`\u6210\u529F\u5411\u6807\u7B7E ${targetCategory} \u590D\u5236\u7C98\u8D34\u4E86 ${copiedCount} \u4E2A\u8868\u60C5\u5305`, "success", "\u7C98\u8D34\u6210\u529F");
      clipboardItems.value = [];
      await fetchEmojis();
    };
    const onEmojiClick = (category, emoji) => {
      if (selectionEnabled.value) {
        const key = `${category}:${emoji}`;
        if (selectedEmojis.value.has(key)) {
          selectedEmojis.value.delete(key);
        } else {
          selectedEmojis.value.set(key, { category, emoji });
        }
      } else {
        toggleDetailDrawer(category, emoji);
      }
    };
    return {
      activeDetailEmoji,
      detailMetadata,
      selectedEmotions,
      selectedPersonas,
      detailDrawerLoading,
      uploadStateByCategory,
      contextMenu,
      clipboardItems,
      toggleDetailDrawer,
      closeDetailDrawer,
      toggleTagInDrawer,
      togglePersonaInDrawer,
      saveEmojiAttributes,
      deleteEmoji,
      batchDeleteSelected,
      batchConvertToGif,
      saveBatchPersonas,
      handleMoveTarget,
      clearAllEmojiFiles,
      submitImport,
      onDragStart,
      onDropEmoji,
      triggerFileInput,
      onFileSelected,
      onUploadDrop,
      openContextMenu,
      closeContextMenu,
      contextMenuDelete,
      contextMenuMove,
      contextMenuCopy,
      contextMenuConvertToGif,
      contextMenuPaste,
      onEmojiClick,
      handleCreateTagInDrawer,
      handleBackspace
    };
  }

  // script.js
  var { createApp, ref: ref8, computed: computed3, onMounted, onUnmounted } = Vue;
  createApp({
    setup() {
      const { toasts, showToast, removeToast } = useToasts();
      const modals = useModals(showToast);
      let pruneSelectionsRef = () => {
      };
      const api = useApi(showToast, () => pruneSelectionsRef());
      const selection = useSelection(api.emojiData, api.allEmojisList);
      pruneSelectionsRef = selection.pruneSelections;
      const sync = useSync(showToast, api.fetchEmojis);
      const categories = useCategories(
        showToast,
        api.fetchEmojis,
        sync.checkSyncStatus,
        modals.renameCategoryModal,
        modals.addCategoryForm,
        api.emojiData,
        api.activeCategories,
        modals.confirm,
        modals.showDangerConfirm
      );
      const emojiActions = useEmojiActions({
        showToast,
        fetchEmojis: api.fetchEmojis,
        activeCategories: api.activeCategories,
        selectionEnabled: selection.selectionEnabled,
        selectedEmojis: selection.selectedEmojis,
        systemPersonas: api.systemPersonas,
        emojiData: api.emojiData,
        allEmojisList: api.allEmojisList,
        getEmojiTags: api.getEmojiTags,
        confirm: modals.confirm,
        showDangerConfirm: modals.showDangerConfirm,
        moveModal: modals.moveModal,
        batchPersonaModal: modals.batchPersonaModal,
        importModal: modals.importModal,
        closeImportModal: modals.closeImportModal,
        drawerTagSearchQuery: api.drawerTagSearchQuery,
        selectedEmotions: api.selectedEmotions
      });
      const syncDrawerVisible = ref8(false);
      const isDrawerInputFocused = ref8(false);
      const getImageUrl = (emoji) => {
        if (!emoji) return "";
        return `/api/file/meme_manager/memes/file/${encodeURIComponent(emoji)}`;
      };
      const activeCategory = computed3(() => {
        if (api.activeCategories.value.includes("all")) return "all";
        if (api.activeCategories.value.length === 0) return "all";
        return api.activeCategories.value[0];
      });
      const activeCategoriesDisplayName = computed3(() => {
        if (api.activeCategories.value.includes("all") || api.activeCategories.value.length === 0) {
          return "\u5168\u90E8\u8868\u60C5";
        }
        return api.activeCategories.value.join(" & ");
      });
      const selectCategory = (category) => {
        if (category === "all") {
          api.activeCategories.value = ["all"];
        } else {
          const allIdx = api.activeCategories.value.indexOf("all");
          if (allIdx > -1) api.activeCategories.value.splice(allIdx, 1);
          const idx = api.activeCategories.value.indexOf(category);
          if (idx > -1) {
            api.activeCategories.value.splice(idx, 1);
          } else {
            api.activeCategories.value.push(category);
          }
          if (api.activeCategories.value.length === 0) {
            api.activeCategories.value = ["all"];
          }
        }
        api.visibleLimit.value = 40;
        emojiActions.closeDetailDrawer();
      };
      const sortedActiveEmojisList = computed3(() => {
        const list = [...api.activeCategoryEmojisList.value];
        list.sort((a, b) => {
          const ta = api.emojiMtimes.value[a] || 0;
          const tb = api.emojiMtimes.value[b] || 0;
          return tb - ta;
        });
        return list;
      });
      const currentEmojiIndex = computed3(() => {
        if (!emojiActions.activeDetailEmoji.value) return -1;
        return sortedActiveEmojisList.value.indexOf(emojiActions.activeDetailEmoji.value);
      });
      const hasPreviousEmoji = computed3(() => {
        return currentEmojiIndex.value > 0;
      });
      const hasNextEmoji = computed3(() => {
        const idx = currentEmojiIndex.value;
        return idx > -1 && idx < sortedActiveEmojisList.value.length - 1;
      });
      const navigateToSiblingEmoji = (direction) => {
        const idx = currentEmojiIndex.value;
        if (idx === -1) return;
        const targetIdx = idx + direction;
        if (targetIdx >= 0 && targetIdx < sortedActiveEmojisList.value.length) {
          const targetEmoji = sortedActiveEmojisList.value[targetIdx];
          emojiActions.toggleDetailDrawer(activeCategory.value, targetEmoji);
        }
      };
      const handleScroll = () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
          const total = api.activeEmojisCount.value;
          if (api.visibleLimit.value < total) {
            api.visibleLimit.value += 20;
          }
        }
      };
      onMounted(async () => {
        if (window.AstrBotPluginPage) {
          await window.AstrBotPluginPage.ready();
        }
        await api.fetchPersonaTags();
        await api.fetchEmojis();
        await api.fetchPersonas();
        void sync.checkSyncStatus(false);
        window.addEventListener("scroll", handleScroll);
      });
      onUnmounted(() => {
        window.removeEventListener("scroll", handleScroll);
      });
      return {
        // API States & Computed
        emojiData: api.emojiData,
        emojiMtimes: api.emojiMtimes,
        tagDescriptions: api.tagDescriptions,
        systemPersonas: api.systemPersonas,
        personaTags: api.personaTags,
        personaDedicatedTag: api.personaDedicatedTag,
        personaFilter: api.personaFilter,
        activeCategories: api.activeCategories,
        activeCategory,
        activeCategoriesDisplayName,
        activeCategoryEmojisList: api.activeCategoryEmojisList,
        activeEmojisCount: api.activeEmojisCount,
        tabSearchQuery: api.tabSearchQuery,
        drawerTagSearchQuery: api.drawerTagSearchQuery,
        fetchEmojis: api.fetchEmojis,
        fetchPersonas: api.fetchPersonas,
        fetchPersonaTags: api.fetchPersonaTags,
        savePersonaDedicatedTag: api.savePersonaDedicatedTag,
        filteredCategories: api.filteredCategories,
        filteredDrawerTags: api.filteredDrawerTags,
        emojiTagsMap: api.emojiTagsMap,
        allEmojisList: api.allEmojisList,
        importableEmojisList: api.importableEmojisList,
        activeCategoryTimeGroups: api.activeCategoryTimeGroups,
        getEmojiTags: api.getEmojiTags,
        visibleLimit: api.visibleLimit,
        // Toasts
        toasts,
        showToast,
        removeToast,
        // Selection
        selectedEmojis: selection.selectedEmojis,
        selectionEnabled: selection.selectionEnabled,
        pruneSelections: selection.pruneSelections,
        toggleSelectionMode: selection.toggleSelectionMode,
        isEmojiSelected: selection.isEmojiSelected,
        toggleEmojiSelection: selection.toggleEmojiSelection,
        getCategorySelectedCount: selection.getCategorySelectedCount,
        getVisibleSelectedCount: selection.getVisibleSelectedCount,
        isAllSelectedInCategory: selection.isAllSelectedInCategory,
        toggleCategorySelection: selection.toggleCategorySelection,
        // Modals
        confirmDialog: modals.confirmDialog,
        dangerConfirmDialog: modals.dangerConfirmDialog,
        moveModal: modals.moveModal,
        batchPersonaModal: modals.batchPersonaModal,
        addCategoryForm: modals.addCategoryForm,
        renameCategoryModal: modals.renameCategoryModal,
        importModal: modals.importModal,
        confirm: modals.confirm,
        handleConfirm: modals.handleConfirm,
        showDangerConfirm: modals.showDangerConfirm,
        startDangerCountdown: modals.startDangerCountdown,
        handleDangerConfirm: modals.handleDangerConfirm,
        cancelDangerConfirm: modals.cancelDangerConfirm,
        openBatchPersonaModal: modals.openBatchPersonaModal,
        closeBatchPersonaModal: modals.closeBatchPersonaModal,
        togglePersonaInBatch: modals.togglePersonaInBatch,
        openMoveModal: modals.openMoveModal,
        closeMoveModal: modals.closeMoveModal,
        openImportModal: modals.openImportModal,
        closeImportModal: modals.closeImportModal,
        toggleImportEmoji: modals.toggleImportEmoji,
        // UI States & Navigation
        syncDrawerVisible,
        selectCategory,
        hasPreviousEmoji,
        hasNextEmoji,
        navigateToSiblingEmoji,
        // Sync
        syncChecking: sync.syncChecking,
        syncStatus: sync.syncStatus,
        imgHostSyncing: sync.imgHostSyncing,
        imgHostStatus: sync.imgHostStatus,
        checkSyncStatus: sync.checkSyncStatus,
        syncConfig: sync.syncConfig,
        restoreCategory: sync.restoreCategory,
        removeFromConfig: sync.removeFromConfig,
        checkImgHostSyncStatus: sync.checkImgHostSyncStatus,
        syncToRemote: sync.syncToRemote,
        syncFromRemote: sync.syncFromRemote,
        // Categories
        openRenameCategory: categories.openRenameCategory,
        saveRenameCategory: categories.saveRenameCategory,
        saveNewCategory: categories.saveNewCategory,
        clearCategory: categories.clearCategory,
        deleteCategory: categories.deleteCategory,
        // Emoji Actions
        activeDetailEmoji: emojiActions.activeDetailEmoji,
        detailMetadata: emojiActions.detailMetadata,
        selectedEmotions: api.selectedEmotions,
        selectedPersonas: emojiActions.selectedPersonas,
        detailDrawerLoading: emojiActions.detailDrawerLoading,
        uploadStateByCategory: emojiActions.uploadStateByCategory,
        contextMenu: emojiActions.contextMenu,
        clipboardItems: emojiActions.clipboardItems,
        toggleDetailDrawer: emojiActions.toggleDetailDrawer,
        closeDetailDrawer: emojiActions.closeDetailDrawer,
        toggleTagInDrawer: emojiActions.toggleTagInDrawer,
        togglePersonaInDrawer: emojiActions.togglePersonaInDrawer,
        saveEmojiAttributes: emojiActions.saveEmojiAttributes,
        deleteEmoji: emojiActions.deleteEmoji,
        batchDeleteSelected: emojiActions.batchDeleteSelected,
        batchConvertToGif: emojiActions.batchConvertToGif,
        saveBatchPersonas: emojiActions.saveBatchPersonas,
        handleMoveTarget: emojiActions.handleMoveTarget,
        clearAllEmojiFiles: emojiActions.clearAllEmojiFiles,
        submitImport: emojiActions.submitImport,
        onDragStart: emojiActions.onDragStart,
        onDropEmoji: emojiActions.onDropEmoji,
        triggerFileInput: emojiActions.triggerFileInput,
        onFileSelected: emojiActions.onFileSelected,
        onUploadDrop: emojiActions.onUploadDrop,
        openContextMenu: emojiActions.openContextMenu,
        closeContextMenu: emojiActions.closeContextMenu,
        contextMenuDelete: emojiActions.contextMenuDelete,
        contextMenuMove: emojiActions.contextMenuMove,
        contextMenuCopy: emojiActions.contextMenuCopy,
        contextMenuConvertToGif: emojiActions.contextMenuConvertToGif,
        contextMenuPaste: emojiActions.contextMenuPaste,
        onEmojiClick: emojiActions.onEmojiClick,
        handleCreateTagInDrawer: emojiActions.handleCreateTagInDrawer,
        handleBackspace: emojiActions.handleBackspace,
        isDrawerInputFocused,
        getImageUrl
      };
    }
  }).mount("#app");
})();
