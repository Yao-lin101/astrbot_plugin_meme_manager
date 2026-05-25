// interactions.js - Event listeners, pointer actions, drag-and-drop, clipboard, and selection handling

import { state, pruneSelectionState } from "./state.js";
import {
  elements,
  LONG_PRESS_DURATION_MS,
  LONG_PRESS_TICK_MS,
  LONG_PRESS_CANCEL_DISTANCE_PX,
  DRAG_READY_TIMEOUT_MS,
  showToast,
  createButton,
  createIconButton,
  showDragHud,
  hideDragHud,
  setLongPressProgress,
  resetLongPressVisual,
  closeMoveTargetModal,
  openMoveTargetModal,
  showConfirm,
  showDangerConfirm,
  updateSelectionUI,
  openEmojiEditModal,
} from "./ui.js";
import {
  deleteEmoji as apiDeleteEmoji,
  moveEmojiItemsToCategory as apiMoveEmojiItemsToCategory,
  copyEmojiItemsToCategory as apiCopyEmojiItemsToCategory,
  fetchEmojis,
  refreshUi,
  requestJson,
} from "./api.js";

// Selection keys and helpers
export function createSelectionKey(category, emoji) {
  return `${category}::${emoji}`;
}

export function isEmojiSelected(category, emoji) {
  return state.selectionState.items.has(createSelectionKey(category, emoji));
}

export function getCategorySelectedCount(category) {
  let count = 0;
  state.selectionState.items.forEach((item) => {
    if (item.category === category) {
      count += 1;
    }
  });
  return count;
}

export function dedupeEmojiItems(items) {
  const uniqueItems = new Map();
  (items || []).forEach((item) => {
    if (!item?.category || !item?.emoji) return;
    uniqueItems.set(createSelectionKey(item.category, item.emoji), {
      category: item.category,
      emoji: item.emoji,
    });
  });
  return Array.from(uniqueItems.values());
}

export function getSortedCategories() {
  return Object.keys(state.latestEmojiData).sort((left, right) =>
    left.localeCompare(right, "zh-CN")
  );
}

export function getMoveableCountForTarget(items, targetCategory) {
  if (!targetCategory) return 0;
  return dedupeEmojiItems(items).filter((item) => item.category !== targetCategory).length;
}

export function getAvailableMoveTargets(items = Array.from(state.selectionState.items.values())) {
  const uniqueItems = dedupeEmojiItems(items);
  if (uniqueItems.length === 0) return [];
  return getSortedCategories().filter(
    (category) => getMoveableCountForTarget(uniqueItems, category) > 0
  );
}

export function groupEmojiItemsByCategory(items) {
  const groupedItems = new Map();
  dedupeEmojiItems(items).forEach((item) => {
    if (!groupedItems.has(item.category)) {
      groupedItems.set(item.category, []);
    }
    groupedItems.get(item.category).push(item.emoji);
  });
  return groupedItems;
}

export function setClipboardItems(items) {
  state.clipboardState.items = dedupeEmojiItems(items);
}

export function getClipboardItems() {
  return dedupeEmojiItems(state.clipboardState.items);
}

export function getContextMenuTargetItems(targetEmojiItem) {
  if (!targetEmojiItem) {
    return dedupeEmojiItems(Array.from(state.selectionState.items.values()));
  }

  const targetCategory = targetEmojiItem.dataset.category;
  const targetEmoji = targetEmojiItem.dataset.emoji;
  if (state.selectionState.enabled && isEmojiSelected(targetCategory, targetEmoji)) {
    return dedupeEmojiItems(Array.from(state.selectionState.items.values()));
  }

  return [{ category: targetCategory, emoji: targetEmoji }];
}

export function getPasteableClipboardItems(targetCategory) {
  if (!targetCategory) return [];
  return getClipboardItems().filter((item) => item.category !== targetCategory);
}

// Context Menu Operations
export function closeBatchContextMenu() {
  state.contextMenuState.items = [];
  state.contextMenuState.targetCategory = null;
  const menu = elements.batchContextMenu;
  if (menu) {
    menu.classList.add("hidden");
    menu.setAttribute("aria-hidden", "true");
    menu.style.left = "-9999px";
    menu.style.top = "-9999px";
  }
}

export function openBatchContextMenu(event) {
  const menu = elements.batchContextMenu;
  if (!menu || !state.selectionState.enabled) return;

  closeBatchContextMenu();

  const targetEmojiItem = event.target.closest(".emoji-item");
  const targetCategoryElement = event.target.closest(".category");
  const targetCategory =
    targetEmojiItem?.dataset.category ||
    targetCategoryElement?.dataset.category ||
    null;
  const targetItems = getContextMenuTargetItems(targetEmojiItem);
  const pasteableItems = getPasteableClipboardItems(targetCategory);

  if (targetItems.length === 0 && pasteableItems.length === 0) return;

  state.contextMenuState.items = targetItems;
  state.contextMenuState.targetCategory = targetCategory;

  const title = elements.batchContextMenuTitle;
  if (title) {
    title.textContent =
      targetItems.length > 0 ? `批量管理 ${targetItems.length} 个文件` : "批量管理";
  }
  const subtitle = elements.batchContextMenuSubtitle;
  if (subtitle) {
    if (targetCategory && pasteableItems.length > 0) {
      subtitle.textContent = `当前分类：${targetCategory}，可粘贴 ${pasteableItems.length} 个文件`;
    } else if (targetCategory) {
      subtitle.textContent = `当前分类：${targetCategory}`;
    } else {
      subtitle.textContent = "选择一个操作继续";
    }
  }

  if (elements.contextMenuDeleteBtn) {
    elements.contextMenuDeleteBtn.disabled = targetItems.length === 0;
  }
  if (elements.contextMenuMoveBtn) {
    elements.contextMenuMoveBtn.disabled =
      targetItems.length === 0 || getAvailableMoveTargets(targetItems).length === 0;
  }
  if (elements.contextMenuCopyBtn) {
    elements.contextMenuCopyBtn.disabled = targetItems.length === 0;
  }
  if (elements.contextMenuPasteBtn) {
    elements.contextMenuPasteBtn.disabled = pasteableItems.length === 0 || !targetCategory;
  }

  menu.classList.remove("hidden");
  menu.setAttribute("aria-hidden", "false");

  requestAnimationFrame(() => {
    const menuWidth = menu.offsetWidth || 240;
    const menuHeight = menu.offsetHeight || 220;
    const left = Math.min(
      window.innerWidth - menuWidth - 12,
      Math.max(12, event.clientX)
    );
    const top = Math.min(
      window.innerHeight - menuHeight - 12,
      Math.max(12, event.clientY)
    );
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  });
}

