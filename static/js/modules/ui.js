// ui.js - DOM management, modals, rendering and layouts for the Meme Manager WebUI

import { state } from "./state.js";
import {
  fetchEmojis,
  syncConfig,
  restoreCategory,
  removeFromConfig,
  clearCategory,
  deleteCategory,
  deleteEmoji,
  requestJson,
} from "./api.js";

// DOM Element cache
export const elements = {
  get toggleSelectionModeBtn() { return document.getElementById("toggle-selection-mode-btn"); },
  get batchMoveBtn() { return document.getElementById("batch-move-btn"); },
  get batchDeleteBtn() { return document.getElementById("batch-delete-btn"); },
  get clearAllBtn() { return document.getElementById("clear-all-btn"); },
  get selectionSummary() { return document.getElementById("selection-summary"); },
  get toastContainer() { return document.getElementById("toast-container"); },
  get batchContextMenu() { return document.getElementById("batch-context-menu"); },
  get batchContextMenuTitle() { return document.getElementById("batch-context-menu-title"); },
  get batchContextMenuSubtitle() { return document.getElementById("batch-context-menu-subtitle"); },
  get contextMenuDeleteBtn() { return document.getElementById("context-menu-delete-btn"); },
  get contextMenuMoveBtn() { return document.getElementById("context-menu-move-btn"); },
  get contextMenuCopyBtn() { return document.getElementById("context-menu-copy-btn"); },
  get contextMenuPasteBtn() { return document.getElementById("context-menu-paste-btn"); },
  get sidebarToggleBtn() { return document.getElementById("sidebar-toggle-btn"); },
  get sidebarCloseBtn() { return document.getElementById("sidebar-close-btn"); },
  get sidebarBackdrop() { return document.getElementById("sidebar-backdrop"); },
  get leftPanel() { return document.getElementById("app-sidebar-panel"); },
  get dragHud() { return document.getElementById("drag-hud"); },
  get dragHudLabel() { return document.getElementById("drag-hud-label"); },
  get dragHudCaption() { return document.getElementById("drag-hud-caption"); },
  get moveTargetModalRoot() { return document.getElementById("move-target-modal"); },
  get moveTargetModalTitle() { return document.getElementById("move-target-modal-title"); },
  get moveTargetModalDescription() { return document.getElementById("move-target-modal-description"); },
  get moveTargetList() { return document.getElementById("move-target-list"); },
  get moveTargetCancelBtn() { return document.getElementById("move-target-cancel-btn"); },
  get categoryEditModalRoot() { return document.getElementById("category-edit-modal"); },
  get categoryEditModalTitle() { return document.getElementById("category-edit-modal-title"); },
  get categoryEditModalDescription() { return document.getElementById("category-edit-modal-description"); },
  get categoryEditNameInput() { return document.getElementById("category-edit-name-input"); },
  get categoryEditDescInput() { return document.getElementById("category-edit-desc-input"); },
  get categoryEditCancelBtn() { return document.getElementById("category-edit-cancel-btn"); },
  get categoryEditSaveBtn() { return document.getElementById("category-edit-save-btn"); },
  get confirmModalRoot() { return document.getElementById("confirm-modal"); },
  get confirmModalTitle() { return document.getElementById("confirm-modal-title"); },
  get confirmModalDescription() { return document.getElementById("confirm-modal-description"); },
  get confirmModalCancelBtn() { return document.getElementById("confirm-modal-cancel-btn"); },
  get confirmModalConfirmBtn() { return document.getElementById("confirm-modal-confirm-btn"); },
  get dangerModalRoot() { return document.getElementById("danger-confirm-modal"); },
  get dangerModalTitle() { return document.getElementById("danger-modal-title"); },
  get dangerModalDescription() { return document.getElementById("danger-modal-description"); },
  get dangerModalStageText() { return document.getElementById("danger-modal-stage-text"); },
  get dangerModalAcknowledge() { return document.getElementById("danger-modal-ack"); },
  get dangerModalCancelBtn() { return document.getElementById("danger-modal-cancel-btn"); },
  get dangerModalConfirmBtn() { return document.getElementById("danger-modal-confirm-btn"); },
  get emojiEditModalRoot() { return document.getElementById("emoji-edit-modal"); },
  get editEmojiFilename() { return document.getElementById("edit-emoji-filename"); },
  get editEmojiEmotions() { return document.getElementById("edit-emoji-emotions"); },
  get editEmojiPersonasDiv() { return document.getElementById("edit-emoji-personas-list"); },
};

