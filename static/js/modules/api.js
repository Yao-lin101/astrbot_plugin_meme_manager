// api.js - API client operations and request state handling

import { state, pruneSelectionState } from "./state.js";
import {
  showToast,
  setButtonBusy,
  restoreButton,
  clearDragMode,
  closeBatchContextMenu,
  displayCategories,
  updateSidebar,
  updateSelectionUI,
  renderSyncStatus,
  renderSyncStatusError,
  normalizeSyncDifferences,
  formatBytes,
  closeMoveTargetModal,
  closeCategoryEditModal,
  closeEmojiEditModal,
} from "./ui.js";

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function startLatestRequest(key) {
  const reqState = state.requestState[key];
  reqState.controller?.abort();
  reqState.seq += 1;
  reqState.controller = new AbortController();
  return {
    seq: reqState.seq,
    controller: reqState.controller,
  };
}

export function isLatestRequest(key, requestToken) {
  const reqState = state.requestState[key];
  return reqState.seq === requestToken.seq && reqState.controller === requestToken.controller;
}

export function finishLatestRequest(key, requestToken) {
  const reqState = state.requestState[key];
  if (reqState.controller === requestToken.controller) {
    reqState.controller = null;
  }
}

export function cancelAllPendingRequests() {
  Object.values(state.requestState).forEach((reqState) => {
    reqState.controller?.abort();
    reqState.controller = null;
  });
  if (state.initialStatusTimerId) {
    clearTimeout(state.initialStatusTimerId);
    state.initialStatusTimerId = null;
  }
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  return {
    message:
      text.startsWith("<!DOCTYPE") || text.startsWith("<html")
        ? "服务器返回了错误页面，请联系管理员"
        : text,
  };
}

export async function requestJson(
  url,
  options = {},
  { defaultErrorMessage = "请求失败" } = {}
) {
  const response = await fetch(url, options);
  const payload = await parseResponsePayload(response).catch(() => ({}));

  if (!response.ok) {
    const error = new Error(payload.message || defaultErrorMessage);
    error.status = response.status;
    error.code = payload.code || null;
    error.payload = payload;
    throw error;
  }

  return payload;
}

export async function fetchEmojis() {
  const requestToken = startLatestRequest("emojis");
  try {
    const personaFilter = document.getElementById("persona-filter");
    const personaId = personaFilter ? personaFilter.value : "";
    const url = personaId ? `/api/emoji?persona_id=${encodeURIComponent(personaId)}` : "/api/emoji";
    const [emojiResponse, tagDescriptions] = await Promise.all([
      fetch(url, { signal: requestToken.controller.signal }).then((res) => {
        if (!res.ok) throw new Error("获取表情包数据失败");
        return res.json();
      }),
      fetch("/api/emotions", {
        signal: requestToken.controller.signal,
      }).then((res) => {
        if (!res.ok) throw new Error("获取标签描述失败");
        return res.json();
      }),
    ]);

    if (!isLatestRequest("emojis", requestToken)) {
      return;
    }
    clearDragMode();
    closeBatchContextMenu();
    state.latestEmojiData = emojiResponse;
    pruneSelectionState();
    displayCategories(emojiResponse, tagDescriptions);
    updateSidebar(emojiResponse, tagDescriptions);
    updateSelectionUI();
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    console.error("加载表情包数据失败", error);
  } finally {
    finishLatestRequest("emojis", requestToken);
  }
}

export async function fetchPersonas() {
  try {
    const res = await fetch("/api/personas");
    if (!res.ok) throw new Error("获取人格列表失败");
    state.systemPersonas = await res.json();
    populatePersonaSelector();
  } catch (e) {
    console.error("加载系统人格失败", e);
  }
}

