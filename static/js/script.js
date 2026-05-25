// script.js - Entry point for the Meme Manager WebUI. Initializes modules and registers global events.

import { state } from "./modules/state.js";
import {
  elements,
  MOBILE_LAYOUT_MEDIA,
  LONG_PRESS_CANCEL_DISTANCE_PX,
  showToast,
  closeConfirm,
  closeDangerConfirm,
  startDangerCountdown,
  closeMoveTargetModal,
  openMoveTargetModal,
  closeCategoryEditModal,
  editCategory,
  cancelEdit,
  saveCategory,
  closeEmojiEditModal,
  openEmojiEditModal,
  syncSidebarLayout,
  updateSidebarToggleState,
  toggleSidebar,
  closeSidebar,
} from "./modules/ui.js";
import {
  fetchEmojis,
  fetchPersonas,
  checkSyncStatus,
  checkImgHostSyncStatus,
  syncToRemote,
  syncFromRemote,
  syncConfig,
  restoreCategory,
  removeFromConfig,
  clearCategory,
  deleteCategory,
  cancelAllPendingRequests,
} from "./modules/api.js";
import {
  clearDragMode,
  closeBatchContextMenu,
  shouldOpenBatchContextMenu,
  openBatchContextMenu,
  hasActiveDragInteraction,
  finishLongPress,
  finishPointerDrag,
  updatePointerDrag,
  cancelLongPress,
  setSelectionMode,
  batchDeleteSelected,
  clearAllEmojiFiles,
  getClipboardItems,
  copyEmojiItemsToCategory,
  copyItemsToClipboard,
} from "./modules/interactions.js";