export const MOBILE_LAYOUT_MEDIA = "(max-width: 960px)";
export const DRAG_HUD_OFFSET_X = 18;
export const DRAG_HUD_OFFSET_Y = 88;
export const LONG_PRESS_DURATION_MS = 3000;
export const LONG_PRESS_TICK_MS = 60;
export const LONG_PRESS_CANCEL_DISTANCE_PX = 18;
export const DRAG_READY_TIMEOUT_MS = 15000;

export let confirmResolver = null;

import {
  clearDragMode,
  closeBatchContextMenu,
  bindEmojiInteractions,
  attachCategoryDropTarget,
  uploadFilesToCategory,
  isCategoryUploading,
  getAvailableMoveTargets,
  getMoveableCountForTarget,
  createSelectionKey,
  isEmojiSelected,
  getCategorySelectedCount,
} from "./interactions.js";

// Helper functions for DOM element creation and modifications
export function createButton({
  className = "",
  text = "",
  disabled = false,
  onClick = null,
}) {
  const button = document.createElement("button");
  button.type = "button";
  if (className) {
    button.className = className;
  }
  button.textContent = text;
  button.disabled = disabled;
  if (onClick) {
    button.addEventListener("click", onClick);
  }
  return button;
}

export function createIconButton({
  className = "",
  iconClass = "",
  title = "",
  ariaLabel = "",
  onClick = null,
}) {
  const button = document.createElement("button");
  button.type = "button";
  if (className) {
    button.className = className;
  }
  if (title) {
    button.title = title;
  }
  if (ariaLabel) {
    button.setAttribute("aria-label", ariaLabel);
  }

  if (iconClass) {
    const icon = document.createElement("i");
    icon.className = iconClass;
    button.appendChild(icon);
  }

  if (onClick) {
    button.addEventListener("click", onClick);
  }

  return button;
}

export function setButtonBusy(button, busyText) {
  if (!button) return;
  if (!button.dataset.originalHtml) {
    button.dataset.originalHtml = button.innerHTML;
  }
  button.disabled = true;
  button.textContent = busyText;
}

export function restoreButton(button) {
  if (!button) return;
  button.disabled = false;
  if (button.dataset.originalHtml) {
    button.innerHTML = button.dataset.originalHtml;
  }
}

export function showToast(message, type = "info", title = "提示", duration = 3200) {
  const container = elements.toastContainer;
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  const content = document.createElement("div");
  content.className = "toast-content";

  const titleElement = document.createElement("p");
  titleElement.className = "toast-title";
  titleElement.textContent = title;

  const messageElement = document.createElement("p");
  messageElement.className = "toast-message";
  messageElement.textContent = message;

  content.appendChild(titleElement);
  content.appendChild(messageElement);
  toast.appendChild(content);
  container.appendChild(toast);

  window.setTimeout(() => {
    toast.remove();
  }, duration);
}

// Dialog / Confirms
export function closeConfirm(result) {
  const root = elements.confirmModalRoot;
  if (root) {
    root.classList.add("hidden");
    root.setAttribute("aria-hidden", "true");
  }
  const confirmBtn = elements.confirmModalConfirmBtn;
  if (confirmBtn) {
    confirmBtn.classList.remove("danger");
    confirmBtn.textContent = "确认";
  }
  if (confirmResolver) {
    const resolver = confirmResolver;
    confirmResolver = null;
    resolver(result);
  }
}

export function showConfirm({
  title,
  description,
  confirmLabel = "确认",
  confirmClassName = "",
}) {
  const root = elements.confirmModalRoot;
  const titleEl = elements.confirmModalTitle;
  const descEl = elements.confirmModalDescription;
  const confirmBtn = elements.confirmModalConfirmBtn;

  if (!root || !titleEl || !descEl || !confirmBtn) {
    return Promise.resolve(confirm(`${title}\n\n${description}`));
  }

  titleEl.textContent = title;
  descEl.textContent = description;
  confirmBtn.textContent = confirmLabel;
  confirmBtn.classList.toggle(
    "danger",
    confirmClassName.includes("danger")
  );
  root.classList.remove("hidden");
  root.setAttribute("aria-hidden", "false");

  return new Promise((resolve) => {
    confirmResolver = resolve;
  });
}

// Danger Confirms
export function resetDangerConfirmState() {
  if (state.dangerConfirmTimer) {
    clearInterval(state.dangerConfirmTimer);
    state.dangerConfirmTimer = null;
  }
  state.dangerConfirmConfig = null;
  state.dangerConfirmStage = "ack";
  
  const ack = elements.dangerModalAcknowledge;
  if (ack) {
    ack.checked = false;
    ack.disabled = false;
  }
  const stageText = elements.dangerModalStageText;
  if (stageText) {
    stageText.textContent = "请先勾选已理解，勾选后会自动开始 5 秒倒计时。";
  }
  const confirmBtn = elements.dangerModalConfirmBtn;
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "请先勾选上方选项";
  }
}