function populatePersonaSelector() {
  const filterSelect = document.getElementById("persona-filter");
  if (!filterSelect) return;
  
  filterSelect.innerHTML = '<option value="">全部 / 全局</option>';
  
  state.systemPersonas.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.id})`;
    filterSelect.appendChild(opt);
  });
}

export async function checkSyncStatus(showAlert = true) {
  const statusDiv = document.getElementById("sync-status");
  if (!statusDiv) return;

  const btn = document.getElementById("check-sync-btn");
  setButtonBusy(btn, "正在检查中...");
  const requestToken = startLatestRequest("syncStatus");

  try {
    const data = await requestJson(
      "/api/sync/status",
      { signal: requestToken.controller.signal },
      {
        defaultErrorMessage: "检查同步状态失败",
      }
    );
    if (!isLatestRequest("syncStatus", requestToken)) {
      return;
    }
    if (data.status === "error") throw new Error(data.message);

    const differences = normalizeSyncDifferences(data);
    renderSyncStatus(statusDiv, differences);

    if (showAlert) {
      showToast("配置状态已刷新。", "success", "检查完成");
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    console.error("检查同步状态失败:", error);
    if (!isLatestRequest("syncStatus", requestToken)) {
      return;
    }
    renderSyncStatusError(statusDiv, error.message);
    if (showAlert) {
      showToast(error.message, "error", "检查失败");
    }
  } finally {
    finishLatestRequest("syncStatus", requestToken);
    if (isLatestRequest("syncStatus", requestToken) || !state.requestState.syncStatus.controller) {
      restoreButton(btn);
    }
  }
}

export async function checkImgHostSyncStatus(showAlert = true) {
  const uploadCountElement = document.getElementById("upload-count");
  const downloadCountElement = document.getElementById("download-count");
  const providerElement = document.getElementById("img-host-provider");
  const remoteImageCountElement = document.getElementById("remote-image-count");
  const remoteStorageSizeElement = document.getElementById("remote-storage-size");

  const requestToken = startLatestRequest("imgHostStatus");
  try {
    const data = await requestJson(
      "/api/img_host/sync/status",
      { signal: requestToken.controller.signal },
      {
        defaultErrorMessage: "获取图床同步状态失败",
      }
    );
    if (!isLatestRequest("imgHostStatus", requestToken)) {
      return;
    }

    const uploadCount = data.upload_count ?? data.to_upload?.length ?? 0;
    const downloadCount = data.download_count ?? data.to_download?.length ?? 0;
    const remoteImageCount =
      data.remote_image_count ??
      data.remote_count ??
      data.remote_images?.length ??
      0;
    let remoteStorageText = "未知";
    if (typeof data.remote_total_bytes === "number") {
      remoteStorageText = formatBytes(data.remote_total_bytes);
    } else if (typeof data.remote_total_bytes_estimated === "number") {
      remoteStorageText = `${formatBytes(data.remote_total_bytes_estimated)}（本地估算）`;
    }

    if (uploadCountElement) {
      uploadCountElement.textContent = uploadCount;
    }
    if (downloadCountElement) {
      downloadCountElement.textContent = downloadCount;
    }
    if (providerElement) {
      providerElement.textContent = data.provider_label || "未知图床";
    }
    if (remoteImageCountElement) {
      remoteImageCountElement.textContent = remoteImageCount;
    }
    if (remoteStorageSizeElement) {
      remoteStorageSizeElement.textContent = remoteStorageText;
    }

    if (showAlert) {
      showToast(
        `${data.provider_label || "图床"}：云端 ${remoteImageCount} 张，待上传 ${uploadCount} 个，待下载 ${downloadCount} 个。`,
        "info",
        "图床状态已刷新"
      );
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    console.error("检查图床同步状态失败:", error);
    if (!isLatestRequest("imgHostStatus", requestToken)) {
      return;
    }
    if (uploadCountElement) {
      uploadCountElement.textContent = "--";
    }
    if (downloadCountElement) {
      downloadCountElement.textContent = "--";
    }
    if (providerElement) {
      providerElement.textContent = "--";
    }
    if (remoteImageCountElement) {
      remoteImageCountElement.textContent = "--";
    }
    if (remoteStorageSizeElement) {
      remoteStorageSizeElement.textContent = "--";
    }
    if (showAlert) {
      showToast(error.message, "error", "检查失败");
    }
  } finally {
    finishLatestRequest("imgHostStatus", requestToken);
  }
}

export async function syncToRemote() {
  const btn = document.getElementById("upload-sync-btn");
  try {
    setButtonBusy(btn, "同步中...");

    await requestJson(
      "/api/img_host/sync/upload",
      {
        method: "POST",
      },
      { defaultErrorMessage: "同步到云端失败" }
    );
    await waitForSyncCompletion();
    await refreshUi({ syncStatus: true, imgHostStatus: true });
    showToast("云端上传同步已完成。", "success", "同步成功");
  } catch (error) {
    console.error("同步到云端失败:", error);
    showToast(error.message, "error", "同步失败");
  } finally {
    restoreButton(btn);
  }
}

export async function syncFromRemote() {
  const btn = document.getElementById("download-sync-btn");
  try {
    setButtonBusy(btn, "同步中...");

    await requestJson(
      "/api/img_host/sync/download",
      {
        method: "POST",
      },
      { defaultErrorMessage: "从云端同步失败" }
    );
    await waitForSyncCompletion();
    await refreshUi({ emojis: true, syncStatus: true, imgHostStatus: true });
    showToast("云端下载同步已完成。", "success", "同步成功");
  } catch (error) {
    console.error("从云端同步失败:", error);
    showToast(error.message, "error", "同步失败");
  } finally {
    restoreButton(btn);
  }
}

export async function syncConfig() {
  try {
    await requestJson(
      "/api/sync/config",
      {
        method: "POST",
      },
      { defaultErrorMessage: "同步配置失败" }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast("配置已同步到最新状态。", "success", "同步成功");
  } catch (error) {
    console.error("同步配置失败:", error);
    showToast(error.message, "error", "同步失败");
  }
}

export async function restoreCategory(category) {
  try {
    const data = await requestJson(
      "/api/category/restore",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: `恢复类别 ${category} 失败` }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(
      `已恢复默认表情包 ${data.copied_count || 0} 个。`,
      "success",
      "恢复成功"
    );
  } catch (error) {
    console.error(`恢复类别 ${category} 失败:`, error);
    showToast(error.message, "error", "恢复失败");
  }
}

export async function removeFromConfig(category) {
  try {
    await requestJson(
      "/api/category/remove_from_config",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: `移出配置失败` }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(`类别「${category}」已从配置文件移出。`, "success", "移出成功");
  } catch (error) {
    console.error(`移出配置失败:`, error);
    showToast(error.message, "error", "移出失败");
  }
}

export async function clearCategory(category) {
  try {
    await requestJson(
      "/api/category/clear",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: `清空类别 ${category} 失败` }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(`分类「${category}」已清空。`, "success", "清空成功");
  } catch (error) {
    console.error(`清空类别 ${category} 失败:`, error);
    showToast(error.message, "error", "清空失败");
  }
}

export async function deleteCategory(category) {
  try {
    await requestJson(
      "/api/category/delete",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ category }),
      },
      { defaultErrorMessage: `删除类别 ${category} 失败` }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(`类别「${category}」已成功删除。`, "success", "删除成功");
  } catch (error) {
    console.error(`删除类别 ${category} 失败:`, error);
    showToast(error.message, "error", "删除失败");
  }
}

export async function deleteEmoji(category, emoji) {
  try {
    await requestJson(
      "/api/emoji/delete",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ category, image_file: emoji }),
      },
      { defaultErrorMessage: `删除表情包失败` }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast("已成功从该类别删除表情包。", "success", "删除成功");
  } catch (error) {
    console.error("删除表情包失败:", error);
    showToast(error.message, "error", "删除失败");
  }
}

export async function moveEmojiItemsToCategory(targetCategory, uniqueItems) {
  try {
    const files = uniqueItems.map((item) => item.emoji);
    const sourceCategory = uniqueItems[0].category;

    await requestJson(
      "/api/emoji/batch_move",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_category: sourceCategory,
          target_category: targetCategory,
          image_files: files,
        }),
      },
      { defaultErrorMessage: "移动表情包失败" }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(
      `成功移动 ${uniqueItems.length} 个表情包到「${targetCategory}」分类。`,
      "success",
      "移动成功"
    );
  } catch (error) {
    console.error("移动表情包失败:", error);
    showToast(error.message, "error", "移动失败");
  }
}

export async function copyEmojiItemsToCategory(targetCategory, uniqueItems) {
  try {
    const files = uniqueItems.map((item) => item.emoji);
    const sourceCategory = uniqueItems[0].category;

    await requestJson(
      "/api/emoji/batch_copy",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_category: sourceCategory,
          target_category: targetCategory,
          image_files: files,
        }),
      },
      { defaultErrorMessage: "复制表情包失败" }
    );
    await refreshUi({ emojis: true, syncStatus: true });
    showToast(
      `成功复制 ${uniqueItems.length} 个表情包到「${targetCategory}」分类。`,
      "success",
      "复制成功"
    );
  } catch (error) {
    console.error("复制表情包失败:", error);
    showToast(error.message, "error", "复制失败");
  }
}

export async function waitForSyncCompletion() {
  while (true) {
    const status = await requestJson("/api/img_host/sync/check_process", {}, {
      defaultErrorMessage: "检查同步状态失败",
    });

    if (status.completed) {
      if (!status.success) {
        throw new Error("同步失败");
      }
      return status;
    }

    await sleep(1000);
  }
}

export async function refreshUi({ emojis = false, syncStatus = false, imgHostStatus = false } = {}) {
  const tasks = [];
  if (emojis) tasks.push(fetchEmojis());
  if (syncStatus) tasks.push(checkSyncStatus(false));
  if (imgHostStatus) tasks.push(checkImgHostSyncStatus(false));
  await Promise.all(tasks).catch((err) => {
    console.error("刷新UI失败:", err);
  });
}
