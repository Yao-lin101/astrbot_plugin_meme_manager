const { ref, reactive, nextTick } = window.Vue;

export function useModals(showToast) {
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

  const importModal = reactive({
    visible: false,
    selectedEmojis: new Set(),
  });

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
    toggleImportEmoji,
  };
}