export function closeDangerConfirm(result) {
  const root = elements.dangerModalRoot;
  if (root) {
    root.classList.add("hidden");
    root.setAttribute("aria-hidden", "true");
  }
  resetDangerConfirmState();
  if (state.dangerConfirmResolver) {
    const resolver = state.dangerConfirmResolver;
    state.dangerConfirmResolver = null;
    resolver(result);
  }
}

export function startDangerCountdown() {
  if (state.dangerConfirmStage !== "ack" || !state.dangerConfirmConfig) {
    return;
  }

  const countdown = state.dangerConfirmConfig?.countdown ?? 5;
  let remaining = countdown;

  state.dangerConfirmStage = "countdown";
  const ack = elements.dangerModalAcknowledge;
  if (ack) {
    ack.disabled = true;
  }
  const stageText = elements.dangerModalStageText;
  if (stageText) {
    stageText.textContent = `安全等待中，还需 ${remaining} 秒，倒计时结束后才可执行。`;
  }
  const confirmBtn = elements.dangerModalConfirmBtn;
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = `等待 ${remaining} 秒`;
  }

  state.dangerConfirmTimer = setInterval(() => {
    remaining -= 1;
    if (remaining > 0) {
      if (stageText) {
        stageText.textContent = `安全等待中，还需 ${remaining} 秒，倒计时结束后才可执行。`;
      }
      if (confirmBtn) {
        confirmBtn.textContent = `等待 ${remaining} 秒`;
      }
      return;
    }

    clearInterval(state.dangerConfirmTimer);
    state.dangerConfirmTimer = null;
    state.dangerConfirmStage = "ready";
    if (stageText) {
      stageText.textContent = "5 秒倒计时已结束，请点击下方按钮执行。";
    }
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = state.dangerConfirmConfig.actionLabel;
    }
  }, 1000);
}

export function showDangerConfirm({ title, description, actionLabel, countdown = 5 }) {
  const root = elements.dangerModalRoot;
  const titleEl = elements.dangerModalTitle;
  const descEl = elements.dangerModalDescription;
  const confirmBtn = elements.dangerModalConfirmBtn;
  const stageText = elements.dangerModalStageText;

  if (!root || !titleEl || !descEl || !confirmBtn) {
    return Promise.resolve(
      confirm(`${title}\n\n${description}\n\n确认要继续执行吗？`)
    );
  }

  resetDangerConfirmState();
  state.dangerConfirmConfig = { actionLabel, countdown };
  titleEl.textContent = title;
  descEl.textContent = description;
  if (stageText) {
    stageText.textContent = `请先勾选已理解，勾选后会自动开始 ${countdown} 秒倒计时。倒计时结束后才可执行。`;
  }
  if (confirmBtn) {
    confirmBtn.textContent = "请先勾选上方选项";
    confirmBtn.disabled = true;
  }
  root.classList.remove("hidden");
  root.setAttribute("aria-hidden", "false");

  return new Promise((resolve) => {
    state.dangerConfirmResolver = resolve;
  });
}

// Sidebar/Layout
export function isCompactViewport() {
  return window.matchMedia(MOBILE_LAYOUT_MEDIA).matches;
}

export function updateSidebarToggleState() {
  const sidebarExpanded = isCompactViewport()
    ? document.body.classList.contains("sidebar-open")
    : !document.body.classList.contains("sidebar-collapsed");

  const btn = elements.sidebarToggleBtn;
  if (btn) {
    btn.setAttribute("aria-expanded", String(sidebarExpanded));
    btn.setAttribute(
      "aria-label",
      sidebarExpanded ? "收起侧边栏" : "展开侧边栏"
    );
  }

  const backdrop = elements.sidebarBackdrop;
  if (backdrop) {
    backdrop.classList.toggle(
      "hidden",
      !(isCompactViewport() && sidebarExpanded)
    );
    backdrop.setAttribute(
      "aria-hidden",
      String(!(isCompactViewport() && sidebarExpanded))
    );
  }

  const panel = elements.leftPanel;
  if (panel) {
    panel.setAttribute("aria-hidden", String(!sidebarExpanded));
  }
}

export function openSidebar() {
  if (!isCompactViewport()) {
    return;
  }
  document.body.classList.add("sidebar-open");
  updateSidebarToggleState();
}

export function closeSidebar() {
  document.body.classList.remove("sidebar-open");
  updateSidebarToggleState();
}

export function syncSidebarLayout() {
  if (isCompactViewport()) {
    document.body.classList.remove("sidebar-collapsed");
    closeSidebar();
    return;
  }

  document.body.classList.remove("sidebar-open");
  document.body.classList.remove("sidebar-collapsed");
  updateSidebarToggleState();
}