export function shouldOpenBatchContextMenu(event) {
  if (!state.selectionState.enabled || hasActiveDragInteraction()) {
    return false;
  }

  return Boolean(
    event.target.closest(".emoji-item") ||
      event.target.closest(".emoji-upload") ||
      event.target.closest(".category")
  );
}

// Drag & Drop State Helpers
export function getDragItemsForEmoji(category, emoji) {
  if (state.selectionState.enabled && isEmojiSelected(category, emoji)) {
    return dedupeEmojiItems(Array.from(state.selectionState.items.values()));
  }
  return [{ category, emoji }];
}

export function getDragReadyLabel(itemCount) {
  return itemCount > 1 ? `${itemCount}项` : "拖";
}

export function hasActiveDragInteraction() {
  return Boolean(
    state.longPressState.emojiItem ||
      state.dragModeState.pointerId !== null ||
      state.dragModeState.items.length > 0
  );
}

export function syncInteractionGuardState() {
  document.body.classList.toggle("drag-session-active", hasActiveDragInteraction());
}

export function stopDragAutoScroll() {
  if (state.dragModeState.autoScrollFrameId) {
    cancelAnimationFrame(state.dragModeState.autoScrollFrameId);
    state.dragModeState.autoScrollFrameId = null;
  }
}

export function stepDragAutoScroll() {
  if (state.dragModeState.pointerId === null) {
    stopDragAutoScroll();
    return;
  }

  const topThreshold = 96;
  const bottomThreshold = window.innerHeight - 96;
  let deltaY = 0;

  if (state.dragModeState.lastClientY < topThreshold) {
    deltaY = Math.max(-18, (state.dragModeState.lastClientY - topThreshold) * 0.18);
  } else if (state.dragModeState.lastClientY > bottomThreshold) {
    deltaY = Math.min(
      18,
      (state.dragModeState.lastClientY - bottomThreshold) * 0.18
    );
  }

  if (deltaY !== 0) {
    window.scrollBy({ top: deltaY, behavior: "auto" });
    updateActiveDropTarget(
      state.dragModeState.lastClientX,
      state.dragModeState.lastClientY
    );
    showDragHud({
      label: getDragReadyLabel(state.dragModeState.items.length),
      caption: state.dragModeState.activeCategory
        ? `松手后移动到 ${state.dragModeState.activeCategory}`
        : "拖到屏幕边缘可自动滚动",
      progress: 1,
      clientX: state.dragModeState.lastClientX,
      clientY: state.dragModeState.lastClientY,
      state: state.dragModeState.activeCategory ? "target" : "ready",
    });
  }

  state.dragModeState.autoScrollFrameId = requestAnimationFrame(stepDragAutoScroll);
}

export function ensureDragAutoScroll() {
  if (state.dragModeState.autoScrollFrameId) return;
  state.dragModeState.autoScrollFrameId = requestAnimationFrame(stepDragAutoScroll);
}

export function updateActiveDropTarget(clientX, clientY) {
  clearCategoryDropHighlights();
  state.dragModeState.activeCategory = null;

  const hoveredElement = document.elementFromPoint(clientX, clientY);
  const categoryDiv = hoveredElement?.closest(".category");
  const targetCategory = categoryDiv?.dataset?.category;

  if (!categoryDiv || !targetCategory) return;

  if (!hasMoveableItemsForTarget(state.dragModeState.items, targetCategory)) return;

  state.dragModeState.activeCategory = targetCategory;
  categoryDiv.classList.add("category-drop-active");
}

export function startPointerDrag(event) {
  if (state.dragModeState.items.length === 0) return;

  state.dragModeState.pointerId = event.pointerId;
  state.dragModeState.isPointerDragging = false;
  state.dragModeState.activeCategory = null;
  state.dragModeState.captureElement = event.currentTarget;
  state.dragModeState.lastClientX = event.clientX;
  state.dragModeState.lastClientY = event.clientY;
  updateActiveDropTarget(event.clientX, event.clientY);
  ensureDragAutoScroll();
  showDragHud({
    label: getDragReadyLabel(state.dragModeState.items.length),
    caption: "拖到目标分类，松手即可移动",
    progress: 1,
    clientX: event.clientX,
    clientY: event.clientY,
    state: "ready",
  });
}

