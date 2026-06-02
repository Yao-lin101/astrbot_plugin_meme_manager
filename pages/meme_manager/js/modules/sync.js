const { ref } = window.Vue;

export function useSync(showToast, fetchEmojis) {
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

  const checkSyncStatus = async (showAlert = true) => {
    syncChecking.value = true;
    try {
      const res = await fetch("/api/sync/status");
      if (!res.ok) throw new Error("获取状态失败");
      const data = await res.json();

      if (data.status === "error") throw new Error(data.message);

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

  const removeFromConfig = async (category) => {
    try {
      const res = await fetch("/api/category/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      if (!res.ok) throw new Error("移除配置失败");
      showToast(`已从配置中移除标签 「${category}」`, "success", "移除成功");
      await fetchEmojis();
      await checkSyncStatus(false);
    } catch (e) {
      showToast(e.message, "error", "删除配置失败");
    }
  };

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
    showToast("正在从云端下载表情包...", "info", "下载同步中", 5000);
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

  return {
    syncChecking,
    syncStatus,
    imgHostSyncing,
    imgHostStatus,
    formatBytes,
    checkSyncStatus,
    syncConfig,
    removeFromConfig,
    checkImgHostSyncStatus,
    syncToRemote,
    syncFromRemote,
  };
}