export function toggleSidebar() {
  if (!isCompactViewport()) {
    return;
  }

  if (document.body.classList.contains("sidebar-open")) {
    closeSidebar();
  } else {
    openSidebar();
  }
}

export function formatBytes(bytes) {
  if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes < 0) {
    return "未知";
  }
  if (bytes === 0) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const precision = unitIndex === 0 ? 0 : value >= 100 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

// Modal Control
export function closeMoveTargetModal() {
  const root = elements.moveTargetModalRoot;
  if (root) {
    root.classList.add("hidden");
    root.setAttribute("aria-hidden", "true");
  }
  state.pendingMoveTargetItems = [];
  const list = elements.moveTargetList;
  if (list) {
    list.innerHTML = "";
  }
}

export function openMoveTargetModal(items = Array.from(state.selectionState.items.values())) {
  const uniqueItems = dedupeEmojiItems(items);
  if (uniqueItems.length === 0) {
    showToast("请先选择要移动的表情包。", "warning", "未选择项目");
    return;
  }

  const availableTargets = getAvailableMoveTargets(uniqueItems);
  if (availableTargets.length === 0) {
    showToast("当前没有可移动到的其他分类。", "warning", "无法移动");
    return;
  }

  state.pendingMoveTargetItems = uniqueItems;
  const titleEl = elements.moveTargetModalTitle;
  if (titleEl) {
    titleEl.textContent = "选择目标分类";
  }
  const descEl = elements.moveTargetModalDescription;
  if (descEl) {
    descEl.textContent =
      uniqueItems.length > 1
        ? `已选 ${uniqueItems.length} 个表情包，选择要批量移动到的分类。`
        : "选择要移动到的目标分类。";
  }

  const list = elements.moveTargetList;
  if (list) {
    list.innerHTML = "";
    availableTargets.forEach((category) => {
      const moveableCount = getMoveableCountForTarget(uniqueItems, category);
      const optionButton = createButton({
        className: "move-target-option",
        onClick: async () => {
          closeMoveTargetModal();
          await moveEmojiItemsToCategory(category, uniqueItems);
        },
      });

      const title = document.createElement("span");
      title.className = "move-target-option-title";
      title.textContent = category;

      const meta = document.createElement("span");
      meta.className = "move-target-option-meta";
      meta.textContent = `可移动 ${moveableCount} 个表情包`;

      optionButton.appendChild(title);
      optionButton.appendChild(meta);
      list.appendChild(optionButton);
    });
  }

  const root = elements.moveTargetModalRoot;
  if (root) {
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");
  }
}

export function closeCategoryEditModal() {
  const root = elements.categoryEditModalRoot;
  if (root) {
    root.classList.add("hidden");
    root.setAttribute("aria-hidden", "true");
  }
  state.activeCategoryEdit = null;
  const nameInput = elements.categoryEditNameInput;
  if (nameInput) {
    nameInput.value = "";
  }
  const descInput = elements.categoryEditDescInput;
  if (descInput) {
    descInput.value = "";
  }
}

export function editCategory(category) {
  const currentDescription = document
    .getElementById(`category-desc-${category}`)
    ?.textContent?.trim();

  state.activeCategoryEdit = category;
  const titleEl = elements.categoryEditModalTitle;
  if (titleEl) {
    titleEl.textContent = `编辑类别「${category}」`;
  }
  const descEl = elements.categoryEditModalDescription;
  if (descEl) {
    descEl.textContent = "修改类别名称和描述，保存后立即生效。";
  }
  const nameInput = elements.categoryEditNameInput;
  if (nameInput) {
    nameInput.value = category;
  }
  const descInput = elements.categoryEditDescInput;
  if (descInput) {
    descInput.value =
      currentDescription && currentDescription !== "请添加描述"
        ? currentDescription
        : "";
  }
  const root = elements.categoryEditModalRoot;
  if (root) {
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");
  }
  window.setTimeout(() => {
    nameInput?.focus();
    nameInput?.select();
  }, 0);
}

export function cancelEdit() {
  closeCategoryEditModal();
}