export function updatePointerDrag(event) {
  if (
    state.dragModeState.pointerId === null ||
    state.dragModeState.pointerId !== event.pointerId ||
    state.dragModeState.items.length === 0
  ) {
    return;
  }

  state.dragModeState.isPointerDragging = true;
  state.dragModeState.lastClientX = event.clientX;
  state.dragModeState.lastClientY = event.clientY;
  updateActiveDropTarget(event.clientX, event.clientY);
  showDragHud({
    label: getDragReadyLabel(state.dragModeState.items.length),
    caption: state.dragModeState.activeCategory
      ? `松手后移动到 ${state.dragModeState.activeCategory}`
      : "拖到目标分类，松手即可移动",
    progress: 1,
    clientX: event.clientX,
    clientY: event.clientY,
    state: state.dragModeState.activeCategory ? "target" : "ready",
  });
}

export async function finishPointerDrag(event) {
  if (
    state.dragModeState.pointerId === null ||
    state.dragModeState.pointerId !== event.pointerId
  ) {
    return;
  }

  const targetCategory = state.dragModeState.activeCategory;
  const dragItems = dedupeEmojiItems(state.dragModeState.items);
  const wasDragging = state.dragModeState.isPointerDragging;

  state.dragModeState.pointerId = null;
  state.dragModeState.activeCategory = null;
  state.dragModeState.isPointerDragging = false;
  state.dragModeState.lastClientX = 0;
  state.dragModeState.lastClientY = 0;
  stopDragAutoScroll();
  if (
    state.dragModeState.captureElement &&
    typeof event.pointerId === "number" &&
    typeof state.dragModeState.captureElement.releasePointerCapture === "function"
  ) {
    try {
      state.dragModeState.captureElement.releasePointerCapture(event.pointerId);
    } catch {}
  }
  state.dragModeState.captureElement = null;
  clearCategoryDropHighlights();
  hideDragHud();
  syncInteractionGuardState();

  if (targetCategory && hasMoveableItemsForTarget(dragItems, targetCategory)) {
    await moveEmojiItemsToCategory(targetCategory, dragItems);
    return;
  }

  if (wasDragging) {
    clearDragMode();
    showToast(
      "未拖到有效分类，已取消本次移动。",
      "warning",
      "拖拽未完成"
    );
    return;
  }

  if (event.pointerType !== "mouse" && dragItems.length > 0) {
    showToast(
      "拖拽模式已开启，继续拖到目标分类即可移动。",
      "info",
      "等待拖拽"
    );
  }
}

export function clearDragMode() {
  cancelLongPress({ keepHud: true });

  if (state.dragModeState.timeoutId) {
    clearTimeout(state.dragModeState.timeoutId);
    state.dragModeState.timeoutId = null;
  }

  stopDragAutoScroll();
  if (
    state.dragModeState.captureElement &&
    typeof state.dragModeState.pointerId === "number" &&
    typeof state.dragModeState.captureElement.releasePointerCapture === "function"
  ) {
    try {
      state.dragModeState.captureElement.releasePointerCapture(state.dragModeState.pointerId);
    } catch {}
  }

  state.dragModeState.items = [];
  state.dragModeState.pointerId = null;
  state.dragModeState.activeCategory = null;
  state.dragModeState.isPointerDragging = false;
  state.dragModeState.captureElement = null;
  state.dragModeState.lastClientX = 0;
  state.dragModeState.lastClientY = 0;
  document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
    emojiItem.classList.remove("drag-ready", "dragging");
    resetLongPressVisual(emojiItem);
  });
  clearCategoryDropHighlights();
  hideDragHud();
  syncInteractionGuardState();
}

export function armDragMode(items, pointerContext = {}) {
  const dragItems = dedupeEmojiItems(items);
  if (dragItems.length === 0) return;

  clearDragMode();
  state.dragModeState.items = dragItems;
  const armedKeys = new Set(
    dragItems.map(({ category, emoji }) => createSelectionKey(category, emoji))
  );

  document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
    const emojiKey = createSelectionKey(
      emojiItem.dataset.category,
      emojiItem.dataset.emoji
    );
    const armed = armedKeys.has(emojiKey);
    emojiItem.classList.toggle("drag-ready", armed);
    resetLongPressVisual(emojiItem);
  });

  if (
    typeof pointerContext.clientX === "number" &&
    typeof pointerContext.clientY === "number"
  ) {
    state.dragModeState.pointerId =
      typeof pointerContext.pointerId === "number"
        ? pointerContext.pointerId
        : null;
    state.dragModeState.captureElement = pointerContext.sourceElement || null;
    state.dragModeState.lastClientX = pointerContext.clientX;
    state.dragModeState.lastClientY = pointerContext.clientY;
    if (
      state.dragModeState.captureElement &&
      state.dragModeState.pointerId !== null &&
      typeof state.dragModeState.captureElement.setPointerCapture === "function"
    ) {
      try {
        state.dragModeState.captureElement.setPointerCapture(state.dragModeState.pointerId);
      } catch {}
    }
    ensureDragAutoScroll();
    showDragHud({
      label: getDragReadyLabel(dragItems.length),
      caption: "拖到目标分类，松手即可移动",
      progress: 1,
      clientX: pointerContext.clientX,
      clientY: pointerContext.clientY,
      state: "ready",
    });
  }

  syncInteractionGuardState();

  state.dragModeState.timeoutId = window.setTimeout(() => {
    clearDragMode();
    showToast("拖拽模式已自动退出，请重新长按进入。", "info", "拖拽模式已结束");
  }, DRAG_READY_TIMEOUT_MS);

  showToast(
    dragItems.length > 1
      ? `已进入拖拽模式，可拖动这 ${dragItems.length} 个表情包到目标分类。`
      : "已进入拖拽模式，可将表情包拖到目标分类。",
    "success",
    "拖拽模式已开启"
  );
}

