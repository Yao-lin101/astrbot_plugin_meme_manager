const { ref } = window.Vue;

export function useSync(showToast, fetchEmojis) {
  const vectorChecking = ref(false);
  const vectorStatus = ref({
    status: null,
    dimension: null,
    tagCount: null,
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

  const checkVectorStatus = async () => {
    if (vectorChecking.value) return;
    vectorChecking.value = true;
    try {
      const res = await fetch("/api/tag_embeddings/status");
      if (!res.ok) throw new Error("读取向量数据库状态失败");
      const { status, dimension, tag_count: tagCount } = await res.json();
      vectorStatus.value = { status, dimension, tagCount };
    } catch {
      vectorStatus.value = { status: "error", dimension: null, tagCount: null };
    } finally {
      vectorChecking.value = false;
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
    vectorChecking,
    vectorStatus,
    imgHostSyncing,
    imgHostStatus,
    formatBytes,
    checkVectorStatus,
    checkImgHostSyncStatus,
    syncToRemote,
    syncFromRemote,
  };
}