export async function saveCategory(oldName = state.activeCategoryEdit) {
  const nameInput = elements.categoryEditNameInput;
  const descInput = elements.categoryEditDescInput;
  const newName = nameInput?.value.trim() || "";
  const newDesc = descInput?.value.trim() || "";

  if (!newName) {
    showToast("类别名称不能为空。", "warning", "保存失败");
    return;
  }

  if (!oldName) {
    showToast("未找到当前正在编辑的类别。", "error", "保存失败");
    return;
  }

  const saveBtn = elements.categoryEditSaveBtn;
  setButtonBusy(saveBtn, "保存中...");

  try {
    if (oldName !== newName) {
      await requestJson(
        "/api/category/rename",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ old_name: oldName, new_name: newName }),
        },
        { defaultErrorMessage: "重命名类别失败" }
      );
    }

    await requestJson(
      "/api/category/update_description",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag: newName, description: newDesc }),
      },
      { defaultErrorMessage: "更新描述失败" }
    );

    await fetchEmojis();
    await syncConfig();
    closeCategoryEditModal();
    showToast(
      `类别「${newName}」已保存。`,
      "success",
      "保存成功"
    );
  } catch (error) {
    console.error("保存类别修改失败:", error);
    showToast(error.message, "error", "保存失败");
  } finally {
    restoreButton(saveBtn);
  }
}

export function closeEmojiEditModal() {
  const root = elements.emojiEditModalRoot;
  if (root) {
    root.classList.add("hidden");
    root.setAttribute("aria-hidden", "true");
  }
}

export async function openEmojiEditModal(emoji) {
  const root = elements.emojiEditModalRoot;
  const editFilename = elements.editEmojiFilename;
  const editEmotions = elements.editEmojiEmotions;
  const editPersonasDiv = elements.editEmojiPersonasDiv;
  if (!root) return;
  
  try {
    const res = await fetch(`/api/emoji/info/${encodeURIComponent(emoji)}`);
    if (!res.ok) throw new Error("获取表情包属性失败");
    const metadata = await res.json();
    
    if (editFilename) editFilename.value = emoji;
    if (editEmotions) editEmotions.value = metadata.emotions ? metadata.emotions.join(", ") : "";
    
    if (editPersonasDiv) {
      editPersonasDiv.innerHTML = "";
      
      const globalLabel = document.createElement("label");
      globalLabel.style.display = "flex";
      globalLabel.style.alignItems = "center";
      globalLabel.style.gap = "8px";
      const globalCheckbox = document.createElement("input");
      globalCheckbox.type = "checkbox";
      globalCheckbox.value = "*";
      globalCheckbox.checked = !metadata.personas || metadata.personas.includes("*");
      const globalSpan = document.createElement("span");
      globalSpan.textContent = "全局可用 (*)";
      globalLabel.appendChild(globalCheckbox);
      globalLabel.appendChild(globalSpan);
      editPersonasDiv.appendChild(globalLabel);
      
      globalCheckbox.addEventListener("change", () => {
        if (globalCheckbox.checked) {
          editPersonasDiv.querySelectorAll("input").forEach(cb => {
            if (cb.value !== "*") cb.checked = false;
          });
        }
      });
      
      state.systemPersonas.forEach(p => {
        const label = document.createElement("label");
        label.style.display = "flex";
        label.style.alignItems = "center";
        label.style.gap = "8px";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = p.id;
        checkbox.checked = metadata.personas && metadata.personas.includes(p.id) && !metadata.personas.includes("*");
        
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            globalCheckbox.checked = false;
          }
        });
        
        const span = document.createElement("span");
        span.textContent = `${p.name} (${p.id})`;
        
        label.appendChild(checkbox);
        label.appendChild(span);
        editPersonasDiv.appendChild(label);
      });
    }
    
    root.classList.remove("hidden");
    root.setAttribute("aria-hidden", "false");
  } catch (e) {
    console.error(e);
    showToast("无法获取表情包属性: " + e.message, "error", "加载失败");
  }
}

// Selection & Toolbar updates
export function updateSelectionToolbar() {
  const selectedCount = state.selectionState.items.size;
  const availableMoveTargets = getAvailableMoveTargets();

  const summary = elements.selectionSummary;
  if (summary) {
    summary.textContent = state.selectionState.enabled
      ? `已选中 ${selectedCount} 个表情包`
      : "未开启批量选择";
  }
  const toggleBtn = elements.toggleSelectionModeBtn;
  if (toggleBtn) {
    toggleBtn.textContent = state.selectionState.enabled
      ? "退出批量选择"
      : "开启批量选择";
  }
  const deleteBtn = elements.batchDeleteBtn;
  if (deleteBtn) {
    deleteBtn.disabled = !state.selectionState.enabled || selectedCount === 0;
  }
  const moveBtn = elements.batchMoveBtn;
  if (moveBtn) {
    moveBtn.disabled =
      !state.selectionState.enabled ||
      selectedCount === 0 ||
      availableMoveTargets.length === 0;
  }
}