// Long Press Logic
export function startLongPress(emojiItem, category, emoji, event) {
  if (
    (event.pointerType === "mouse" && event.button !== 0) ||
    event.target.closest(".delete-btn") ||
    event.target.closest(".edit-btn")
  ) {
    return;
  }

  if (
    emojiItem.classList.contains("drag-ready") &&
    state.dragModeState.items.length > 0
  ) {
    emojiItem.dataset.suppressClick = "true";
    if (typeof emojiItem.setPointerCapture === "function") {
      try {
        emojiItem.setPointerCapture(event.pointerId);
      } catch {}
    }
    startPointerDrag(event);
    return;
  }

  const dragItems = getDragItemsForEmoji(category, emoji);
  if (dragItems.length === 0) return;

  cancelLongPress();
  if (
    state.dragModeState.items.length > 0 &&
    !emojiItem.classList.contains("drag-ready")
  ) {
    clearDragMode();
  }

  state.longPressState.emojiItem = emojiItem;
  state.longPressState.pointerId = event.pointerId;
  state.longPressState.startTime = performance.now();
  state.longPressState.startX = event.clientX;
  state.longPressState.startY = event.clientY;
  state.longPressState.currentX = event.clientX;
  state.longPressState.currentY = event.clientY;

  emojiItem.classList.add("long-press-active");
  syncInteractionGuardState();
  setLongPressProgress(
    0,
    `${Math.ceil(LONG_PRESS_DURATION_MS / 1000)}s`
  );

  state.longPressState.intervalId = window.setInterval(() => {
    if (!state.longPressState.emojiItem) return;

    const elapsed = performance.now() - state.longPressState.startTime;
    const progress = elapsed / LONG_PRESS_DURATION_MS;
    const remainingSeconds = Math.max(
      1,
      Math.ceil((LONG_PRESS_DURATION_MS - elapsed) / 1000)
    );
    setLongPressProgress(
      progress,
      `${remainingSeconds}s`
    );
  }, LONG_PRESS_TICK_MS);

  state.longPressState.timeoutId = window.setTimeout(() => {
    emojiItem.dataset.suppressClick = "true";
    const pointerContext = {
      pointerId: state.longPressState.pointerId,
      clientX: state.longPressState.currentX,
      clientY: state.longPressState.currentY,
      sourceElement: emojiItem,
    };
    cancelLongPress({ preserveReady: true, keepHud: true });
    armDragMode(dragItems, pointerContext);
  }, LONG_PRESS_DURATION_MS);
}

export function finishLongPress(event) {
  if (
    !state.longPressState.emojiItem ||
    (typeof event.pointerId === "number" &&
      state.longPressState.pointerId !== null &&
      event.pointerId !== state.longPressState.pointerId)
  ) {
    return;
  }

  cancelLongPress();
}

export function cancelLongPress({ preserveReady = false, keepHud = false } = {}) {
  if (state.longPressState.timeoutId) {
    clearTimeout(state.longPressState.timeoutId);
    state.longPressState.timeoutId = null;
  }
  if (state.longPressState.intervalId) {
    clearInterval(state.longPressState.intervalId);
    state.longPressState.intervalId = null;
  }
  if (state.longPressState.emojiItem) {
    state.longPressState.emojiItem.classList.remove("long-press-active");
    if (!preserveReady) {
      resetLongPressVisual(state.longPressState.emojiItem);
    }
  }

  state.longPressState.emojiItem = null;
  state.longPressState.pointerId = null;
  state.longPressState.startTime = 0;
  state.longPressState.startX = 0;
  state.longPressState.startY = 0;
  state.longPressState.currentX = 0;
  state.longPressState.currentY = 0;

  if (!keepHud && state.dragModeState.pointerId === null) {
    hideDragHud();
  }

  syncInteractionGuardState();
}

export function isInternalEmojiDrag(event) {
  const dragTypes = Array.from(event.dataTransfer?.types || []);
  return dragTypes.includes("application/x-meme-emoji");
}

export function getDraggedEmojiPayload(event) {
  try {
    const rawPayload = event.dataTransfer?.getData("application/x-meme-emoji");
    if (!rawPayload) return null;
    const payload = JSON.parse(rawPayload);
    if (Array.isArray(payload?.items) && payload.items.length > 0) {
      const items = dedupeEmojiItems(payload.items);
      return items.length > 0 ? { items } : null;
    }
    if (!payload?.category || !payload?.emoji) return null;
    return { items: [{ category: payload.category, emoji: payload.emoji }] };
  } catch {
    return null;
  }
}

export function hasMoveableItemsForTarget(items, targetCategory) {
  return dedupeEmojiItems(items).some(
    (item) => item.category !== targetCategory
  );
}

export function clearCategoryDropHighlights() {
  document.querySelectorAll(".category-drop-active").forEach((categoryDiv) => {
    categoryDiv.classList.remove("category-drop-active");
  });
}

// Upload helpers
export function normalizeUploadFiles(fileList) {
  const validFiles = [];
  let invalidCount = 0;

  Array.from(fileList || []).forEach((file) => {
    const isImageFile =
      file instanceof File &&
      (file.type.startsWith("image/") ||
        /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name));

    if (isImageFile) {
      validFiles.push(file);
      return;
    }
    invalidCount += 1;
  });

  return { validFiles, invalidCount };
}

