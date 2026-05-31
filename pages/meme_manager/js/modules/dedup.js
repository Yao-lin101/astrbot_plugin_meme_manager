const { ref, computed } = window.Vue;

export function useDedup(showToast, fetchEmojis) {
  const duplicateModal = ref({
    visible: false,
    scanning: false,
    resolving: false,
  });

  const similarityThreshold = ref(85); // 50 - 100
  const duplicateGroups = ref([]);
  const mergeMetadata = ref(true);

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const openDuplicateModal = () => {
    duplicateGroups.value = [];
    duplicateModal.value.visible = true;
    duplicateModal.value.scanning = false;
    duplicateModal.value.resolving = false;
  };

  const closeDuplicateModal = () => {
    duplicateModal.value.visible = false;
  };

  const scanDuplicates = async () => {
    duplicateModal.value.scanning = true;
    duplicateGroups.value = [];
    try {
      const thresholdVal = similarityThreshold.value / 100;
      const res = await fetch(`/api/emoji/check_duplicates?threshold=${thresholdVal}`);
      if (!res.ok) {
        throw new Error("扫描重复表情包请求失败");
      }
      const data = await res.json();
      const groups = data.groups || [];

      // Pre-select the first as keep, others as delete
      groups.forEach((group) => {
        if (group.memes && group.memes.length > 0) {
          group.memes.forEach((meme, index) => {
            meme.action = index === 0 ? 'keep' : 'delete';
          });
        }
      });

      duplicateGroups.value = groups;
      if (groups.length === 0) {
        showToast("未检测到任何重复/相似的表情包！", "success", "扫描完成");
      } else {
        showToast(`扫描完成，共发现 ${groups.length} 组相似表情包！`, "info", "扫描完成");
      }
    } catch (e) {
      console.error(e);
      showToast(e.message || "未知错误", "error", "扫描失败");
    } finally {
      duplicateModal.value.scanning = false;
    }
  };

  const toggleMemeAction = (group, targetMeme, action) => {
    targetMeme.action = action;
  };

  const totalDeletesCount = computed(() => {
    let count = 0;
    duplicateGroups.value.forEach(group => {
      group.memes.forEach(meme => {
        if (meme.action === 'delete') {
          count++;
        }
      });
    });
    return count;
  });

  const resolveDuplicates = async () => {
    const keeps = [];
    const deletes = [];

    duplicateGroups.value.forEach((group) => {
      group.memes.forEach((meme) => {
        if (meme.action === 'keep') {
          keeps.push(meme.filename);
        } else if (meme.action === 'delete') {
          deletes.push(meme.filename);
        }
      });
    });

    if (deletes.length === 0) {
      showToast("没有选择需要清理/删除的表情包！", "warning", "操作提示");
      return;
    }

    // Double check if any group has NO keeps at all
    let hasGroupWithNoKeeps = false;
    for (const group of duplicateGroups.value) {
      const keepCount = group.memes.filter(m => m.action === 'keep').length;
      if (keepCount === 0) {
        hasGroupWithNoKeeps = true;
        break;
      }
    }

    if (hasGroupWithNoKeeps) {
      const confirmProceed = confirm("检测到有部分重复表情组未选择保留任何图片，这意味着该组的图片将全部被删除。是否继续？");
      if (!confirmProceed) return;
    }

    duplicateModal.value.resolving = true;
    try {
      const res = await fetch("/api/emoji/resolve_duplicates", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          keeps,
          deletes,
          merge: mergeMetadata.value
        })
      });

      if (!res.ok) {
        throw new Error("清理重复表情包请求失败");
      }

      showToast("重复表情包清理成功！", "success", "清理成功");
      duplicateModal.value.visible = false;
      await fetchEmojis();
    } catch (e) {
      console.error(e);
      showToast(e.message || "未知错误", "error", "清理失败");
    } finally {
      duplicateModal.value.resolving = false;
    }
  };

  return {
    duplicateModal,
    similarityThreshold,
    duplicateGroups,
    mergeMetadata,
    formatBytes,
    openDuplicateModal,
    closeDuplicateModal,
    scanDuplicates,
    toggleMemeAction,
    resolveDuplicates,
    totalDeletesCount,
  };
}