export function updateSelectionDecorations() {
  document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
    const category = emojiItem.dataset.category;
    const emoji = emojiItem.dataset.emoji;
    const selected = isEmojiSelected(category, emoji);
    const selectionIndicator = emojiItem.querySelector(".selection-indicator");

    emojiItem.classList.toggle("selection-mode", state.selectionState.enabled);
    emojiItem.classList.toggle("selected", selected);
    if (selectionIndicator) {
      selectionIndicator.classList.toggle("checked", selected);
      selectionIndicator.setAttribute(
        "aria-label",
        selected ? "已选中" : "未选择"
      );
    }
  });

  document.querySelectorAll(".category").forEach((categoryDiv) => {
    const category = categoryDiv.dataset.category;
    const totalCount = Array.isArray(state.latestEmojiData[category])
      ? state.latestEmojiData[category].length
      : 0;
    const selectedCount = getCategorySelectedCount(category);
    const summary = categoryDiv.querySelector(".category-selection-summary");
    const selectAllBtn = categoryDiv.querySelector(".select-all-category-btn");
    const hasEmojis = totalCount > 0;
    const allSelected = hasEmojis && selectedCount === totalCount;

    if (summary) {
      summary.textContent = state.selectionState.enabled
        ? `已选 ${selectedCount} / ${totalCount}`
        : "未开启批量选择";
    }
    if (selectAllBtn) {
      selectAllBtn.disabled = !hasEmojis;
      selectAllBtn.textContent = state.selectionState.enabled
        ? allSelected
          ? "取消本类"
          : "本类全选"
        : "本类选择";
    }
  });
}

export function updateSelectionUI() {
  updateSelectionToolbar();
  updateSelectionDecorations();
}

// Sync Rendering
export function createSyncStatusSection(title, categories, actionsBuilder = null) {
  const section = document.createElement("div");
  section.className = "status-section";

  const heading = document.createElement("h4");
  heading.textContent = title;
  section.appendChild(heading);

  const list = document.createElement("ul");
  categories.forEach((category) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = category;
    item.appendChild(label);

    if (actionsBuilder) {
      item.appendChild(actionsBuilder(category));
    }

    list.appendChild(item);
  });
  section.appendChild(list);

  return section;
}

export function normalizeSyncDifferences(payload) {
  const source =
    payload && typeof payload.differences === "object" && payload.differences !== null
      ? payload.differences
      : payload;

  return {
    missing_in_config: Array.isArray(source?.missing_in_config)
      ? source.missing_in_config
      : [],
    deleted_categories: Array.isArray(source?.deleted_categories)
      ? source.deleted_categories
      : [],
  };
}

export function renderSyncStatus(statusDiv, differences) {
  statusDiv.innerHTML = "";
  const fragments = [];
  const normalizedDifferences = normalizeSyncDifferences(differences);

  if (normalizedDifferences.missing_in_config.length > 0) {
    fragments.push(
      createSyncStatusSection(
        "新增类别（需要添加到配置）：",
        normalizedDifferences.missing_in_config,
        () =>
          createButton({
            className: "sync-btn",
            text: "同步配置",
            onClick: () => syncConfig(),
          })
      )
    );
  }

  if (normalizedDifferences.deleted_categories.length > 0) {
    fragments.push(
      createSyncStatusSection(
        "已删除的类别（配置中仍存在）：",
        normalizedDifferences.deleted_categories,
        (category) => {
          const actions = document.createElement("div");
          actions.className = "action-buttons";
          actions.appendChild(
            createButton({
              className: "restore-btn",
              text: "恢复类别",
              onClick: () => restoreCategory(category),
            })
          );
          actions.appendChild(
            createButton({
              className: "remove-btn",
              text: "从配置中删除",
              onClick: () => removeFromConfig(category),
            })
          );
          return actions;
        }
      )
    );
  }

  if (fragments.length === 0) {
    const text = document.createElement("p");
    text.textContent = "配置与文件夹结构一致！";
    statusDiv.appendChild(text);
    return;
  }

  fragments.forEach((fragment) => {
    statusDiv.appendChild(fragment);
  });

  const syncActions = document.createElement("div");
  syncActions.className = "sync-actions";
  syncActions.appendChild(
    createButton({
      className: "main-sync-btn",
      text: "同步所有配置",
      onClick: () => syncConfig(),
    })
  );
  statusDiv.appendChild(syncActions);
}

export function renderSyncStatusError(statusDiv, message) {
  statusDiv.innerHTML = "";

  const errorText = document.createElement("p");
  errorText.style.color = "red";
  errorText.textContent = `检查同步状态失败: ${message}`;
  statusDiv.appendChild(errorText);

  statusDiv.appendChild(
    createButton({
      className: "retry-btn",
      text: "重试",
      onClick: () => checkSyncStatus(),
    })
  );
}