export function dedupeUploadFiles(files) {
  const uniqueFiles = [];
  const seenSignatures = new Set();
  let duplicateCount = 0;

  files.forEach((file) => {
    const signature = [
      file.name,
      file.size,
      file.lastModified,
      file.type,
    ].join("::");

    if (seenSignatures.has(signature)) {
      duplicateCount += 1;
      return;
    }

    seenSignatures.add(signature);
    uniqueFiles.push(file);
  });

  return { uniqueFiles, duplicateCount };
}

export function refreshUploadDropzones(category = null) {
  document.querySelectorAll(".emoji-upload").forEach((uploadBlock) => {
    if (category && uploadBlock.dataset.category !== category) return;

    const uploadTitle = uploadBlock.querySelector(".emoji-upload-title");
    const uploadHint = uploadBlock.querySelector(".emoji-upload-hint");
    const uploadMeta = uploadBlock.querySelector(".emoji-upload-meta");
    const uploadProgress = uploadBlock.querySelector(".emoji-upload-progress");
    const uploadProgressBar = uploadBlock.querySelector(".emoji-upload-progress-bar");
    const uploadIconInner = uploadBlock.querySelector(".emoji-upload-icon i");

    if (
      !uploadTitle ||
      !uploadHint ||
      !uploadMeta ||
      !uploadProgress ||
      !uploadProgressBar ||
      !uploadIconInner
    ) {
      return;
    }

    const uploadState = state.uploadStateByCategory.get(uploadBlock.dataset.category);

    if (!uploadState) {
      uploadBlock.classList.remove("uploading");
      uploadBlock.setAttribute("aria-busy", "false");
      uploadTitle.textContent = "上传表情包";
      uploadHint.textContent = "点击上传图片，或将表情长按 3 秒后拖到这里";
      uploadMeta.textContent = "";
      uploadMeta.classList.add("hidden");
      uploadProgress.classList.add("hidden");
      uploadProgressBar.style.width = "0%";
      uploadIconInner.className = "fas fa-cloud-arrow-up";
      return;
    }

    const processedCount = uploadState.completed + uploadState.failed + uploadState.duplicates;
    const currentIndex = Math.min(processedCount + 1, uploadState.total);
    const progressPercent =
      uploadState.total > 0 ? Math.round((processedCount / uploadState.total) * 100) : 0;

    uploadBlock.classList.add("uploading");
    uploadBlock.setAttribute("aria-busy", "true");
    uploadIconInner.className = "fas fa-spinner fa-spin";
    uploadMeta.classList.remove("hidden");
    uploadProgress.classList.remove("hidden");
    uploadProgressBar.style.width = `${progressPercent}%`;

    if (uploadState.refreshing) {
      uploadTitle.textContent = "正在刷新列表";
      uploadHint.textContent = `已处理 ${uploadState.total} 个文件，正在更新界面`;
    } else {
      uploadTitle.textContent = `正在上传 ${currentIndex}/${uploadState.total}`;
      uploadHint.textContent = uploadState.currentFileName
        ? `当前文件：${uploadState.currentFileName}`
        : "正在准备上传文件";
    }

    const metaParts = [`已完成 ${processedCount}/${uploadState.total}`];
    if (uploadState.duplicates > 0) metaParts.push(`重复 ${uploadState.duplicates}`);
    if (uploadState.failed > 0) metaParts.push(`失败 ${uploadState.failed}`);
    uploadMeta.textContent = metaParts.join("，");
  });
}

export function isCategoryUploading(category) {
  return state.uploadStateByCategory.has(category);
}

export async function uploadEmoji(category, file) {
  const formData = new FormData();
  formData.append("category", category);
  formData.append("image_file", file);

  return requestJson(
    "/api/emoji/add",
    {
      method: "POST",
      body: formData,
    },
    { defaultErrorMessage: "上传失败，服务器返回错误" }
  );
}

