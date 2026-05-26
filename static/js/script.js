// script.js - Unified Vue 3 Application for AstrBot Meme Manager WebUI
const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;

createApp({
  setup() {
    // ----------------------------------------------------
    // State variables
    // ----------------------------------------------------
    const emojiData = ref({});
    const tagDescriptions = ref({});
    const systemPersonas = ref([]);

    // UI States
    const activeCategory = ref(null);
    const activeDetailEmoji = ref(null);
    const personaFilter = ref("");
    const toasts = ref([]);
    const syncDrawerVisible = ref(false);
    let toastIdCounter = 0;

    // Properties Editor (Inline Grid Drawer)
    const detailMetadata = ref(null);
    const selectedEmotions = ref([]);
    const selectedPersonas = ref([]);
    const detailDrawerLoading = ref(false);

    // Upload state tracking
    const uploadStateByCategory = ref(new Map());

    // Batch Selection Mode
    const selectionEnabled = ref(false);
    const selectedEmojis = ref(new Map()); // Key: 'category:emoji' -> { category, emoji }

    // Context Menu State (right click / long press)
    const contextMenu = reactive({
      visible: false,
      x: 0,
      y: 0,
      targetCategory: null,
      targetEmoji: null,
      targetItems: [],
      pasteableItems: [],
    });

    // Clipboard (for Copy / Paste)
    const clipboardItems = ref([]);

    // Modals
    const confirmDialog = reactive({
      visible: false,
      title: "",
      description: "",
      confirmLabel: "确认",
      confirmClass: "",
      resolve: null,
    });

    const dangerConfirmDialog = reactive({
      visible: false,
      title: "",
      description: "",
      actionLabel: "确认",
      countdown: 0,
      stage: "ack", // 'ack', 'countdown', 'input'
      timer: null,
      resolve: null,
    });

    const moveModal = reactive({
      visible: false,
      resolve: null,
    });

    const batchPersonaModal = reactive({
      visible: false,
      personas: [],
    });

    const addCategoryForm = reactive({
      visible: false,
      name: "",
    });

    const renameCategoryModal = reactive({
      visible: false,
      category: "",
      originalCategory: "",
    });

    // Sync state tracking
    const syncChecking = ref(false);
    const syncStatus = ref({
      inSync: true,
      missingInConfig: [],
      deletedCategories: [],
    });

    const imgHostSyncing = ref(false);
    const imgHostStatus = ref({
      provider: "--",
      remoteImageCount: "--",
      remoteStorageSize: "--",
      uploadCount: 0,
      downloadCount: 0,
    });

    // ----------------------------------------------------
    // Toast Notification helper
    // ----------------------------------------------------
    const showToast = (message, type = "info", title = "系统提示", duration = 3000) => {
      const id = toastIdCounter++;
      toasts.value.push({ id, message, type, title });
      setTimeout(() => {
        removeToast(id);
      }, duration);
    };

    const removeToast = (id) => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    };

    // ----------------------------------------------------
    // Utilities
    // ----------------------------------------------------
    const formatBytes = (bytes) => {
      if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes < 0) return "未知";
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

    // ----------------------------------------------------
    // API Data Fetching
    // ----------------------------------------------------
    const fetchEmojis = async () => {
      try {
        const personaId = personaFilter.value;
        const url = personaId ? `/api/emoji?persona_id=${encodeURIComponent(personaId)}` : "/api/emoji";
        
        const [emojiRes, tagRes] = await Promise.all([
          fetch(url).then(res => {
            if (!res.ok) throw new Error("获取表情包数据失败");
            return res.json();
          }),
          fetch("/api/emotions").then(res => {
            if (!res.ok) throw new Error("获取类别描述失败");
            return res.json();
          })
        ]);

        emojiData.value = emojiRes;
        tagDescriptions.value = tagRes;

        // Clean up selections of items that no longer exist
        pruneSelections();

        // Default to 'all' if activeCategory is unset or missing
        const categories = Object.keys(emojiRes);
        if (categories.length > 0) {
          if (!activeCategory.value || (!emojiRes[activeCategory.value] && activeCategory.value !== 'all')) {
            activeCategory.value = 'all';
          }
        } else {
          activeCategory.value = null;
        }
      } catch (e) {
        console.error(e);
        showToast(e.message, "error", "加载数据失败");
      }
    };

    const fetchPersonas = async () => {
      try {
        const res = await fetch("/api/personas");
        if (!res.ok) throw new Error("获取系统人格失败");
        systemPersonas.value = await res.json();
      } catch (e) {
        console.error(e);
      }
    };

    const pruneSelections = () => {
      for (const [key, item] of selectedEmojis.value.entries()) {
        const list = emojiData.value[item.category];
        if (!list || !list.includes(item.emoji)) {
          selectedEmojis.value.delete(key);
        }
      }
    };

    // ----------------------------------------------------
    // Tab & Navigation Handling
    // ----------------------------------------------------
    const selectCategory = (category) => {
      activeCategory.value = category;
      closeDetailDrawer();
    };

    // ----------------------------------------------------
    // Multi-tag Emoji mapping computed
    // ----------------------------------------------------
    const emojiTagsMap = computed(() => {
      const map = new Map();
      Object.entries(emojiData.value).forEach(([cat, emos]) => {
        if (Array.isArray(emos)) {
          emos.forEach((emo) => {
            if (!map.has(emo)) map.set(emo, new Set());
            map.get(emo).add(cat);
          });
        }
      });
      return map;
    });

    const allEmojisList = computed(() => {
      const allSet = new Set();
      Object.values(emojiData.value).forEach((list) => {
        if (Array.isArray(list)) {
          list.forEach((emoji) => allSet.add(emoji));
        }
      });
      return Array.from(allSet).sort();
    });

    const getEmojiTags = (emoji) => {
      const tags = emojiTagsMap.value.get(emoji);
      return tags ? Array.from(tags).sort() : [];
    };

    // ----------------------------------------------------
    // Inline Properties Drawer (Detail Drawer)
    // ----------------------------------------------------
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
        if (!res.ok) throw new Error("获取属性失败");
        const metadata = await res.json();

        // Check if user switched to another emoji during load
        if (activeDetailEmoji.value !== emoji) return;

        detailMetadata.value = metadata;
        selectedEmotions.value = metadata.emotions || [];
        selectedPersonas.value = metadata.personas || [];
      } catch (e) {
        showToast(e.message, "error", "加载表情属性失败");
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
        // Clear global if selected specific
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

    const saveEmojiAttributes = async () => {
      if (selectedEmotions.value.length === 0) {
        showToast("请至少选择一个分类标签。", "warning", "保存提示");
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
            personas: personas,
          }),
        });
        if (!res.ok) throw new Error("保存属性失败");

        showToast("属性保存成功！", "success", "修改成功");
        closeDetailDrawer();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "保存失败");
      }
    };

    // ----------------------------------------------------
    // Actions - Delete Emoji
    // ----------------------------------------------------
    const deleteEmoji = async (category, emoji) => {
      const confirmed = await confirm(
        "删除标签 / 文件",
        `确认从分类「${category}」下移除表情包？若该表情包不属于其他任何分类，它将被物理删除。`,
        "确认删除",
        "danger"
      );
      if (!confirmed) return;

      try {
        const res = await fetch("/api/emoji/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, image_file: emoji }),
        });
        if (!res.ok) throw new Error("删除失败");

        selectedEmojis.value.delete(`${category}:${emoji}`);
        showToast("表情包已成功删除", "success", "删除成功");
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "删除失败");
      }
    };

    // ----------------------------------------------------
    // Modals & Overlays handlers (Confirm / Dialogs)
    // ----------------------------------------------------
    const confirm = (title, description, confirmLabel = "确认", confirmClass = "") => {
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

    const showDangerConfirm = (title, description, actionLabel = "确认操作") => {
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
      }, 1000);
    };

    const handleDangerConfirm = () => {
      const input = document.getElementById("danger-modal-ack");
      if (input && input.value.trim() === "CONFIRM") {
        dangerConfirmDialog.visible = false;
        if (dangerConfirmDialog.resolve) dangerConfirmDialog.resolve(true);
      } else {
        showToast("请输入大写的 CONFIRM 确认此操作！", "warning", "输入错误");
      }
    };

    const cancelDangerConfirm = () => {
      if (dangerConfirmDialog.timer) {
        clearInterval(dangerConfirmDialog.timer);
      }
      dangerConfirmDialog.visible = false;
      if (dangerConfirmDialog.resolve) dangerConfirmDialog.resolve(false);
    };

    // ----------------------------------------------------
    // Batch Selection Operations
    // ----------------------------------------------------
    const toggleSelectionMode = () => {
      selectionEnabled.value = !selectionEnabled.value;
      if (!selectionEnabled.value) {
        selectedEmojis.value.clear();
      }
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

    const onEmojiClick = (category, emoji) => {
      if (selectionEnabled.value) {
        toggleEmojiSelection(category, emoji);
      } else {
        toggleDetailDrawer(category, emoji);
      }
    };

    const getCategorySelectedCount = (category) => {
      let count = 0;
      for (const item of selectedEmojis.value.values()) {
        if (item.category === category) count++;
      }
      return count;
    };

    const isAllSelectedInCategory = (category) => {
      const list = category === 'all' ? allEmojisList.value : (emojiData.value[category] || []);
      if (list.length === 0) return false;
      return list.every((emoji) => isEmojiSelected(category, emoji));
    };

    const toggleCategorySelection = (category) => {
      if (!selectionEnabled.value) {
        selectionEnabled.value = true;
      }
      const list = category === 'all' ? allEmojisList.value : (emojiData.value[category] || []);
      if (isAllSelectedInCategory(category)) {
        list.forEach((emoji) => {
          selectedEmojis.value.delete(`${category}:${emoji}`);
        });
      } else {
        list.forEach((emoji) => {
          selectedEmojis.value.set(`${category}:${emoji}`, { category, emoji });
        });
      }
    };

    // ----------------------------------------------------
    // Actions - Batch Actions
    // ----------------------------------------------------
    const batchDeleteSelected = async () => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;

      const confirmed = await confirm(
        "批量删除表情包",
        `确认删除已选中的 ${items.length} 个表情包？这会移除其分类标签，若该表情包不属于其他任何分类，它将被物理删除。`,
        "确认批量删除",
        "danger"
      );
      if (!confirmed) return;

      // Group by category to hit Quart batch delete endpoint
      const grouped = {};
      items.forEach((item) => {
        const cats = item.category === 'all' ? getEmojiTags(item.emoji) : [item.category];
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
            body: JSON.stringify({ category: cat, image_files: files }),
          });
          if (res.ok) {
            const result = await res.json();
            successCount += result.deleted_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }

      showToast(`已成功批量删除 ${successCount} 个表情包。`, "success", "批量删除完成");
      selectedEmojis.value.clear();
      await fetchEmojis();
    };

    const batchConvertToGif = async () => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;

      const confirmed = await confirm(
        "转换为 GIF",
        `确认将选中的 ${items.length} 个表情包转换为 GIF 格式吗？(移动端 QQ 对 WEBP 动图支持不佳，推荐转换)`,
        "确认转换",
        "primary"
      );
      if (!confirmed) return;

      const filenames = Array.from(new Set(items.map(item => item.emoji)));
      
      try {
        const res = await fetch("/api/emoji/batch_convert_gif", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames }),
        });
        if (res.ok) {
          const result = await res.json();
          showToast(
            `成功转换 ${result.converted_count} 个，跳过 ${result.skipped_count} 个，失败 ${result.failed_count} 个。`,
            "success",
            "转换完成"
          );
        } else {
          throw new Error("转换请求失败");
        }
      } catch (e) {
        showToast(e.message, "error", "转换失败");
      }

      selectedEmojis.value.clear();
      await fetchEmojis();
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
            filenames: filenames,
            personas: personas,
          }),
        });
        if (!res.ok) throw new Error("批量更新人格限制失败");

        showToast("批量设置人格限制成功！", "success", "修改成功");
        closeBatchPersonaModal();
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "批量设置失败");
      }
    };

    const openMoveModal = () => {
      moveModal.visible = true;
    };

    const closeMoveModal = () => {
      moveModal.visible = false;
    };

    const handleMoveTarget = async (targetCategory) => {
      const items = Array.from(selectedEmojis.value.values());
      if (items.length === 0) return;

      // Group by source category
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
              image_files: files,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            movedCount += data.moved_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }

      showToast(`已成功将 ${movedCount} 个表情包移动到 ${targetCategory}`, "success", "移动成功");
      closeMoveModal();
      selectedEmojis.value.clear();
      await fetchEmojis();
    };

    const clearAllEmojiFiles = async () => {
      const totalCount = Object.values(emojiData.value).reduce((sum, list) => sum + (list?.length || 0), 0);
      if (totalCount === 0) {
        showToast("库中没有任何表情包可以清空", "warning");
        return;
      }

      const confirmed = await showDangerConfirm(
        "清空所有表情包",
        `确认彻底清空库中的所有 ${totalCount} 个表情包？此操作将删除所有磁盘文件，但保留分类目录配置。`
      );
      if (!confirmed) return;

      try {
        const res = await fetch("/api/emoji/clear_all", { method: "POST" });
        if (!res.ok) throw new Error("清空失败");
        const data = await res.json();

        showToast(`已清空全部表情包，共删除 ${data.deleted_count} 个文件。`, "success", "清空成功");
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "清空失败");
      }
    };

    // ----------------------------------------------------
    // Actions - Categories Management
    // ----------------------------------------------------
    const openRenameCategory = (category) => {
      renameCategoryModal.category = category;
      renameCategoryModal.originalCategory = category;
      renameCategoryModal.visible = true;
    };

    const saveRenameCategory = async () => {
      const oldName = renameCategoryModal.originalCategory;
      const newName = renameCategoryModal.category.trim();
      if (!newName) {
        showToast("标签名称不能为空", "warning");
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
            new_name: newName,
          }),
        });
        if (!res.ok) throw new Error("重命名类别失败");

        showToast(`标签已成功从「${oldName}」重命名为「${newName}」。`, "success", "重命名成功");
        renameCategoryModal.visible = false;
        if (activeCategory.value === oldName) {
          activeCategory.value = newName;
        }
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "重命名失败");
      }
    };

    const saveNewCategory = async () => {
      const name = addCategoryForm.name.trim();

      if (!name) {
        showToast("请输入分类名称再保存", "warning");
        return;
      }

      try {
        const res = await fetch("/api/category/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: name }),
        });
        if (!res.ok) throw new Error("添加分类失败");

        showToast(`新分类「${name}」添加成功。`, "success", "保存成功");
        addCategoryForm.name = "";
        addCategoryForm.visible = false;
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "添加失败");
      }
    };

    const clearCategory = async (category) => {
      const count = emojiData.value[category]?.length || 0;
      if (count === 0) {
        showToast("该类别当前为空，无需清空", "info");
        return;
      }

      const confirmed = await showDangerConfirm(
        `清空分类「${category}」`,
        `确定要删除分类「${category}」下的全部 ${count} 个表情文件吗？保留分类名称和描述。`
      );
      if (!confirmed) return;

      try {
        const res = await fetch("/api/category/clear", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category }),
        });
        if (!res.ok) throw new Error("清空失败");
        const data = await res.json();

        showToast(`已清空分类 ${category}，删除了 ${data.deleted_count} 个表情包。`, "success", "清空成功");
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "清空失败");
      }
    };

    const deleteCategory = async (category) => {
      const count = emojiData.value[category]?.length || 0;
      const confirmed = await showDangerConfirm(
        `删除分类「${category}」`,
        `确认删除分类「${category}」吗？此操作将清除该分类的所有表情包分类标签，若表情包不属于其他任何分类，对应的磁盘文件将被物理删除。`
      );
      if (!confirmed) return;

      try {
        const res = await fetch("/api/category/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category }),
        });
        if (!res.ok) throw new Error("删除失败");

        showToast(`已成功删除分类 ${category}`, "success", "删除成功");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "删除失败");
      }
    };

    // ----------------------------------------------------
    // Drag & Drop (HTML5 standard API)
    // ----------------------------------------------------
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
            image_files: items.map((i) => i.emoji),
          }),
        });
        if (!res.ok) throw new Error("移动失败");
        const result = await res.json();

        showToast(`成功将 ${result.moved_count} 个表情包移动到分类 ${targetCategory}`, "success", "移动成功");
        selectedEmojis.value.clear();
        await fetchEmojis();
      } catch (e) {
        showToast(e.message, "error", "移动失败");
      }
    };

    // ----------------------------------------------------
    // File Upload Drag & Drop & Upload Progress
    // ----------------------------------------------------
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
        showToast(`当前分类 ${category} 正在上传中，请稍候。`, "warning");
        return;
      }

      const total = files.length;
      uploadStateByCategory.value.set(category, { progress: 0, text: `准备上传 0/${total}` });

      let completed = 0;
      let failed = 0;
      let dups = 0;

      for (let i = 0; i < total; i++) {
        const file = files[i];
        uploadStateByCategory.value.set(category, {
          progress: Math.round((i / total) * 100),
          text: `上传中: ${i + 1}/${total} (${file.name})`,
        });

        const formData = new FormData();
        formData.append("category", category);
        formData.append("image_file", file);

        try {
          const res = await fetch("/api/emoji/add", {
            method: "POST",
            body: formData,
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
        `上传完成！成功 ${completed} 个` +
          (dups > 0 ? `，重复跳过 ${dups} 个` : "") +
          (failed > 0 ? `，失败 ${failed} 个` : ""),
        failed > 0 ? "warning" : "success",
        "上传完毕"
      );
      await fetchEmojis();
    };

    // ----------------------------------------------------
    // Context Menu Handling
    // ----------------------------------------------------
    const openContextMenu = (event, category, emoji) => {
      const key = `${category}:${emoji}`;
      let targetItems = [];
      if (selectionEnabled.value && selectedEmojis.value.has(key)) {
        targetItems = Array.from(selectedEmojis.value.values());
      } else {
        targetItems = [{ category, emoji }];
      }

      // Check pasteable items in clipboard
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
        "批量删除表情包",
        `确认删除右键选中的 ${count} 个表情包吗？此操作不可恢复。`,
        "确认删除",
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
            body: JSON.stringify({ category: cat, image_files: files }),
          });
          if (res.ok) {
            const data = await res.json();
            successCount += data.deleted_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }

      showToast(`成功删除了 ${successCount} 个表情包`, "success", "删除成功");
      // Prune select items
      contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
      await fetchEmojis();
    };

    const contextMenuMove = () => {
      contextMenu.visible = false;
      openMoveModal();
    };

    const contextMenuCopy = () => {
      contextMenu.visible = false;
      clipboardItems.value = [...contextMenu.targetItems];
      showToast(`已成功复制 ${clipboardItems.value.length} 个表情到剪贴板，可在其他分类右键粘贴。`, "success", "复制成功");
    };

    const contextMenuConvertToGif = async () => {
      contextMenu.visible = false;
      const count = contextMenu.targetItems.length;
      if (count === 0) return;

      const confirmed = await confirm(
        "转换为 GIF",
        `确认将选中的 ${count} 个表情包转换为 GIF 格式吗？(移动端 QQ 对 WEBP 动图支持不佳，推荐转换)`,
        "确认转换",
        "primary"
      );
      if (!confirmed) return;

      const filenames = Array.from(new Set(contextMenu.targetItems.map(item => item.emoji)));
      
      try {
        const res = await fetch("/api/emoji/batch_convert_gif", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames }),
        });
        if (res.ok) {
          const result = await res.json();
          showToast(
            `成功转换 ${result.converted_count} 个，跳过 ${result.skipped_count} 个，失败 ${result.failed_count} 个。`,
            "success",
            "转换完成"
          );
        } else {
          throw new Error("转换请求失败");
        }
      } catch (e) {
        showToast(e.message, "error", "转换失败");
      }

      // Clear selection if those items were in selectedEmojis
      contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
      await fetchEmojis();
    };

    const contextMenuPaste = async () => {
      contextMenu.visible = false;
      const targetCategory = contextMenu.targetCategory;
      const pasteable = contextMenu.pasteableItems;
      if (pasteable.length === 0) return;

      // Group by source category
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
              image_files: files,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            copiedCount += data.copied_count || 0;
          }
        } catch (e) {
          console.error(e);
        }
      }

      showToast(`成功向分类 ${targetCategory} 复制粘贴了 ${copiedCount} 个表情包`, "success", "粘贴成功");
      clipboardItems.value = [];
      await fetchEmojis();
    };

    // ----------------------------------------------------
    // Sync status & Operations
    // ----------------------------------------------------
    const checkSyncStatus = async (showAlert = true) => {
      syncChecking.value = true;
      try {
        const res = await fetch("/api/sync/status");
        if (!res.ok) throw new Error("获取状态失败");
        const data = await res.json();

        if (data.status === "error") throw new Error(data.message);

        // Normalize differences
        const diffs = data.differences || data;
        syncStatus.value.missingInConfig = diffs.missing_in_config || [];
        syncStatus.value.deletedCategories = diffs.deleted_categories || [];
        syncStatus.value.inSync =
          syncStatus.value.missingInConfig.length === 0 && syncStatus.value.deletedCategories.length === 0;

        if (showAlert) {
          showToast("配置同步状态检查完毕。", "success", "刷新成功");
        }
      } catch (e) {
        showToast(e.message, "error", "同步检查失败");
      } finally {
        syncChecking.value = false;
      }
    };

    const syncConfig = async () => {
      try {
        const res = await fetch("/api/sync/config", { method: "POST" });
        if (!res.ok) throw new Error("同步失败");
        showToast("已成功将磁盘文件夹同步至系统配置", "success", "配置同步完成");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "同步失败");
      }
    };

    const restoreCategory = async (category) => {
      try {
        const res = await fetch("/api/category/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, description: "请添加描述" }),
        });
        if (!res.ok) throw new Error("恢复分类文件夹失败");
        showToast(`分类「${category}」对应文件夹已成功重建。`, "success", "恢复成功");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "恢复失败");
      }
    };

    const removeFromConfig = async (category) => {
      try {
        const res = await fetch("/api/category/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category }),
        });
        if (!res.ok) throw new Error("移除配置失败");
        showToast(`已从配置中移除类别 「${category}」`, "success", "移除成功");
        await fetchEmojis();
        await checkSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "删除配置失败");
      }
    };

    // ----------------------------------------------------
    // Cloud & Image Host Synchronization
    // ----------------------------------------------------
    const checkImgHostSyncStatus = async (showAlert = true) => {
      try {
        const res = await fetch("/api/img_host/sync/status");
        if (!res.ok) throw new Error("获取图床状态失败");
        const data = await res.json();

        const uploadCount = data.upload_count ?? data.to_upload?.length ?? 0;
        const downloadCount = data.download_count ?? data.to_download?.length ?? 0;
        const remoteImageCount = data.remote_image_count ?? data.remote_count ?? data.remote_images?.length ?? 0;
        
        let remoteStorageText = "未知";
        if (typeof data.remote_total_bytes === "number") {
          remoteStorageText = formatBytes(data.remote_total_bytes);
        } else if (typeof data.remote_total_bytes_estimated === "number") {
          remoteStorageText = `${formatBytes(data.remote_total_bytes_estimated)}（估算）`;
        }

        imgHostStatus.value.provider = data.provider_label || "未知图床";
        imgHostStatus.value.remoteImageCount = remoteImageCount;
        imgHostStatus.value.remoteStorageSize = remoteStorageText;
        imgHostStatus.value.uploadCount = uploadCount;
        imgHostStatus.value.downloadCount = downloadCount;

        if (showAlert) {
          showToast(
            `${data.provider_label || "图床"}已刷新。云端：${remoteImageCount} 张，待上传：${uploadCount} 个。`,
            "success",
            "刷新成功"
          );
        }
      } catch (e) {
        showToast(e.message, "error", "图床同步检查失败");
      }
    };

    const syncToRemote = async () => {
      imgHostSyncing.value = true;
      showToast("正在将待上传文件同步至云端图床...", "info", "上传同步中", 5000);
      try {
        const res = await fetch("/api/img_host/sync/upload", { method: "POST" });
        if (!res.ok) throw new Error("上传同步失败");
        showToast("本地表情包成功全量同步至云端图床", "success", "同步成功");
        await checkImgHostSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "同步失败");
      } finally {
        imgHostSyncing.value = false;
      }
    };

    const syncFromRemote = async () => {
      imgHostSyncing.value = true;
      showToast("正在从云端下载同步表情包...", "info", "下载同步中", 5000);
      try {
        const res = await fetch("/api/img_host/sync/download", { method: "POST" });
        if (!res.ok) throw new Error("下载同步失败");
        showToast("云端图床成功全量拉取同步至本地", "success", "同步成功");
        await fetchEmojis();
        await checkImgHostSyncStatus(false);
      } catch (e) {
        showToast(e.message, "error", "同步失败");
      } finally {
        imgHostSyncing.value = false;
      }
    };

    // ----------------------------------------------------
    // Lifecycle hooks
    // ----------------------------------------------------
    onMounted(async () => {
      await fetchEmojis();
      await fetchPersonas();
      void checkSyncStatus(false);
    });

    return {
      emojiData,
      tagDescriptions,
      systemPersonas,
      activeCategory,
      allEmojisList,
      activeDetailEmoji,
      personaFilter,
      toasts,
      syncDrawerVisible,
      detailMetadata,
      selectedEmotions,
      selectedPersonas,
      detailDrawerLoading,
      uploadStateByCategory,
      selectionEnabled,
      selectedEmojis,
      contextMenu,
      clipboardItems,
      confirmDialog,
      dangerConfirmDialog,
      moveModal,
      batchPersonaModal,
      addCategoryForm,
      renameCategoryModal,
      syncChecking,
      syncStatus,
      imgHostSyncing,
      imgHostStatus,
      showToast,
      removeToast,
      fetchEmojis,
      selectCategory,
      getEmojiTags,
      toggleDetailDrawer,
      closeDetailDrawer,
      toggleTagInDrawer,
      togglePersonaInDrawer,
      saveEmojiAttributes,
      deleteEmoji,
      handleConfirm,
      startDangerCountdown,
      handleDangerConfirm,
      cancelDangerConfirm,
      toggleSelectionMode,
      isEmojiSelected,
      toggleEmojiSelection,
      onEmojiClick,
      getCategorySelectedCount,
      isAllSelectedInCategory,
      toggleCategorySelection,
      batchDeleteSelected,
      openBatchPersonaModal,
      closeBatchPersonaModal,
      togglePersonaInBatch,
      saveBatchPersonas,
      openMoveModal,
      closeMoveModal,
      handleMoveTarget,
      clearAllEmojiFiles,
      openRenameCategory,
      saveRenameCategory,
      saveNewCategory,
      clearCategory,
      deleteCategory,
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
      contextMenuPaste,
      batchConvertToGif,
      contextMenuConvertToGif,
      checkSyncStatus,
      checkImgHostSyncStatus,
      syncConfig,
      restoreCategory,
      removeFromConfig,
      syncToRemote,
      syncFromRemote,
    };
  },
}).mount("#app");