// Display/Render Categories
export function displayCategories(emojiData, tagDescriptions) {
  const container = document.getElementById("emoji-categories");
  if (!container) return;
  container.innerHTML = "";

  Object.entries(emojiData).forEach(([category, emojis]) => {
    const categoryDiv = document.createElement("div");
    categoryDiv.className = "category";
    categoryDiv.id = `category-${category}`;
    categoryDiv.dataset.category = category;

    const description = tagDescriptions[category] || `请添加描述`;
    const titleDiv = document.createElement("div");
    titleDiv.className = "category-title";
    const categorySelectedCount = getCategorySelectedCount(category);
    const allSelectedInCategory =
      Array.isArray(emojis) &&
      emojis.length > 0 &&
      emojis.every((emoji) => isEmojiSelected(category, emoji));
    const headerDiv = document.createElement("div");
    headerDiv.className = "category-header";

    const titleMain = document.createElement("div");
    titleMain.className = "category-title-main";

    const categoryName = document.createElement("div");
    categoryName.className = "category-name";
    categoryName.id = `category-name-${category}`;
    categoryName.textContent = category;

    const summarySpan = document.createElement("span");
    summarySpan.className = "category-selection-summary";
    summarySpan.id = `category-selection-summary-${category}`;
    summarySpan.textContent = state.selectionState.enabled
      ? `已选 ${categorySelectedCount} / ${emojis.length || 0}`
      : "未开启批量选择";

    titleMain.appendChild(categoryName);
    titleMain.appendChild(summarySpan);

    const actionsDiv = document.createElement("div");
    actionsDiv.className = "category-actions";

    const editBtn = createButton({
      className: "edit-category-btn",
      text: "编辑类别",
      onClick: () => editCategory(category),
    });
    const toggleCategoryBtn = createButton({
      className: "select-all-category-btn",
      text: state.selectionState.enabled
        ? allSelectedInCategory
          ? "取消本类"
          : "本类全选"
        : "本类选择",
      disabled: !Array.isArray(emojis) || emojis.length === 0,
      onClick: () => toggleCategorySelection(category, emojis),
    });
    const clearCategoryBtn = createButton({
      className: "clear-category-btn danger",
      text: "清空本类",
      onClick: () => clearCategory(category),
    });
    const deleteCategoryBtn = createIconButton({
      className: "delete-category-btn icon-only-btn danger",
      iconClass: "fas fa-trash",
      title: `删除类别 ${category}`,
      ariaLabel: `删除类别 ${category}`,
      onClick: () => deleteCategory(category),
    });

    actionsDiv.appendChild(editBtn);
    actionsDiv.appendChild(toggleCategoryBtn);
    actionsDiv.appendChild(clearCategoryBtn);
    actionsDiv.appendChild(deleteCategoryBtn);

    headerDiv.appendChild(titleMain);
    headerDiv.appendChild(actionsDiv);

    const descriptionElement = document.createElement("p");
    descriptionElement.className = "description";
    descriptionElement.id = `category-desc-${category}`;
    descriptionElement.textContent = description;

    titleDiv.appendChild(headerDiv);
    titleDiv.appendChild(descriptionElement);
    categoryDiv.appendChild(titleDiv);

    const emojiGrid = document.createElement("div");
    emojiGrid.className = "emoji-grid";

    if (Array.isArray(emojis)) {
      emojis.forEach((emoji) => {
        const emojiItem = document.createElement("div");
        emojiItem.className = "emoji-item";
        emojiItem.dataset.category = category;
        emojiItem.dataset.emoji = emoji;
        emojiItem.dataset.suppressClick = "false";
        emojiItem.tabIndex = 0;

        const selectionIndicator = document.createElement("button");
        selectionIndicator.type = "button";
        selectionIndicator.className = "selection-indicator";
        selectionIndicator.setAttribute("aria-label", "选择表情包");
        emojiItem.appendChild(selectionIndicator);

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = "×";
        deleteBtn.onclick = (e) => {
          e.stopPropagation();
          deleteEmoji(category, emoji);
        };
        emojiItem.appendChild(deleteBtn);

        const editBtnEl = document.createElement("button");
        editBtnEl.className = "edit-btn";
        editBtnEl.innerHTML = "<i class='fas fa-pen'></i>";
        editBtnEl.style.position = "absolute";
        editBtnEl.style.bottom = "5px";
        editBtnEl.style.right = "5px";
        editBtnEl.style.zIndex = "10";
        editBtnEl.style.background = "rgba(0, 0, 0, 0.5)";
        editBtnEl.style.color = "#fff";
        editBtnEl.style.border = "none";
        editBtnEl.style.borderRadius = "3px";
        editBtnEl.style.padding = "2px 5px";
        editBtnEl.style.fontSize = "10px";
        editBtnEl.style.cursor = "pointer";
        editBtnEl.onclick = (e) => {
          e.stopPropagation();
          openEmojiEditModal(emoji);
        };
        emojiItem.appendChild(editBtnEl);

        bindEmojiInteractions(emojiItem, category, emoji);

        emojiItem.setAttribute("data-bg", `/memes/${category}/${emoji}`);
        emojiGrid.appendChild(emojiItem);
      });
    }

    const { uploadBlock, fileInput } = createUploadDropzone(category);

    emojiGrid.appendChild(uploadBlock);
    emojiGrid.appendChild(fileInput);

    categoryDiv.appendChild(emojiGrid);
    attachCategoryDropTarget(categoryDiv, category);
    container.appendChild(categoryDiv);
  });

  const lazyBackgrounds = document.querySelectorAll(".emoji-item");
  const observer = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const emojiItem = entry.target;
          const bgUrl = emojiItem.getAttribute("data-bg");
          emojiItem.style.backgroundImage = `url('${bgUrl}')`;
          emojiItem.removeAttribute("data-bg");
          obs.unobserve(emojiItem);
        }
      });
    },
    { threshold: 0.1 }
  );

  lazyBackgrounds.forEach((item) => {
    observer.observe(item);
  });

  updateSelectionDecorations();
}