export async function uploadFilesToCategory(category, fileList) {
  const { validFiles, invalidCount } = normalizeUploadFiles(fileList);

  if (invalidCount > 0) {
    showToast(
      `已忽略 ${invalidCount} 个非图片文件。`,
      "warning",
      "文件类型不支持"
    );
  }

  if (validFiles.length === 0) return;

  const { uniqueFiles, duplicateCount } = dedupeUploadFiles(validFiles);

  if (duplicateCount > 0) {
    showToast(
      `已忽略本批次中 ${duplicateCount} 个重复文件。`,
      "info",
      "已自动去重"
    );
  }

  if (uniqueFiles.length === 0) return;

  if (isCategoryUploading(category)) {
    showToast(
      `分类 ${category} 正在上传文件，请等待当前批次完成。`,
      "info",
      "上传进行中"
    );
    return;
  }

  const uploadState = {
    total: uniqueFiles.length,
    completed: 0,
    failed: 0,
    duplicates: 0,
    currentFileName: uniqueFiles[0]?.name || "",
    refreshing: false,
  };
  state.uploadStateByCategory.set(category, uploadState);
  refreshUploadDropzones(category);

  showToast(
    uniqueFiles.length > 1
      ? `开始向 ${category} 上传 ${uniqueFiles.length} 个文件。`
      : `开始向 ${category} 上传 1 个文件。`,
    "info",
    "上传开始",
    2200
  );

  const failedUploads = [];
  const duplicateUploads = [];

  for (const file of uniqueFiles) {
    uploadState.currentFileName = file.name;
    refreshUploadDropzones(category);

    try {
      await uploadEmoji(category, file);
      uploadState.completed += 1;
    } catch (error) {
      if (error.code === "duplicate_emoji" || error.status === 409) {
        uploadState.duplicates += 1;
        duplicateUploads.push({ fileName: file.name, error });
      } else {
        uploadState.failed += 1;
        failedUploads.push({ fileName: file.name, error });
      }
    }

    refreshUploadDropzones(category);
  }

  if (uploadState.completed > 0) {
    uploadState.refreshing = true;
    uploadState.currentFileName = "";
    refreshUploadDropzones(category);
    await refreshUi({ emojis: true });
  }

  state.uploadStateByCategory.delete(category);
  refreshUploadDropzones(category);

  if (uploadState.failed === 0 && uploadState.duplicates === 0) {
    showToast(
      uploadState.completed > 1
        ? `已向 ${category} 上传 ${uploadState.completed} 个文件。`
        : `已向 ${category} 上传 1 个文件。`,
      "success",
      "上传成功"
    );
    return;
  }

  if (uploadState.completed > 0 && uploadState.failed === 0) {
    showToast(
      `上传完成，新增 ${uploadState.completed} 个，跳过重复 ${uploadState.duplicates} 个。`,
      "warning",
      "上传已去重",
      4500
    );
    return;
  }

  if (
    uploadState.completed === 0 &&
    uploadState.duplicates > 0 &&
    uploadState.failed === 0
  ) {
    const firstDuplicateMessage =
      duplicateUploads[0]?.error?.message || "这些文件已存在于当前分类";
    showToast(
      `未新增文件，已跳过 ${uploadState.duplicates} 个重复项：${firstDuplicateMessage}`,
      "info",
      "无需重复上传",
      4500
    );
    return;
  }

  if (uploadState.completed > 0) {
    showToast(
      `上传完成，成功 ${uploadState.completed} 个，重复 ${uploadState.duplicates} 个，失败 ${uploadState.failed} 个。`,
      "warning",
      "部分上传失败",
      4500
    );
    return;
  }

  const firstErrorMessage =
    failedUploads[0]?.error?.message || "服务器返回错误";
  showToast(
    `本次上传全部失败：${firstErrorMessage}`,
    "error",
    "上传失败",
    4500
  );
}

export function createUploadDropzone(category) {
  const uploadBlock = document.createElement("div");
  uploadBlock.className = "emoji-upload";
  uploadBlock.dataset.category = category;
  uploadBlock.tabIndex = 0;
  uploadBlock.setAttribute("role", "button");
  uploadBlock.setAttribute(
    "aria-label",
    `上传 ${category} 分类表情包，支持点击选择或拖拽图片`
  );

  const uploadIcon = document.createElement("div");
  uploadIcon.className = "emoji-upload-icon";
  const uploadIconInner = document.createElement("i");
  uploadIconInner.className = "fas fa-cloud-arrow-up";
  uploadIcon.appendChild(uploadIconInner);

  const uploadTitle = document.createElement("div");
  uploadTitle.className = "emoji-upload-title";
  uploadTitle.textContent = "上传表情包";

  const uploadHint = document.createElement("div");
  uploadHint.className = "emoji-upload-hint";
  uploadHint.textContent = "点击上传图片，或将表情长按 3 秒后拖到这里";

  const uploadMeta = document.createElement("div");
  uploadMeta.className = "emoji-upload-meta hidden";

  const uploadProgress = document.createElement("div");
  uploadProgress.className = "emoji-upload-progress hidden";
  const uploadProgressBar = document.createElement("span");
  uploadProgressBar.className = "emoji-upload-progress-bar";
  uploadProgress.appendChild(uploadProgressBar);

  uploadBlock.appendChild(uploadIcon);
  uploadBlock.appendChild(uploadTitle);
  uploadBlock.appendChild(uploadHint);
  uploadBlock.appendChild(uploadMeta);
  uploadBlock.appendChild(uploadProgress);

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.style.display = "none";
  fileInput.accept = "image/*";
  fileInput.multiple = true;

  let dragDepth = 0;

  const setDragState = (active) => {
    uploadBlock.classList.toggle("drag-active", active);
  };

  uploadBlock.addEventListener("click", () => {
    if (isCategoryUploading(category)) {
      showToast(
        `分类 ${category} 正在上传文件，请稍候。`,
        "info",
        "上传进行中"
      );
      return;
    }
    fileInput.click();
  });

  uploadBlock.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (isCategoryUploading(category)) {
        showToast(
          `分类 ${category} 正在上传文件，请稍候。`,
          "info",
          "上传进行中"
        );
        return;
      }
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", (event) => {
    void uploadFilesToCategory(category, event.target.files);
    fileInput.value = "";
  });

  uploadBlock.addEventListener("dragenter", (event) => {
    if (isInternalEmojiDrag(event)) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    dragDepth += 1;
    setDragState(true);
  });

  uploadBlock.addEventListener("dragover", (event) => {
    if (isInternalEmojiDrag(event)) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
    setDragState(true);
  });

  uploadBlock.addEventListener("dragleave", (event) => {
    if (isInternalEmojiDrag(event)) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      setDragState(false);
    }
  });

  uploadBlock.addEventListener("drop", (event) => {
    if (isInternalEmojiDrag(event)) {
      event.preventDefault();
      dragDepth = 0;
      setDragState(false);
      return;
    }
    event.preventDefault();
    dragDepth = 0;
    setDragState(false);
    if (isCategoryUploading(category)) {
      showToast(
        `分类 ${category} 正在上传文件，请等待当前批次完成。`,
        "info",
        "上传进行中"
      );
      return;
    }
    void uploadFilesToCategory(category, event.dataTransfer?.files);
  });

  refreshUploadDropzones(category);

  return { uploadBlock, fileInput };
}

