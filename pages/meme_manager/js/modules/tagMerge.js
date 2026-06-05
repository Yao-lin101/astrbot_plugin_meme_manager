const { ref, computed } = window.Vue;

export function useTagMerge(showToast, fetchEmojis, confirm) {
  const tagMergeModal = ref({
    visible: false,
    scanning: false,
    merging: false,
    scanned: false,
  });

  const tagMergeSimilarityThreshold = ref(80); // 50 - 95
  const tagMergeGroups = ref([]);
  const tagMergeTotalTags = ref(0);
  const tagMergeTagsWithoutVector = ref(0);

  const openTagMergeModal = () => {
    tagMergeGroups.value = [];
    tagMergeModal.value.visible = true;
    tagMergeModal.value.scanning = false;
    tagMergeModal.value.merging = false;
    tagMergeModal.value.scanned = false;
  };

  const closeTagMergeModal = () => {
    tagMergeModal.value.visible = false;
  };

  const scanSimilarTags = async () => {
    tagMergeModal.value.scanning = true;
    tagMergeGroups.value = [];
    try {
      const thresholdVal = tagMergeSimilarityThreshold.value / 100;
      const res = await fetch(`/api/tag_merge/scan?threshold=${thresholdVal}`);
      if (!res.ok) {
        throw new Error("扫描相似标签请求失败");
      }
      const data = await res.json();
      const groups = data.groups || [];

      // 为每个标签附加 enabled 标志（默认参与合并）
      groups.forEach((group) => {
        group.tags.forEach((tag) => {
          tag.enabled = true;
        });
      });

      tagMergeGroups.value = groups;
      tagMergeTotalTags.value = data.total_tags || 0;
      tagMergeTagsWithoutVector.value = data.tags_without_vector || 0;
      tagMergeModal.value.scanned = true;

      if (groups.length === 0) {
        showToast("未发现可合并的相似标签组！", "success", "扫描完成");
      } else {
        showToast(`扫描完成，共发现 ${groups.length} 组相似标签！`, "info", "扫描完成");
      }
    } catch (e) {
      console.error(e);
      showToast(e.message || "未知错误", "error", "扫描失败");
    } finally {
      tagMergeModal.value.scanning = false;
    }
  };

  const setRepresentativeTag = (group, tagName) => {
    group.tags.forEach((tag) => {
      tag.is_representative = tag.name === tagName;
    });
  };

  const toggleTagInGroup = (group, tagName) => {
    const tag = group.tags.find((t) => t.name === tagName);
    if (!tag) return;
    // 不允许取消代表标签
    if (tag.is_representative) return;
    tag.enabled = !tag.enabled;
  };

  // 待合并的 source 标签总数（启用且非代表的标签）
  const totalMergeCount = computed(() => {
    let count = 0;
    tagMergeGroups.value.forEach((group) => {
      const hasRep = group.tags.some((t) => t.is_representative);
      if (!hasRep) return;
      group.tags.forEach((tag) => {
        if (!tag.is_representative && tag.enabled) {
          count++;
        }
      });
    });
    return count;
  });

  const mergeSelectedGroups = async () => {
    const merges = [];
    tagMergeGroups.value.forEach((group) => {
      const rep = group.tags.find((t) => t.is_representative);
      if (!rep) return;
      const sources = group.tags
        .filter((t) => !t.is_representative && t.enabled)
        .map((t) => t.name);
      if (sources.length > 0) {
        merges.push({ target: rep.name, sources });
      }
    });

    if (merges.length === 0) {
      showToast("没有选择需要合并的标签！", "warning", "操作提示");
      return;
    }

    const sourceCount = merges.reduce((acc, m) => acc + m.sources.length, 0);
    const confirmProceed = await confirm(
      "确认合并标签",
      `即将把 ${sourceCount} 个标签合并到对应的代表标签中，此操作会修改表情库的标签数据，是否继续？`,
      "确认合并"
    );
    if (!confirmProceed) return;

    tagMergeModal.value.merging = true;
    try {
      const res = await fetch("/api/tag_merge/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ merges }),
      });
      if (!res.ok) {
        throw new Error("标签合并请求失败");
      }
      showToast("标签合并成功！", "success", "合并成功");
      tagMergeModal.value.visible = false;
      await fetchEmojis();
    } catch (e) {
      console.error(e);
      showToast(e.message || "未知错误", "error", "合并失败");
    } finally {
      tagMergeModal.value.merging = false;
    }
  };

  return {
    tagMergeModal,
    tagMergeSimilarityThreshold,
    tagMergeGroups,
    tagMergeTotalTags,
    tagMergeTagsWithoutVector,
    openTagMergeModal,
    closeTagMergeModal,
    scanSimilarTags,
    setRepresentativeTag,
    toggleTagInGroup,
    mergeSelectedGroups,
    totalMergeCount,
  };
}