document.addEventListener("DOMContentLoaded", () => {
  // Bind category add form toggling
  const addCategoryBtn = document.getElementById("add-category-btn");
  if (addCategoryBtn) {
    addCategoryBtn.addEventListener("click", function () {
      const form = document.getElementById("add-category-form");
      if (form) form.style.display = "block";
      this.style.display = "none";
    });
  }

  // Bind category save button
  const saveCategoryBtn = document.getElementById("save-category-btn");
  if (saveCategoryBtn) {
    saveCategoryBtn.addEventListener("click", async function () {
      const categoryName = document.getElementById("new-category-name")?.value.trim();
      const categoryDesc = document.getElementById("new-category-description")?.value.trim() || "请添加描述";

      if (!categoryName) {
        showToast("请输入类别名称后再保存。", "warning", "缺少类别名称");
        return;
      }

      const saveButton = this;
      const { setButtonBusy, restoreButton, refreshUi } = await import("./modules/ui.js");
      const { requestJson } = await import("./modules/api.js");
      setButtonBusy(saveButton, "保存中...");

      try {
        await requestJson(
          "/api/category/restore",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              category: categoryName,
              description: categoryDesc,
            }),
          },
          { defaultErrorMessage: "添加类别失败" }
        );

        const newNameEl = document.getElementById("new-category-name");
        const newDescEl = document.getElementById("new-category-description");
        if (newNameEl) newNameEl.value = "";
        if (newDescEl) newDescEl.value = "";

        const form = document.getElementById("add-category-form");
        if (form) form.style.display = "none";
        if (addCategoryBtn) addCategoryBtn.style.display = "block";

        await fetchEmojis();
        await checkSyncStatus(false);
        showToast(`类别「${categoryName}」已添加。`, "success", "添加成功");
      } catch (error) {
        console.error("添加类别失败:", error);
        showToast(error.message, "error", "添加失败");
      } finally {
        restoreButton(saveButton);
      }
    });
  }

  // Bind Sync buttons
  const checkSyncBtn = document.getElementById("check-sync-btn");
  if (checkSyncBtn) {
    checkSyncBtn.addEventListener("click", () => checkSyncStatus());
  }

  const uploadSyncBtn = document.getElementById("upload-sync-btn");
  if (uploadSyncBtn) {
    uploadSyncBtn.addEventListener("click", () => syncToRemote());
  }

  const downloadSyncBtn = document.getElementById("download-sync-btn");
  if (downloadSyncBtn) {
    downloadSyncBtn.addEventListener("click", () => syncFromRemote());
  }

  // Bind batch actions
  const toggleSelectionModeBtn = elements.toggleSelectionModeBtn;
  if (toggleSelectionModeBtn) {
    toggleSelectionModeBtn.addEventListener("click", () => {
      setSelectionMode(!state.selectionState.enabled);
    });
  }

  const batchDeleteBtn = elements.batchDeleteBtn;
  if (batchDeleteBtn) {
    batchDeleteBtn.addEventListener("click", batchDeleteSelected);
  }

  const batchMoveBtn = elements.batchMoveBtn;
  if (batchMoveBtn) {
    batchMoveBtn.addEventListener("click", () => {
      openMoveTargetModal(Array.from(state.selectionState.items.values()));
    });
  }

  const clearAllBtn = elements.clearAllBtn;
  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", clearAllEmojiFiles);
  }

  // Bind Context Menu actions
  const contextMenuDeleteBtn = elements.contextMenuDeleteBtn;
  if (contextMenuDeleteBtn) {
    contextMenuDeleteBtn.addEventListener("click", async () => {
      const menuItems = state.contextMenuState.items;
      closeBatchContextMenu();
      const { deleteEmojiItems, isEmojiSelected } = await import("./modules/interactions.js");
      await deleteEmojiItems(menuItems, {
        useSelectionState:
          menuItems.length > 0 &&
          menuItems.every((item) => isEmojiSelected(item.category, item.emoji)),
        confirmMode: "danger",
      });
    });
  }

  const contextMenuMoveBtn = elements.contextMenuMoveBtn;
  if (contextMenuMoveBtn) {
    contextMenuMoveBtn.addEventListener("click", async () => {
      const menuItems = state.contextMenuState.items;
      closeBatchContextMenu();
      const confirmed = await showConfirm({
        title: "移动表情包",
        description: `确认继续为这 ${menuItems.length} 个表情包选择目标分类？`,
        confirmLabel: "继续选择目标分类",
      });
      if (!confirmed) return;
      openMoveTargetModal(menuItems);
    });
  }

  const contextMenuCopyBtn = elements.contextMenuCopyBtn;
  if (contextMenuCopyBtn) {
    contextMenuCopyBtn.addEventListener("click", async () => {
      const menuItems = state.contextMenuState.items;
      closeBatchContextMenu();
      const confirmed = await showConfirm({
        title: "复制表情包",
        description: `确认复制这 ${menuItems.length} 个表情包到 WebUI 剪贴板？`,
        confirmLabel: "确认复制",
      });
      if (!confirmed) return;
      copyItemsToClipboard(menuItems);
    });
  }

  const contextMenuPasteBtn = elements.contextMenuPasteBtn;
  if (contextMenuPasteBtn) {
    contextMenuPasteBtn.addEventListener("click", async () => {
      const targetCategory = state.contextMenuState.targetCategory;
      const clipboardItems = getClipboardItems();
      closeBatchContextMenu();
      const confirmed = await showConfirm({
        title: "粘贴表情包",
        description: `确认将剪贴板中的 ${clipboardItems.length} 个表情包粘贴到「${targetCategory}」？`,
        confirmLabel: "确认粘贴",
      });
      if (!confirmed) return;
      await copyEmojiItemsToCategory(targetCategory, clipboardItems);
    });
  }

  // Bind Sidebar Actions
  const sidebarToggleBtn = elements.sidebarToggleBtn;
  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener("click", () => toggleSidebar());
  }

  const sidebarCloseBtn = elements.sidebarCloseBtn;
  if (sidebarCloseBtn) {
    sidebarCloseBtn.addEventListener("click", () => closeSidebar());
  }

  const sidebarBackdrop = elements.sidebarBackdrop;
  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", () => closeSidebar());
  }

  // Bind Danger Confirm Ack Modal actions
  const dangerModalAck = elements.dangerModalAcknowledge;
  if (dangerModalAck) {
    dangerModalAck.addEventListener("change", () => {
      if (state.dangerConfirmStage === "ack") {
        if (!dangerModalAck.checked) {
          const btn = elements.dangerModalConfirmBtn;
          if (btn) {
            btn.disabled = true;
            btn.textContent = "请先勾选上方选项";
          }
          return;
        }
        startDangerCountdown();
      }
    });
  }

  const dangerModalCancelBtn = elements.dangerModalCancelBtn;
  if (dangerModalCancelBtn) {
    dangerModalCancelBtn.addEventListener("click", () => {
      closeDangerConfirm(false);
    });
  }

  const dangerModalConfirmBtn = elements.dangerModalConfirmBtn;
  if (dangerModalConfirmBtn) {
    dangerModalConfirmBtn.addEventListener("click", () => {
      if (state.dangerConfirmStage === "ack" && dangerModalAck?.checked) {
        startDangerCountdown();
        return;
      }
      if (state.dangerConfirmStage === "ready") {
        closeDangerConfirm(true);
      }
    });
  }

  const dangerModalRoot = elements.dangerModalRoot;
  if (dangerModalRoot) {
    dangerModalRoot.addEventListener("click", (event) => {
      if (event.target === dangerModalRoot) {
        closeDangerConfirm(false);
      }
    });
  }

  // Bind Standard Confirm Modal actions
  const confirmModalCancelBtn = elements.confirmModalCancelBtn;
  if (confirmModalCancelBtn) {
    confirmModalCancelBtn.addEventListener("click", () => {
      closeConfirm(false);
    });
  }

  const confirmModalConfirmBtn = elements.confirmModalConfirmBtn;
  if (confirmModalConfirmBtn) {
    confirmModalConfirmBtn.addEventListener("click", () => {
      closeConfirm(true);
    });
  }

  const confirmModalRoot = elements.confirmModalRoot;
  if (confirmModalRoot) {
    confirmModalRoot.addEventListener("click", (event) => {
      if (event.target === confirmModalRoot) {
        closeConfirm(false);
      }
    });
  }

  // Bind Category Edit Modal actions
  const categoryEditCancelBtn = elements.categoryEditCancelBtn;
  if (categoryEditCancelBtn) {
    categoryEditCancelBtn.addEventListener("click", () => {
      closeCategoryEditModal();
    });
  }

  const categoryEditSaveBtn = elements.categoryEditSaveBtn;
  if (categoryEditSaveBtn) {
    categoryEditSaveBtn.addEventListener("click", async () => {
      await saveCategory();
    });
  }

  const categoryEditModalRoot = elements.categoryEditModalRoot;
  if (categoryEditModalRoot) {
    categoryEditModalRoot.addEventListener("click", (event) => {
      if (event.target === categoryEditModalRoot) {
        closeCategoryEditModal();
      }
    });
  }

  [elements.categoryEditNameInput, elements.categoryEditDescInput].forEach((input) => {
    input?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await saveCategory();
      }
    });
  });

  // Bind Move Target Modal actions
  const moveTargetCancelBtn = elements.moveTargetCancelBtn;
  if (moveTargetCancelBtn) {
    moveTargetCancelBtn.addEventListener("click", () => {
      closeMoveTargetModal();
    });
  }

  const moveTargetModalRoot = elements.moveTargetModalRoot;
  if (moveTargetModalRoot) {
    moveTargetModalRoot.addEventListener("click", (event) => {
      if (event.target === moveTargetModalRoot) {
        closeMoveTargetModal();
      }
    });
  }

  // Document level pointer move handlers for dragging & long press cancellation
  document.addEventListener("pointermove", (event) => {
    if (
      state.longPressState.emojiItem &&
      typeof event.pointerId === "number" &&
      event.pointerId === state.longPressState.pointerId
    ) {
      const offsetX = event.clientX - state.longPressState.startX;
      const offsetY = event.clientY - state.longPressState.startY;
      const movedDistance = Math.hypot(offsetX, offsetY);
      if (movedDistance > LONG_PRESS_CANCEL_DISTANCE_PX) {
        cancelLongPress();
        return;
      }

      state.longPressState.currentX = event.clientX;
      state.longPressState.currentY = event.clientY;

      const elapsed = performance.now() - state.longPressState.startTime;
      const progress = Math.min(1, elapsed / LONG_PRESS_DURATION_MS);
      const remainingSeconds = Math.max(
        1,
        Math.ceil((LONG_PRESS_DURATION_MS - elapsed) / 1000)
      );
      setLongPressProgress(progress, `${remainingSeconds}s`);
      event.preventDefault();
    }

    if (
      state.dragModeState.pointerId !== null &&
      typeof event.pointerId === "number" &&
      event.pointerId === state.dragModeState.pointerId
    ) {
      updatePointerDrag(event);
      event.preventDefault();
    }
  });

  const handlePointerRelease = async (event) => {
    finishLongPress(event);
    await finishPointerDrag(event);
  };

  document.addEventListener("pointerup", (event) => {
    void handlePointerRelease(event);
  });

  document.addEventListener("pointercancel", (event) => {
    void handlePointerRelease(event);
  });

  document.addEventListener(
    "touchmove",
    (event) => {
      if (state.dragModeState.pointerId !== null) {
        event.preventDefault();
      }
    },
    { passive: false }
  );

  document.addEventListener("dragstart", (event) => {
    if (hasActiveDragInteraction() || event.target?.closest?.(".emoji-item")) {
      event.preventDefault();
    }
  });

  document.addEventListener("contextmenu", (event) => {
    if (shouldOpenBatchContextMenu(event)) {
      event.preventDefault();
      openBatchContextMenu(event);
      return;
    }

    closeBatchContextMenu();

    if (hasActiveDragInteraction()) {
      event.preventDefault();
    }
  });

  document.addEventListener("click", (event) => {
    const menu = elements.batchContextMenu;
    if (!menu || menu.classList.contains("hidden")) return;
    if (event.target.closest("#batch-context-menu")) return;
    closeBatchContextMenu();
  });

  document.addEventListener("scroll", () => closeBatchContextMenu(), true);

  document.addEventListener("selectstart", (event) => {
    if (
      hasActiveDragInteraction() ||
      event.target?.closest?.(".emoji-item") ||
      event.target?.closest?.(".emoji-upload")
    ) {
      event.preventDefault();
    }
  });

  // ESC key cancels modals & drag
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.dragModeState.items.length > 0) {
      clearDragMode();
      showToast("已退出拖拽模式。", "info", "拖拽模式已关闭");
      return;
    }
    if (event.key === "Escape" && elements.batchContextMenu) {
      const isOpen = !elements.batchContextMenu.classList.contains("hidden");
      if (isOpen) {
        closeBatchContextMenu();
        return;
      }
    }
    if (event.key === "Escape" && isCompactViewport()) {
      const isOpen = document.body.classList.contains("sidebar-open");
      if (isOpen) {
        closeSidebar();
        return;
      }
    }
    if (event.key === "Escape" && elements.moveTargetModalRoot) {
      const isOpen = !elements.moveTargetModalRoot.classList.contains("hidden");
      if (isOpen) {
        closeMoveTargetModal();
        return;
      }
    }
    if (event.key === "Escape" && elements.categoryEditModalRoot) {
      const isOpen = !elements.categoryEditModalRoot.classList.contains("hidden");
      if (isOpen) {
        closeCategoryEditModal();
        return;
      }
    }
    if (event.key === "Escape" && elements.confirmModalRoot) {
      const isOpen = !elements.confirmModalRoot.classList.contains("hidden");
      if (isOpen) {
        closeConfirm(false);
        return;
      }
    }
    if (event.key === "Escape" && elements.dangerModalRoot) {
      const isOpen = !elements.dangerModalRoot.classList.contains("hidden");
      if (isOpen) {
        closeDangerConfirm(false);
      }
    }
  });

  // Persona filter change listener
  const filterSelect = document.getElementById("persona-filter");
  if (filterSelect) {
    filterSelect.addEventListener("change", () => {
      fetchEmojis();
    });
  }

  // Emoji Edit Modal cancel and save buttons
  const emojiEditCancelBtn = document.getElementById("emoji-edit-cancel-btn");
  if (emojiEditCancelBtn) {
    emojiEditCancelBtn.addEventListener("click", closeEmojiEditModal);
  }

  const emojiEditSaveBtn = document.getElementById("emoji-edit-save-btn");
  if (emojiEditSaveBtn) {
    emojiEditSaveBtn.addEventListener("click", async () => {
      const filename = elements.editEmojiFilename.value;
      const emotionsStr = elements.editEmojiEmotions.value;
      const emotions = emotionsStr.split(",").map(e => e.trim()).filter(e => e);

      const checkedPersonas = [];
      elements.editEmojiPersonasDiv.querySelectorAll("input:checked").forEach(cb => {
        checkedPersonas.push(cb.value);
      });

      if (checkedPersonas.length === 0) {
        checkedPersonas.push("*");
      }

      const { setButtonBusy, restoreButton } = await import("./modules/ui.js");
      setButtonBusy(emojiEditSaveBtn, "正在保存...");

      try {
        const res = await fetch("/api/emoji/edit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: filename,
            emotions: emotions,
            personas: checkedPersonas,
          }),
        });

        if (!res.ok) throw new Error("保存表情包属性失败");

        showToast("属性保存成功！", "success", "编辑成功");
        closeEmojiEditModal();
        await fetchEmojis();
      } catch (e) {
        console.error(e);
        showToast("保存失败: " + e.message, "error", "保存失败");
      } finally {
        restoreButton(emojiEditSaveBtn);
      }
    });
  }

  // Initialize data and listeners
  syncSidebarLayout();
  updateSidebarToggleState();

  window.addEventListener("resize", () => {
    syncSidebarLayout();
    closeBatchContextMenu();
  });

  window.addEventListener("beforeunload", () => {
    cancelAllPendingRequests();
  });

  void (async () => {
    await fetchEmojis();
    await fetchPersonas();
    state.initialStatusTimerId = window.setTimeout(() => {
      state.initialStatusTimerId = null;
      void checkSyncStatus(false);
      void checkImgHostSyncStatus(false);
    }, 180);
  })();

  // Expose legacy API on window object for HTML links/buttons
  window.restoreCategory = restoreCategory;
  window.removeFromConfig = removeFromConfig;
  window.syncConfig = syncConfig;
  window.editCategory = editCategory;
  window.cancelEdit = cancelEdit;
  window.saveCategory = saveCategory;
  window.openEmojiEditModal = openEmojiEditModal;
});