export function updateSidebar(data) {
  const sidebarList = document.getElementById("sidebar-list");
  if (!sidebarList) return;
  sidebarList.innerHTML = "";

  for (const category in data) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = "#category-" + category;
    a.textContent = category;
    a.addEventListener("click", () => {
      if (isCompactViewport()) {
        closeSidebar();
      }
    });
    li.appendChild(a);
    sidebarList.appendChild(li);
  }
}

// DragHUD
export function showDragHud({
  label,
  caption,
  progress = 0,
  clientX = null,
  clientY = null,
  state: hudState = "press",
}) {
  const dragHud = elements.dragHud;
  if (!dragHud) return;

  const safeProgress = Math.max(0, Math.min(progress, 1));
  dragHud.classList.remove("hidden");
  dragHud.classList.add("visible");
  dragHud.dataset.state = hudState;
  dragHud.style.setProperty("--drag-hud-progress", `${safeProgress * 360}deg`);
  dragHud.setAttribute("aria-hidden", "false");

  const labelEl = elements.dragHudLabel;
  if (labelEl) {
    labelEl.textContent = label;
  }
  const captionEl = elements.dragHudCaption;
  if (captionEl) {
    captionEl.textContent = caption;
  }
  if (typeof clientX === "number" && typeof clientY === "number") {
    updateDragHudPosition(clientX, clientY);
  }
}

export function hideDragHud() {
  const dragHud = elements.dragHud;
  if (!dragHud) return;

  dragHud.classList.remove("visible");
  dragHud.classList.add("hidden");
  dragHud.dataset.state = "idle";
  dragHud.style.setProperty("--drag-hud-progress", "0deg");
  dragHud.style.transform = "translate3d(-9999px, -9999px, 0)";
  dragHud.setAttribute("aria-hidden", "true");

  const labelEl = elements.dragHudLabel;
  if (labelEl) {
    labelEl.textContent = `${Math.ceil(LONG_PRESS_DURATION_MS / 1000)}s`;
  }
  const captionEl = elements.dragHudCaption;
  if (captionEl) {
    captionEl.textContent = `长按 ${Math.ceil(LONG_PRESS_DURATION_MS / 1000)} 秒进入拖拽`;
  }
}

export function updateDragHudPosition(clientX, clientY) {
  const dragHud = elements.dragHud;
  if (!dragHud) return;

  const hudRect = dragHud.getBoundingClientRect();
  const hudWidth = hudRect.width || 72;
  const hudHeight = hudRect.height || 72;
  const x = Math.min(
    window.innerWidth - hudWidth - 10,
    Math.max(10, clientX + DRAG_HUD_OFFSET_X)
  );
  const y = Math.min(
    window.innerHeight - hudHeight - 10,
    Math.max(10, clientY - DRAG_HUD_OFFSET_Y)
  );

  dragHud.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;
}

export function setLongPressProgress(progress, label) {
  if (!state.longPressState.emojiItem) return;

  showDragHud({
    label,
    caption: `长按 ${Math.ceil(LONG_PRESS_DURATION_MS / 1000)} 秒进入拖拽`,
    progress,
    clientX: state.longPressState.currentX,
    clientY: state.longPressState.currentY,
    state: "press",
  });
}

export function resetLongPressVisual(emojiItem) {
  if (!emojiItem) return;
  emojiItem.classList.remove("long-press-active");
}

import { dedupeEmojiItems, toggleCategorySelection } from "./interactions.js";
