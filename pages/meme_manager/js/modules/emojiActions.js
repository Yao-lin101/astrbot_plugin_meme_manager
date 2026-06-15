const { ref, reactive, nextTick } = window.Vue;

export function useEmojiActions({
  showToast,
  fetchEmojis,
  activeCategories,
  selectionEnabled,
  selectedEmojis,
  systemPersonas,
  emojiData,
  allEmojisList,
  getEmojiTags,
  confirm,
  showDangerConfirm,
  moveModal,
  batchPersonaModal,
  importModal,
  closeImportModal,
  drawerTagSearchQuery,
  selectedEmotions,
  batchAnalyzeModal,
}) {
  const activeDetailEmoji = ref(null);
  const detailMetadata = ref(null);
  const selectedPersonas = ref([]);
  const detailEmojiDescription = ref("");
  const detailDrawerLoading = ref(false);
  const aiAnalysisLoading = ref(false);
  const aiAnalysisMode = ref('');

  // Upload state tracking
  const uploadStateByCategory = ref(new Map());

  // Context Menu State
  const contextMenu = reactive({
    visible: false,
    x: 0,
    y: 0,
    targetCategory: null,
    targetEmoji: null,
    targetItems: [],
    pasteableItems: [],
  });

  const clipboardItems = ref([]);

  const toggleDetailDrawer = async (category, emoji) => {
    if (activeDetailEmoji.value === emoji) {
      closeDetailDrawer();
      return;
    }
    
    closeDetailDrawer();
    activeDetailEmoji.value = emoji;
    detailDrawerLoading.value = true;

    try {
      const res = await fetch(`/api/emoji/info?filename=${encodeURIComponent(emoji)}`);
      if (!res.ok) throw new Error("获取属性失败");
      const metadata = await res.json();

      if (activeDetailEmoji.value !== emoji) return;

      detailMetadata.value = metadata;
      selectedEmotions.value = metadata.emotions || [];
      selectedPersonas.value = metadata.personas || [];
      detailEmojiDescription.value = metadata.description || "";
    } catch (e) {
      showToast(e.message, "error", "加载表情属性失败");
      closeDetailDrawer();
    } finally {
      detailDrawerLoading.value = false;
    }
  };

  const closeDetailDrawer = () => {
    activeDetailEmoji.value = null;
    detailMetadata.value = null;
    selectedEmotions.value = [];
    selectedPersonas.value = [];
    detailEmojiDescription.value = "";
    drawerTagSearchQuery.value = "";
  };

  const toggleTagInDrawer = (tag) => {
    const idx = selectedEmotions.value.indexOf(tag);
    if (idx > -1) {
      selectedEmotions.value.splice(idx, 1);
    } else {
      selectedEmotions.value.push(tag);
    }
  };

  const togglePersonaInDrawer = (personaId) => {
    if (personaId === "*") {
      if (selectedPersonas.value.includes("*")) {
        selectedPersonas.value = [];
      } else {
        selectedPersonas.value = ["*"];
      }
    } else {
      const gIdx = selectedPersonas.value.indexOf("*");
      if (gIdx > -1) selectedPersonas.value.splice(gIdx, 1);

      const idx = selectedPersonas.value.indexOf(personaId);
      if (idx > -1) {
        selectedPersonas.value.splice(idx, 1);
      } else {
        selectedPersonas.value.push(personaId);
      }
    }
  };

  const handleCreateTagInDrawer = async () => {
    const newTag = drawerTagSearchQuery.value.trim();
    if (!newTag) return;

    const allCategories = Object.keys(emojiData.value);
    const existingCat = allCategories.find(cat => cat.toLowerCase() === newTag.toLowerCase());

    if (existingCat) {
      if (!selectedEmotions.value.includes(existingCat)) {
        selectedEmotions.value.push(existingCat);
      }
      drawerTagSearchQuery.value = "";
      return;
    }

    try {
      const res = await fetch("/api/category/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: newTag }),
      });
      if (!res.ok) throw new Error("创建标签失败");

      emojiData.value[newTag] = [];
      if (!selectedEmotions.value.includes(newTag)) {
        selectedEmotions.value.push(newTag);
      }
      showToast(`已成功创建新标签「${newTag}」并添加`, "success", "创建成功");
      drawerTagSearchQuery.value = "";
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "创建失败");
    }
  };

  const handleBackspace = (event) => {
    if (event && event.isComposing) return;
    if (drawerTagSearchQuery.value === "" && selectedEmotions.value.length > 0) {
      selectedEmotions.value.pop();
    }
  };

  const saveEmojiAttributes = async (closeAfterSave = true) => {
    if (selectedEmotions.value.length === 0) {
      showToast("请至少选择一个标签。", "warning", "保存提示");
      return false;
    }

    const personas = selectedPersonas.value.length === 0 ? ["*"] : selectedPersonas.value;
    const emoji = activeDetailEmoji.value;

    try {
      const res = await fetch("/api/emoji/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: emoji,
          emotions: selectedEmotions.value,
          personas: personas,
          description: detailEmojiDescription.value,
        }),
      });
      if (!res.ok) throw new Error("保存属性失败");

      showToast("属性保存成功！", "success", "修改成功");
      if (closeAfterSave) {
        closeDetailDrawer();
      }
      await fetchEmojis();
      return true;
    } catch (e) {
      showToast(e.message, "error", "保存失败");
      return false;
    }
  };

  const deleteEmoji = async (category, emoji) => {
    const isAll = category === "all";
    const title = isAll ? "物理删除表情包" : "删除标签 / 文件";
    const promptText = isAll
      ? "确认物理删除该表情包吗？此操作将永久从磁盘和所有标签下删除该表情文件！"
      : `确认从标签「${category}」下移除表情包？若该表情包不属于其他任何标签，它将被物理删除。`;

    const confirmed = await confirm(
      title,
      promptText,
      "确认删除",
      "danger"
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/emoji/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, image_file: emoji }),
      });
      if (!res.ok) throw new Error("删除失败");

      selectedEmojis.value.delete(`${category}:${emoji}`);
      showToast("表情包已成功删除", "success", "删除成功");
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "删除失败");
    }
  };

  const batchDeleteSelected = async () => {
    const items = Array.from(selectedEmojis.value.values());
    if (items.length === 0) return;

    const confirmed = await confirm(
      "批量删除表情包",
      `确认删除已选中的 ${items.length} 个表情包？这会移除其标签，若该表情包不属于其他任何标签，它将被物理删除。`,
      "确认批量删除",
      "danger"
    );
    if (!confirmed) return;

    const grouped = {};
    items.forEach((item) => {
      const cats = item.category === 'all' ? getEmojiTags(item.emoji) : [item.category];
      cats.forEach((cat) => {
        if (!grouped[cat]) grouped[cat] = [];
        if (!grouped[cat].includes(item.emoji)) {
          grouped[cat].push(item.emoji);
        }
      });
    });

    let successCount = 0;
    for (const [cat, files] of Object.entries(grouped)) {
      try {
        const res = await fetch("/api/emoji/batch_delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: cat, image_files: files }),
        });
        if (res.ok) {
          const result = await res.json();
          successCount += result.deleted_count || 0;
        }
      } catch (e) {
        console.error(e);
      }
    }

    showToast(`已成功批量删除 ${successCount} 个表情包。`, "success", "批量删除完成");
    selectedEmojis.value.clear();
    await fetchEmojis();
  };

  const batchConvertToGif = async () => {
    const items = Array.from(selectedEmojis.value.values());
    if (items.length === 0) return;

    const confirmed = await confirm(
      "转换为 GIF",
      `确认将选中的 ${items.length} 个表情包转换为 GIF 格式吗？(移动端 QQ 对 WEBP 动图支持不佳，推荐转换)`,
      "确认转换",
      "primary"
    );
    if (!confirmed) return;

    const filenames = Array.from(new Set(items.map(item => item.emoji)));
    
    try {
      const res = await fetch("/api/emoji/batch_convert_gif", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filenames }),
      });
      if (res.ok) {
        const result = await res.json();
        showToast(
          `成功转换 ${result.converted_count} 个，跳过 ${result.skipped_count} 个，失败 ${result.failed_count} 个。`,
          "success",
          "转换完成"
        );
      } else {
        throw new Error("转换请求失败");
      }
    } catch (e) {
      showToast(e.message, "error", "转换失败");
    }

    selectedEmojis.value.clear();
    await fetchEmojis();
  };

  const batchRenameToTags = async () => {
    const items = Array.from(selectedEmojis.value.values());
    if (items.length === 0) return;

    const confirmed = await confirm(
      "更名为标签集合",
      `确认将选中的 ${items.length} 个表情包文件重命名为其标签集合吗？(无标签的表情将保持原文件名)`,
      "确认更名",
      "primary"
    );
    if (!confirmed) return;

    const filenames = Array.from(new Set(items.map(item => item.emoji)));

    try {
      const res = await fetch("/api/emoji/batch_rename_to_tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filenames }),
      });
      if (res.ok) {
        const result = await res.json();
        showToast(
          `成功更名 ${result.renamed_count} 个，跳过 ${result.skipped_count} 个。`,
          "success",
          "更名完成"
        );
      } else {
        throw new Error("更名请求失败");
      }
    } catch (e) {
      showToast(e.message, "error", "更名失败");
    }

    selectedEmojis.value.clear();
    await fetchEmojis();
  };

  const saveBatchPersonas = async () => {
    const items = Array.from(selectedEmojis.value.values());
    if (items.length === 0) return;
    const filenames = items.map((item) => item.emoji);

    const personas = batchPersonaModal.personas.length === 0 ? ["*"] : batchPersonaModal.personas;

    try {
      const res = await fetch("/api/emoji/batch_edit_personas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filenames: filenames,
          personas: personas,
        }),
      });
      if (!res.ok) throw new Error("批量更新人格限制失败");

      showToast("批量设置人格限制成功！", "success", "修改成功");
      batchPersonaModal.visible = false;
      selectedEmojis.value.clear();
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "批量设置失败");
    }
  };

  const handleMoveTarget = async (targetCategory) => {
    const items = Array.from(selectedEmojis.value.values());
    if (items.length === 0) return;

    const grouped = {};
    items.forEach((item) => {
      if (!grouped[item.category]) grouped[item.category] = [];
      grouped[item.category].push(item.emoji);
    });

    let movedCount = 0;
    for (const [sourceCat, files] of Object.entries(grouped)) {
      try {
        const res = await fetch("/api/emoji/batch_move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_category: sourceCat,
            target_category: targetCategory,
            image_files: files,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          movedCount += data.moved_count || 0;
        }
      } catch (e) {
        console.error(e);
      }
    }

    showToast(`已成功将 ${movedCount} 个表情包移动到 ${targetCategory}`, "success", "移动成功");
    moveModal.visible = false;
    selectedEmojis.value.clear();
    await fetchEmojis();
  };

  const clearAllEmojiFiles = async () => {
    const totalCount = Object.values(emojiData.value).reduce((sum, list) => sum + (list?.length || 0), 0);
    if (totalCount === 0) {
      showToast("库中没有任何表情包可以清空", "warning");
      return;
    }

    const confirmed = await showDangerConfirm(
      "清空所有表情包",
      `确认彻底清空库中的所有 ${totalCount} 个表情包？此操作将删除所有磁盘文件，但保留标签目录配置。`
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/emoji/clear_all", { method: "POST" });
      if (!res.ok) throw new Error("清空失败");
      const data = await res.json();

      showToast(`已清空全部表情包，共删除 ${data.deleted_count} 个文件。`, "success", "清空成功");
      selectedEmojis.value.clear();
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "清空失败");
    }
  };

  const submitImport = async () => {
    const category = activeCategories.value[0];
    if (!category || category === 'all') return;

    const filenames = Array.from(importModal.selectedEmojis);
    if (filenames.length === 0) return;

    try {
      const res = await fetch("/api/emoji/batch_import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, filenames }),
      });
      if (!res.ok) throw new Error("批量导入失败");

      showToast(`成功导入 ${filenames.length} 个表情到标签 ${category}`, "success", "导入成功");
      closeImportModal();
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "导入失败");
    }
  };

  const onDragStart = (event, emoji, category) => {
    let dragItems = [];
    const key = `${category}:${emoji}`;
    if (selectionEnabled.value && selectedEmojis.value.has(key)) {
      dragItems = Array.from(selectedEmojis.value.values());
    } else {
      dragItems = [{ category, emoji }];
    }

    event.dataTransfer.setData("application/json", JSON.stringify({ items: dragItems, sourceCategory: category }));
    event.dataTransfer.effectAllowed = "move";
  };

  const onDropEmoji = async (event, targetCategory) => {
    try {
      const dataStr = event.dataTransfer.getData("application/json");
      if (!dataStr) return;
      const { items, sourceCategory } = JSON.parse(dataStr);
      if (sourceCategory === targetCategory) return;

      const res = await fetch("/api/emoji/batch_move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_category: sourceCategory,
          target_category: targetCategory,
          image_files: items.map((i) => i.emoji),
        }),
      });
      if (!res.ok) throw new Error("移动失败");
      const result = await res.json();

      showToast(`成功将 ${result.moved_count} 个表情包移动到标签 ${targetCategory}`, "success", "移动成功");
      selectedEmojis.value.clear();
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "移动失败");
    }
  };

  const triggerFileInput = (category) => {
    const input = document.getElementById(`file-input-${category}`);
    if (input) input.click();
  };

  const onFileSelected = (event, category) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      uploadFiles(files, category);
    }
    event.target.value = "";
  };

  const onUploadDrop = (event, category) => {
    const files = event.dataTransfer.files;
    if (files && files.length > 0) {
      uploadFiles(files, category);
    }
  };

  const uploadFiles = async (files, category) => {
    if (uploadStateByCategory.value.has(category)) {
      showToast(`当前标签 ${category} 正在上传中，请稍候。`, "warning");
      return;
    }

    const total = files.length;
    uploadStateByCategory.value.set(category, { progress: 0, text: `准备上传 0/${total}` });

    let completed = 0;
    let failed = 0;
    let dups = 0;

    for (let i = 0; i < total; i++) {
      const file = files[i];
      uploadStateByCategory.value.set(category, {
        progress: Math.round((i / total) * 100),
        text: `上传中: ${i + 1}/${total} (${file.name})`,
      });

      const formData = new FormData();
      formData.append("category", category);
      formData.append("image_file", file);

      try {
        const res = await fetch("/api/emoji/add", {
          method: "POST",
          body: formData,
        });

        let resData = null;
        try {
          resData = await res.json();
        } catch (err) {
          // ignore
        }

        if (res.status === 409) {
          if (resData && (resData.code === "similar_emoji" || resData.code === "duplicate_emoji")) {
            const localUrl = URL.createObjectURL(file);
            const targetFilename = resData.existing_filename || resData.filename;
            const similarUrl = `/api/plug/astrbot_plugin_meme_manager/memes/file/thumbnail/${encodeURIComponent(targetFilename)}`;
            
            const isSimilar = resData.code === "similar_emoji";
            const title = isSimilar ? "检测到相似表情包" : "检测到完全相同的表情包";
            const description = isSimilar
              ? `表情包「${file.name}」与已有表情「${targetFilename}」相似度达 ${Math.round(resData.similarity * 100)}%，是否仍要继续上传？`
              : `分类中已存在完全相同的文件「${targetFilename}」，是否仍要强制上传为新文件？`;

            const confirmed = await confirm(
              title,
              description,
              "继续上传",
              "primary",
              similarUrl,
              localUrl
            );
            
            URL.revokeObjectURL(localUrl);

            if (confirmed) {
              const forceFormData = new FormData();
              forceFormData.append("category", category);
              forceFormData.append("image_file", file);
              forceFormData.append("ignore_similarity", "true");
              
              try {
                const forceRes = await fetch("/api/emoji/add", {
                  method: "POST",
                  body: forceFormData,
                });
                if (forceRes.ok) {
                  completed++;
                } else {
                  failed++;
                }
              } catch (err) {
                failed++;
              }
            } else {
              dups++;
            }
          } else {
            dups++;
          }
        } else if (!res.ok) {
          throw new Error();
        } else {
          completed++;
        }
      } catch (e) {
        failed++;
      }
    }

    uploadStateByCategory.value.delete(category);
    showToast(
      `上传完成！成功 ${completed} 个` +
        (dups > 0 ? `，重复跳过 ${dups} 个` : "") +
        (failed > 0 ? `，失败 ${failed} 个` : ""),
      failed > 0 ? "warning" : "success",
      "上传完毕"
    );
    await fetchEmojis();
  };

  const openContextMenu = (event, category, emoji) => {
    const key = `${category}:${emoji}`;
    let targetItems = [];
    if (selectionEnabled.value && selectedEmojis.value.has(key)) {
      targetItems = Array.from(selectedEmojis.value.values());
    } else {
      targetItems = [{ category, emoji }];
    }

    const pasteableItems = clipboardItems.value.filter((i) => i.category !== category);

    contextMenu.x = event.clientX;
    contextMenu.y = event.clientY;
    contextMenu.targetCategory = category;
    contextMenu.targetEmoji = emoji;
    contextMenu.targetItems = targetItems;
    contextMenu.pasteableItems = pasteableItems;
    contextMenu.visible = true;
  };

  const closeContextMenu = () => {
    contextMenu.visible = false;
  };

  const contextMenuDelete = async () => {
    contextMenu.visible = false;
    const count = contextMenu.targetItems.length;
    if (count === 0) return;

    const confirmed = await confirm(
      "批量删除表情包",
      `确认删除右键选中的 ${count} 个表情包吗？此操作不可恢复。`,
      "确认删除",
      "danger"
    );
    if (!confirmed) return;

    const grouped = {};
    contextMenu.targetItems.forEach((item) => {
      if (!grouped[item.category]) grouped[item.category] = [];
      grouped[item.category].push(item.emoji);
    });

    let successCount = 0;
    for (const [cat, files] of Object.entries(grouped)) {
      try {
        const res = await fetch("/api/emoji/batch_delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: cat, image_files: files }),
        });
        if (res.ok) {
          const data = await res.json();
          successCount += data.deleted_count || 0;
        }
      } catch (e) {
        console.error(e);
      }
    }

    showToast(`成功删除了 ${successCount} 个表情包`, "success", "删除成功");
    contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
    await fetchEmojis();
  };

  const contextMenuMove = () => {
    contextMenu.visible = false;
    moveModal.visible = true;
  };

  const contextMenuCopy = () => {
    contextMenu.visible = false;
    clipboardItems.value = [...contextMenu.targetItems];
    showToast(`已成功复制 ${clipboardItems.value.length} 个表情到剪贴板，可在其他标签右键粘贴。`, "success", "复制成功");
  };

  const contextMenuConvertToGif = async () => {
    contextMenu.visible = false;
    const count = contextMenu.targetItems.length;
    if (count === 0) return;

    const confirmed = await confirm(
      "转换为 GIF",
      `确认将选中的 ${count} 个表情包转换为 GIF 格式吗？(移动端 QQ 对 WEBP 动图支持不佳，推荐转换)`,
      "确认转换",
      "primary"
    );
    if (!confirmed) return;

    const filenames = Array.from(new Set(contextMenu.targetItems.map(item => item.emoji)));
    
    try {
      const res = await fetch("/api/emoji/batch_convert_gif", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filenames }),
      });
      if (res.ok) {
        const result = await res.json();
        showToast(
          `成功转换 ${result.converted_count} 个，跳过 ${result.skipped_count} 个，失败 ${result.failed_count} 个。`,
          "success",
          "转换完成"
        );
      } else {
        throw new Error("转换请求失败");
      }
    } catch (e) {
      showToast(e.message, "error", "转换失败");
    }

    contextMenu.targetItems.forEach((i) => selectedEmojis.value.delete(`${i.category}:${i.emoji}`));
    await fetchEmojis();
  };

  const contextMenuPaste = async () => {
    contextMenu.visible = false;
    const targetCategory = contextMenu.targetCategory;
    const pasteable = contextMenu.pasteableItems;
    if (pasteable.length === 0) return;

    const grouped = {};
    pasteable.forEach((item) => {
      if (!grouped[item.category]) grouped[item.category] = [];
      grouped[item.category].push(item.emoji);
    });

    let copiedCount = 0;
    for (const [sourceCat, files] of Object.entries(grouped)) {
      try {
        const res = await fetch("/api/emoji/batch_copy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_category: sourceCat,
            target_category: targetCategory,
            image_files: files,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          copiedCount += data.copied_count || 0;
        }
      } catch (e) {
        console.error(e);
      }
    }

    showToast(`成功向标签 ${targetCategory} 复制粘贴了 ${copiedCount} 个表情包`, "success", "粘贴成功");
    clipboardItems.value = [];
    await fetchEmojis();
  };

  const runSingleEmojiAnalysis = async (mode) => {
    if (!activeDetailEmoji.value) return;

    if (!batchAnalyzeModal.selectedProvider) {
      showToast("请先选择多模态 AI 供应商。", "warning", "分析提示");
      return;
    }

    aiAnalysisLoading.value = true;
    aiAnalysisMode.value = mode;
    detailDrawerLoading.value = true;

    try {
      if (mode === 'desc_by_tags' || mode === 'tags_desc_by_tags') {
        const saved = await saveEmojiAttributes(false);
        if (!saved) {
          return; // Abort analysis if save failed or was canceled
        }
      }

      // Ensure prompt templates are loaded
      if (!batchAnalyzeModal.promptTemplate || !batchAnalyzeModal.promptTemplate.intro) {
        const templateRes = await fetch("/api/prompt/template");
        if (templateRes.ok) {
          batchAnalyzeModal.promptTemplate = await templateRes.json();
        }
      }

      const analyze_tags = mode === 'tags_desc_by_tags' || mode === 'full';
      const analyze_description = mode === 'desc_by_tags' || mode === 'tags_desc_by_tags' || mode === 'full';
      const pass_existing_tags_as_ref = mode === 'desc_by_tags' || mode === 'tags_desc_by_tags';

      let parts = [];
      if (batchAnalyzeModal.promptTemplate.intro) {
        parts.push(batchAnalyzeModal.promptTemplate.intro);
      }
      if (analyze_tags && batchAnalyzeModal.promptTemplate.tags) {
        parts.push(batchAnalyzeModal.promptTemplate.tags);
      }
      if (analyze_description && batchAnalyzeModal.promptTemplate.desc) {
        parts.push(batchAnalyzeModal.promptTemplate.desc);
      }
      const prompt_content = parts.join("\n\n");

      const res = await fetch("/api/emoji/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: activeDetailEmoji.value,
          provider_id: batchAnalyzeModal.selectedProvider,
          analyze_tags,
          analyze_description,
          pass_existing_tags_as_ref,
          prompt_content
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.message || "AI 分析请求失败");
      }

      const result = await res.json();

      if (analyze_tags) {
        // AI-generated tags completely overwrite existing tags
        selectedEmotions.value = result.tags || [];
      }
      if (analyze_description) {
        detailEmojiDescription.value = result.description || "";
      }

      showToast("AI 分析成功！正在自动保存到数据库...", "success", "分析成功");
      // Trigger automatic save to backend database without closing the modal
      await saveEmojiAttributes(false);
    } catch (e) {
      console.error(e);
      showToast(e.message, "error", "AI 分析失败");
    } finally {
      detailDrawerLoading.value = false;
      aiAnalysisLoading.value = false;
      aiAnalysisMode.value = '';
    }
  };

  const onEmojiClick = (category, emoji) => {
    if (selectionEnabled.value) {
      const key = `${category}:${emoji}`;
      if (selectedEmojis.value.has(key)) {
        selectedEmojis.value.delete(key);
      } else {
        selectedEmojis.value.set(key, { category, emoji });
      }
    } else {
      toggleDetailDrawer(category, emoji);
    }
  };

  return {
    activeDetailEmoji,
    detailMetadata,
    detailEmojiDescription,
    selectedEmotions,
    selectedPersonas,
    detailDrawerLoading,
    aiAnalysisLoading,
    aiAnalysisMode,
    uploadStateByCategory,
    contextMenu,
    clipboardItems,
    toggleDetailDrawer,
    closeDetailDrawer,
    toggleTagInDrawer,
    togglePersonaInDrawer,
    saveEmojiAttributes,
    runSingleEmojiAnalysis,
    deleteEmoji,
    batchDeleteSelected,
    batchConvertToGif,
    batchRenameToTags,
    saveBatchPersonas,
    handleMoveTarget,
    clearAllEmojiFiles,
    submitImport,
    onDragStart,
    onDropEmoji,
    triggerFileInput,
    onFileSelected,
    onUploadDrop,
    openContextMenu,
    closeContextMenu,
    contextMenuDelete,
    contextMenuMove,
    contextMenuCopy,
    contextMenuConvertToGif,
    contextMenuPaste,
    onEmojiClick,
    handleCreateTagInDrawer,
    handleBackspace,
  };
}