export function bindEmojiInteractions(emojiItem, category, emoji) {
  const selectionIndicator = emojiItem.querySelector(".selection-indicator");
  if (selectionIndicator) {
    selectionIndicator.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
    });
    selectionIndicator.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!state.selectionState.enabled) {
        setSelectionMode(true);
      }
      toggleEmojiSelection(category, emoji);
    });
  }

  emojiItem.addEventListener("click", () => {
    if (emojiItem.dataset.suppressClick === "true") {
      emojiItem.dataset.suppressClick = "false";
      return;
    }
    if (!state.selectionState.enabled) return;
    toggleEmojiSelection(category, emoji);
  });

  emojiItem.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    openEmojiEditModal(emoji);
  });

  emojiItem.addEventListener("keydown", (event) => {
    if (!state.selectionState.enabled) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleEmojiSelection(category, emoji);
    }
  });

  emojiItem.addEventListener("pointerdown", (event) => {
    startLongPress(emojiItem, category, emoji, event);
  });
}

export function attachCategoryDropTarget(categoryDiv, category) {
  let dragDepth = 0;

  const setActive = (active) => {
    categoryDiv.classList.toggle("category-drop-active", active);
  };

  categoryDiv.addEventListener("dragenter", (event) => {
    if (!isInternalEmojiDrag(event)) return;

    const payload = getDraggedEmojiPayload(event);
    if (!payload || !hasMoveableItemsForTarget(payload.items, category)) return;

    event.preventDefault();
    dragDepth += 1;
    setActive(true);
  });

  categoryDiv.addEventListener("dragover", (event) => {
    if (!isInternalEmojiDrag(event)) return;

    const payload = getDraggedEmojiPayload(event);
    if (!payload || !hasMoveableItemsForTarget(payload.items, category)) return;

    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    setActive(true);
  });

  categoryDiv.addEventListener("dragleave", (event) => {
    if (!isInternalEmojiDrag(event)) return;

    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      setActive(false);
    }
  });

  categoryDiv.addEventListener("drop", async (event) => {
    if (!isInternalEmojiDrag(event)) return;

    const payload = getDraggedEmojiPayload(event);
    dragDepth = 0;
    setActive(false);
    if (!payload || !hasMoveableItemsForTarget(payload.items, category)) return;

    event.preventDefault();
    await moveEmojiItemsToCategory(category, payload.items);
  });
}

export async function deleteEmoji(category, emoji) {
  const confirmed = await showConfirm({
    title: "删除表情包",
    description: `确认删除分类「${category}」中的表情包「${emoji}」？此操作不可恢复。`,
    confirmLabel: "确认删除",
    confirmClassName: "danger",
  });
  if (!confirmed) return;

  try {
    const data = await requestJson(
      "/api/emoji/delete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, image_file: emoji }),
      },
      { defaultErrorMessage: "删除表情包失败" }
    );
    state.selectionState.items.delete(createSelectionKey(category, emoji));
    await refreshUi({ emojis: true });
    showToast(
      `已从 ${data.category} 删除 ${data.filename}`,
      "success",
      "删除成功"
    );
  } catch (error) {
    console.error("删除表情包失败", error);
    showToast(`删除表情包失败：${error.message}`, "error", "删除失败", 4500);
  }
}

export async function deleteEmojiItems(
  items,
  { useSelectionState = true, confirmMode = "normal" } = {}
) {
  const uniqueItems = dedupeEmojiItems(items);
  const selectedCount = uniqueItems.length;
  if (selectedCount === 0) {
    showToast("请先选择要删除的表情包", "warning", "未选择项目");
    return;
  }

  const confirmDescription = `确认删除已选中的 ${selectedCount} 个表情包？未成功删除的项目会保留选中状态。`;
  const confirmed =
    confirmMode === "danger"
      ? await showDangerConfirm({
          title: "批量删除表情包",
          description: confirmDescription,
          actionLabel: "确认删除已选文件",
          countdown: 5,
        })
      : await showConfirm({
          title: "批量删除表情包",
          description: confirmDescription,
          confirmLabel: "确认批量删除",
          confirmClassName: "danger",
        });
  if (!confirmed) return;

  let deletedCount = 0;
  const errors = [];
  const deletedKeys = [];
  const groupedSelections = groupEmojiItemsByCategory(uniqueItems);

  for (const [category, imageFiles] of groupedSelections.entries()) {
    try {
      const data = await requestJson(
        "/api/emoji/batch_delete",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, image_files: imageFiles }),
        },
        { defaultErrorMessage: `批量删除失败: ${category}` }
      );
      deletedCount += data.deleted_count || 0;
      (data.deleted_files || []).forEach((filename) => {
        deletedKeys.push(createSelectionKey(category, filename));
      });
    } catch (error) {
      console.error("批量删除失败", error);
      errors.push(`${category}: ${error.message}`);
    }
  }

  if (useSelectionState) {
    deletedKeys.forEach((selectionKey) => {
      state.selectionState.items.delete(selectionKey);
    });
  }

  if (deletedCount > 0) {
    await refreshUi({ emojis: true });
  } else {
    updateSelectionUI();
  }

  if (errors.length > 0) {
    showToast(
      `已删除 ${deletedCount} 个表情包。\n失败分类：${errors.join("；")}`,
      "warning",
      "批量删除部分完成",
      5200
    );
    return;
  }

  showToast(
    `已删除 ${deletedCount} 个表情包`,
    "success",
    "批量删除完成"
  );
}

export async function batchDeleteSelected() {
  await deleteEmojiItems(Array.from(state.selectionState.items.values()));
}

