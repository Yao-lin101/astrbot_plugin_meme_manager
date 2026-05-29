const { ref, computed } = window.Vue;

export function useSelection(emojiData, allEmojisList) {
  const selectedEmojis = ref(new Map()); // Key: 'category:emoji' -> { category, emoji }
  const selectionEnabled = computed(() => selectedEmojis.value.size > 0);

  const pruneSelections = () => {
    for (const [key, item] of selectedEmojis.value.entries()) {
      const list = emojiData.value[item.category];
      if (!list || !list.includes(item.emoji)) {
        selectedEmojis.value.delete(key);
      }
    }
  };

  const toggleSelectionMode = () => {
    selectedEmojis.value.clear();
  };

  const isEmojiSelected = (category, emoji) => {
    return selectedEmojis.value.has(`${category}:${emoji}`);
  };

  const toggleEmojiSelection = (category, emoji) => {
    const key = `${category}:${emoji}`;
    if (selectedEmojis.value.has(key)) {
      selectedEmojis.value.delete(key);
    } else {
      selectedEmojis.value.set(key, { category, emoji });
    }
  };

  const getCategorySelectedCount = (category) => {
    let count = 0;
    for (const item of selectedEmojis.value.values()) {
      if (item.category === category) count++;
    }
    return count;
  };

  const getVisibleSelectedCount = (visibleList, category) => {
    let count = 0;
    if (!visibleList) return 0;
    visibleList.forEach((emoji) => {
      if (selectedEmojis.value.has(`${category}:${emoji}`)) count++;
    });
    return count;
  };

  const isAllSelectedInCategory = (category, visibleList) => {
    const list = visibleList || (category === 'all' ? allEmojisList.value : (emojiData.value[category] || []));
    if (list.length === 0) return false;
    return list.every((emoji) => isEmojiSelected(category, emoji));
  };

  const toggleCategorySelection = (category, visibleList) => {
    const list = visibleList || (category === 'all' ? allEmojisList.value : (emojiData.value[category] || []));
    if (isAllSelectedInCategory(category, list)) {
      list.forEach((emoji) => {
        selectedEmojis.value.delete(`${category}:${emoji}`);
      });
    } else {
      list.forEach((emoji) => {
        selectedEmojis.value.set(`${category}:${emoji}`, { category, emoji });
      });
    }
  };

  return {
    selectedEmojis,
    selectionEnabled,
    pruneSelections,
    toggleSelectionMode,
    isEmojiSelected,
    toggleEmojiSelection,
    getCategorySelectedCount,
    getVisibleSelectedCount,
    isAllSelectedInCategory,
    toggleCategorySelection,
  };
}
