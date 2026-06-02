const { ref, reactive, nextTick, watch } = window.Vue;

export function useModals(showToast) {
  const confirmDialog = reactive({
    visible: false,
    title: "",
    description: "",
    confirmLabel: "确认",
    confirmClass: "",
    imageUrl: "",
    localImageUrl: "",
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

  const importModal = reactive({
    visible: false,
    selectedEmojis: new Set(),
  });

  const batchAnalyzeModal = reactive({
    visible: false,
    step: "config", // 'config' or 'progress'
    providers: [],
    selectedProvider: "",
    analyzeTags: true,
    analyzeDescription: true,
    passExistingTagsAsRef: false,
    promptTemplate: { intro: "", tags: "", desc: "" },
    promptContent: "",
    isPromptManuallyEdited: false,
    pollTimer: null,
    status: {
      status: "idle",
      total: 0,
      current_index: 0,
      current_file: "",
      results: []
    }
  });

  const updatePromptContent = () => {
    let parts = [];
    if (batchAnalyzeModal.promptTemplate.intro) {
      parts.push(batchAnalyzeModal.promptTemplate.intro);
    }
    if (batchAnalyzeModal.analyzeTags && batchAnalyzeModal.promptTemplate.tags) {
      parts.push(batchAnalyzeModal.promptTemplate.tags);
    }
    if (batchAnalyzeModal.analyzeDescription && batchAnalyzeModal.promptTemplate.desc) {
      parts.push(batchAnalyzeModal.promptTemplate.desc);
    }
    batchAnalyzeModal.promptContent = parts.join("\n\n");
    batchAnalyzeModal.isPromptManuallyEdited = false;
  };

  watch(
    () => [batchAnalyzeModal.analyzeTags, batchAnalyzeModal.analyzeDescription],
    () => {
      updatePromptContent();
      if (!(batchAnalyzeModal.analyzeDescription && !batchAnalyzeModal.analyzeTags)) {
        batchAnalyzeModal.passExistingTagsAsRef = false;
      }
    }
  );

  const confirm = (title, description, confirmLabel = "确认", confirmClass = "", imageUrl = "", localImageUrl = "") => {
    return new Promise((resolve) => {
      confirmDialog.title = title;
      confirmDialog.description = description;
      confirmDialog.confirmLabel = confirmLabel;
      confirmDialog.confirmClass = confirmClass;
      confirmDialog.imageUrl = imageUrl;
      confirmDialog.localImageUrl = localImageUrl;
      confirmDialog.resolve = resolve;
      confirmDialog.visible = true;
    });
  };

  const handleConfirm = (value) => {
    confirmDialog.visible = false;
    if (confirmDialog.resolve) confirmDialog.resolve(value);
    confirmDialog.imageUrl = "";
    confirmDialog.localImageUrl = "";
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
    importModal.selectedEmojis = new Set();
    importModal.visible = true;
  };

  const closeImportModal = () => {
    importModal.visible = false;
    importModal.selectedEmojis = new Set();
  };

  const toggleImportEmoji = (emoji) => {
    if (importModal.selectedEmojis.has(emoji)) {
      importModal.selectedEmojis.delete(emoji);
    } else {
      importModal.selectedEmojis.add(emoji);
    }
  };

  const openBatchAnalyzeModal = async () => {
    try {
      const res = await fetch("/api/providers");
      if (!res.ok) throw new Error("获取大模型提供商失败");
      batchAnalyzeModal.providers = await res.json();
    } catch (e) {
      console.error(e);
      showToast(e.message, "error", "获取供应商失败");
      return;
    }

    try {
      const statusRes = await fetch("/api/emoji/batch_analyze/status");
      if (statusRes.ok) {
        const currentStatus = await statusRes.json();
        batchAnalyzeModal.status = currentStatus;
        if (currentStatus.status === "running") {
          batchAnalyzeModal.step = "progress";
          batchAnalyzeModal.visible = true;
          startPollingBatchAnalyze();
          return;
        }
      }
    } catch (e) {
      console.error("检查批量分析状态失败", e);
    }

    batchAnalyzeModal.step = "config";
    batchAnalyzeModal.selectedProvider = "";
    batchAnalyzeModal.analyzeTags = true;
    batchAnalyzeModal.analyzeDescription = true;
    batchAnalyzeModal.passExistingTagsAsRef = false;
    batchAnalyzeModal.isPromptManuallyEdited = false;

    try {
      const templateRes = await fetch("/api/prompt/template");
      if (templateRes.ok) {
        batchAnalyzeModal.promptTemplate = await templateRes.json();
      } else {
        throw new Error("获取提示词模板失败");
      }
    } catch (e) {
      console.error("获取提示词模板失败", e);
      batchAnalyzeModal.promptTemplate = { intro: "", tags: "", desc: "" };
    }

    updatePromptContent();

    batchAnalyzeModal.visible = true;
  };

  const closeBatchAnalyzeModal = () => {
    stopPollingBatchAnalyze();
    batchAnalyzeModal.visible = false;
  };

  const startBatchAnalyze = async (selectedEmojisMap, fetchEmojis) => {
    const map = selectedEmojisMap && (selectedEmojisMap.value || selectedEmojisMap);
    if (!map || map.size === 0) {
      showToast("没有选中任何表情包", "warning", "未选择表情");
      return;
    }

    const filenames = Array.from(map.values()).map(item => item.emoji);

    try {
      const res = await fetch("/api/emoji/batch_analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filenames: filenames,
          provider_id: batchAnalyzeModal.selectedProvider,
          analyze_tags: batchAnalyzeModal.analyzeTags,
          analyze_description: batchAnalyzeModal.analyzeDescription,
          pass_existing_tags_as_ref: batchAnalyzeModal.passExistingTagsAsRef,
          prompt_content: batchAnalyzeModal.promptContent
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.message || "启动重新分析失败");
      }

      showToast("批量重新分析任务已启动", "success", "启动成功");
      batchAnalyzeModal.step = "progress";
      
      await updateBatchAnalyzeStatus(fetchEmojis);
      startPollingBatchAnalyze(fetchEmojis);
    } catch (e) {
      showToast(e.message, "error", "启动失败");
    }
  };

  const cancelBatchAnalyze = async () => {
    try {
      const res = await fetch("/api/emoji/batch_analyze/cancel", {
        method: "POST"
      });
      if (!res.ok) throw new Error("取消批量分析失败");
      showToast("正在发送取消信号...", "info", "取消分析");
    } catch (e) {
      showToast(e.message, "error", "取消失败");
    }
  };

  const updateBatchAnalyzeStatus = async (fetchEmojis) => {
    try {
      const res = await fetch("/api/emoji/batch_analyze/status");
      if (!res.ok) throw new Error("获取状态失败");
      const currentStatus = await res.json();
      batchAnalyzeModal.status = currentStatus;

      if (currentStatus.status === "completed" || currentStatus.status === "idle") {
        stopPollingBatchAnalyze();
        if (fetchEmojis) {
          await fetchEmojis();
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const startPollingBatchAnalyze = (fetchEmojis) => {
    if (batchAnalyzeModal.pollTimer) clearInterval(batchAnalyzeModal.pollTimer);
    batchAnalyzeModal.pollTimer = setInterval(() => {
      void updateBatchAnalyzeStatus(fetchEmojis);
    }, 1000);
  };

  const stopPollingBatchAnalyze = () => {
    if (batchAnalyzeModal.pollTimer) {
      clearInterval(batchAnalyzeModal.pollTimer);
      batchAnalyzeModal.pollTimer = null;
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
    batchAnalyzeModal,
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
    toggleImportEmoji,
    openBatchAnalyzeModal,
    closeBatchAnalyzeModal,
    startBatchAnalyze,
    cancelBatchAnalyze,
  };
}