export async function deleteCategory(category) {
  const emojiCount = Array.isArray(state.latestEmojiData[category])
    ? state.latestEmojiData[category].length
    : 0;

  const confirmed = await showDangerConfirm({
    title: `删除分类「${category}」`,
    description: `该操作会删除分类「${category}」本身，并移除其描述配置${
      emojiCount > 0 ? `，同时删除其中的 ${emojiCount} 个表情包` : ""
    }。`,
    actionLabel: "确认删除当前分类",
    countdown: 5,
  });
  if (!confirmed) return;

  try {
    await requestJson(
      "/api/category/delete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: "删除分类失败" }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(`已删除分类 ${category}`, "success", "删除成功");
  } catch (error) {
    console.error("删除分类失败:", error);
    showToast(`删除分类失败：${error.message}`, "error", "删除失败", 4500);
  }
}

export async function clearCategory(category) {
  const emojiCount = Array.isArray(state.latestEmojiData[category])
    ? state.latestEmojiData[category].length
    : 0;
  if (emojiCount === 0) {
    showToast(
      `分类 ${category} 当前没有可清空的表情包`,
      "warning",
      "无需清空"
    );
    return;
  }

  const confirmed = await showDangerConfirm({
    title: `清空分类「${category}」`,
    description: `该操作会删除分类「${category}」下的 ${emojiCount} 个表情包，但会保留分类名称和描述配置。`,
    actionLabel: "确认清空当前分类",
    countdown: 5,
  });
  if (!confirmed) return;

  try {
    const data = await requestJson(
      "/api/category/clear",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: "清空分类失败" }
    );
    clearSelections();
    await refreshUi({ emojis: true });
    showToast(
      `已清空分类 ${category}，删除 ${data.deleted_count} 个表情包。`,
      "success",
      "清空成功"
    );
  } catch (error) {
    console.error("清空分类失败:", error);
    showToast(`清空分类失败：${error.message}`, "error", "清空失败", 4500);
  }
}

export async function clearAllEmojiFiles() {
  const totalEmojiCount = Object.values(state.latestEmojiData).reduce(
    (sum, emojis) => sum + (Array.isArray(emojis) ? emojis.length : 0),
    0
  );
  if (totalEmojiCount === 0) {
    showToast("当前没有可清空的表情包", "warning", "无需清空");
    return;
  }

  const confirmed = await showDangerConfirm({
    title: "清空全部表情包",
    description: `该操作会删除全部 ${totalEmojiCount} 个表情包，但保留现有分类目录和描述配置。`,
    actionLabel: "确认清空全部表情包",
    countdown: 5,
  });
  if (!confirmed) return;

  try {
    const data = await requestJson(
      "/api/emoji/clear_all",
      {
        method: "POST",
      },
      { defaultErrorMessage: "清空全部表情包失败" }
    );
    clearSelections();
    await refreshUi({ emojis: true });
    showToast(
      `已清空全部表情包，共删除 ${data.deleted_count} 个文件，涉及 ${data.affected_categories} 个分类。`,
      "success",
      "清空成功",
      4200
    );
  } catch (error) {
    console.error("清空全部表情包失败:", error);
    showToast(
      `清空全部表情包失败：${error.message}`,
      "error",
      "清空失败",
      4500
    );
  }
}

export function clearSelections() {
  clearDragMode();
  closeMoveTargetModal();
  closeBatchContextMenu();
  state.selectionState.items.clear();
  updateSelectionUI();
}

export function setSelectionMode(enabled) {
  clearDragMode();
  closeMoveTargetModal();
  closeBatchContextMenu();
  state.selectionState.enabled = enabled;
  if (!enabled) {
    state.selectionState.items.clear();
  }
  updateSelectionUI();
}

export function toggleEmojiSelection(category, emoji) {
  clearDragMode();
  closeMoveTargetModal();
  closeBatchContextMenu();
  const selectionKey = createSelectionKey(category, emoji);
  if (state.selectionState.items.has(selectionKey)) {
    state.selectionState.items.delete(selectionKey);
  } else {
    state.selectionState.items.set(selectionKey, { category, emoji });
  }
  updateSelectionUI();
}

export function toggleCategorySelection(category, emojis) {
  if (!Array.isArray(emojis) || emojis.length === 0) return;

  clearDragMode();
  closeMoveTargetModal();
  closeBatchContextMenu();
  if (!state.selectionState.enabled) {
    setSelectionMode(true);
  }

  const allSelected = emojis.every((emoji) => isEmojiSelected(category, emoji));
  emojis.forEach((emoji) => {
    const selectionKey = createSelectionKey(category, emoji);
    if (allSelected) {
      state.selectionState.items.delete(selectionKey);
    } else {
      state.selectionState.items.set(selectionKey, { category, emoji });
    }
  });
  updateSelectionUI();
}

export function copyEmojiItemsToCategory(targetCategory, items) {
  return apiCopyEmojiItemsToCategory(targetCategory, items);
}

export function moveEmojiItemsToCategory(targetCategory, items) {
  return apiMoveEmojiItemsToCategory(targetCategory, items);
}

export function copyItemsToClipboard(items) {
  const uniqueItems = dedupeEmojiItems(items);
  if (uniqueItems.length === 0) {
    showToast("请先选择要复制的表情包。", "warning", "未选择项目");
    return false;
  }

  setClipboardItems(uniqueItems);
  showToast(
    uniqueItems.length > 1
      ? `已复制 ${uniqueItems.length} 个表情包，可在目标分类右键后粘贴。`
      : "已复制 1 个表情包，可在目标分类右键后粘贴。",
    "success",
    "已复制到批量剪贴板"
  );
  return true;
}
