const { ref } = window.Vue;

export function useCategories(
  showToast,
  fetchEmojis,
  checkSyncStatus,
  renameCategoryModal,
  addCategoryForm,
  emojiData,
  activeCategories,
  confirm,
  showDangerConfirm
) {
  const openRenameCategory = (category) => {
    renameCategoryModal.category = category;
    renameCategoryModal.originalCategory = category;
    renameCategoryModal.visible = true;
  };

  const saveRenameCategory = async () => {
    const oldName = renameCategoryModal.originalCategory;
    const newName = renameCategoryModal.category.trim();
    if (!newName) {
      showToast("标签名称不能为空", "warning");
      return;
    }
    if (oldName === newName) {
      renameCategoryModal.visible = false;
      return;
    }
    try {
      const res = await fetch("/api/category/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          old_name: oldName,
          new_name: newName,
        }),
      });
      if (!res.ok) throw new Error("重命名类别失败");

      showToast(`标签已成功从「${oldName}」重命名为「${newName}」。`, "success", "重命名成功");
      renameCategoryModal.visible = false;
      const idx = activeCategories.value.indexOf(oldName);
      if (idx > -1) {
        activeCategories.value[idx] = newName;
      }
      await fetchEmojis();
      await checkSyncStatus(false);
    } catch (e) {
      showToast(e.message, "error", "重命名失败");
    }
  };

  const saveNewCategory = async () => {
    const name = addCategoryForm.name.trim();

    if (!name) {
      showToast("请输入分类名称再保存", "warning");
      return;
    }

    try {
      const res = await fetch("/api/category/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: name }),
      });
      if (!res.ok) throw new Error("添加分类失败");

      showToast(`新分类「${name}」添加成功。`, "success", "保存成功");
      addCategoryForm.name = "";
      addCategoryForm.visible = false;
      await fetchEmojis();
      await checkSyncStatus(false);
    } catch (e) {
      showToast(e.message, "error", "添加失败");
    }
  };

  const clearCategory = async (category) => {
    const count = emojiData.value[category]?.length || 0;
    if (count === 0) {
      showToast("该类别当前为空，无需清空", "info");
      return;
    }

    const confirmed = await showDangerConfirm(
      `清空分类「${category}」`,
      `确定要删除分类「${category}」下的全部 ${count} 个表情文件吗？保留分类名称和描述。`
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/category/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      if (!res.ok) throw new Error("清空失败");
      const data = await res.json();

      showToast(`已清空分类 ${category}，删除了 ${data.deleted_count} 个表情包。`, "success", "清空成功");
      await fetchEmojis();
    } catch (e) {
      showToast(e.message, "error", "清空失败");
    }
  };

  const deleteCategory = async (category) => {
    const confirmed = await confirm(
      `删除分类「${category}」`,
      `确认删除分类「${category}」吗？此操作将清除该分类的所有表情包分类标签，若表情包不属于其他任何分类，对应的磁盘文件将被物理删除。`,
      "确认删除",
      "danger"
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/category/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      if (!res.ok) throw new Error("删除失败");

      showToast(`已成功删除分类 ${category}`, "success", "删除成功");
      await fetchEmojis();
      await checkSyncStatus(false);
    } catch (e) {
      showToast(e.message, "error", "删除失败");
    }
  };

  return {
    openRenameCategory,
    saveRenameCategory,
    saveNewCategory,
    clearCategory,
    deleteCategory,
  };
}
