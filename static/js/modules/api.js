const { ref, computed } = window.Vue;

export function useApi(showToast, pruneSelections) {
  const emojiData = ref({});
  const emojiMtimes = ref({});
  const tagDescriptions = ref({});
  const systemPersonas = ref([]);
  const personaTags = ref({});
  const personaDedicatedTag = ref("");
  const personaFilter = ref("");
  const activeCategory = ref(null);
  
  const tabSearchQuery = ref("");
  const drawerTagSearchQuery = ref("");
  const visibleLimit = ref(60);

  const fetchEmojis = async () => {
    visibleLimit.value = 60;
    try {
      const personaId = personaFilter.value;
      personaDedicatedTag.value = personaTags.value[personaId] || "";
      const url = personaId ? `/api/emoji?persona_id=${encodeURIComponent(personaId)}` : "/api/emoji";
      
      const [emojiRes, tagRes] = await Promise.all([
        fetch(url).then(res => {
          if (!res.ok) throw new Error("获取表情包数据失败");
          return res.json();
        }),
        fetch("/api/emotions").then(res => {
          if (!res.ok) throw new Error("获取类别描述失败");
          return res.json();
        })
      ]);

      emojiData.value = emojiRes.categories || {};
      emojiMtimes.value = emojiRes.mtimes || {};
      tagDescriptions.value = tagRes;

      if (pruneSelections) pruneSelections();

      // Default to 'all' if activeCategory is unset or missing
      const categories = Object.keys(emojiData.value);
      if (categories.length > 0) {
        if (!activeCategory.value || (!emojiData.value[activeCategory.value] && activeCategory.value !== 'all')) {
          activeCategory.value = 'all';
        }
      } else {
        activeCategory.value = null;
      }
    } catch (e) {
      console.error(e);
      showToast(e.message, "error", "加载数据失败");
    }
  };

  const fetchPersonas = async () => {
    try {
      const res = await fetch("/api/personas");
      if (!res.ok) throw new Error("获取系统人格失败");
      systemPersonas.value = await res.json();
    } catch (e) {
      console.error(e);
    }
  };

  const fetchPersonaTags = async () => {
    try {
      const res = await fetch("/api/persona_tags");
      if (!res.ok) throw new Error("获取人格专属标签失败");
      personaTags.value = await res.json();
    } catch (e) {
      console.error(e);
    }
  };

  const savePersonaDedicatedTag = async () => {
    const personaId = personaFilter.value;
    if (!personaId) return;

    const tag = personaDedicatedTag.value;
    try {
      const res = await fetch("/api/persona_tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          persona_id: personaId,
          tag: tag
        })
      });
      if (!res.ok) throw new Error("保存专属标签失败");

      if (!tag || !tag.trim()) {
        delete personaTags.value[personaId];
      } else {
        personaTags.value[personaId] = tag.trim();
      }
      showToast("专属标签已保存！", "success", "保存成功");
    } catch (e) {
      showToast(e.message, "error", "保存失败");
    }
  };

  const filteredCategories = computed(() => {
    const query = tabSearchQuery.value.trim().toLowerCase();
    const categories = Object.keys(emojiData.value);
    if (!query) return categories;
    return categories.filter(category => category.toLowerCase().includes(query));
  });

  const filteredDrawerTags = computed(() => {
    const query = drawerTagSearchQuery.value.trim().toLowerCase();
    const tags = Object.keys(emojiData.value);
    if (!query) return tags;
    return tags.filter(tag => tag.toLowerCase().includes(query));
  });

  const emojiTagsMap = computed(() => {
    const map = new Map();
    Object.entries(emojiData.value).forEach(([cat, emos]) => {
      if (Array.isArray(emos)) {
        emos.forEach((emo) => {
          if (!map.has(emo)) map.set(emo, new Set());
          map.get(emo).add(cat);
        });
      }
    });
    return map;
  });

  const allEmojisList = computed(() => {
    const allSet = new Set();
    Object.values(emojiData.value).forEach((list) => {
      if (Array.isArray(list)) {
        list.forEach((emoji) => allSet.add(emoji));
      }
    });
    return Array.from(allSet).sort();
  });

  const importableEmojisList = computed(() => {
    if (!activeCategory.value || activeCategory.value === 'all') return [];
    const currentList = emojiData.value[activeCategory.value] || [];
    return allEmojisList.value.filter((emoji) => !currentList.includes(emoji));
  });

  const activeCategoryTimeGroups = computed(() => {
    if (!activeCategory.value) return [];
    const list = activeCategory.value === 'all' ? allEmojisList.value : (emojiData.value[activeCategory.value] || []);
    
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
    const sevenDaysAgoStart = todayStart - 7 * 24 * 60 * 60 * 1000;

    const groups = [
      { title: "今天 (Today)", list: [] },
      { title: "昨天 (Yesterday)", list: [] },
      { title: "最近一周 (Last 7 Days)", list: [] },
      { title: "更早以前 (Earlier)", list: [] }
    ];

    list.forEach((emoji) => {
      const mtimeSec = emojiMtimes.value[emoji] || 0;
      const mtimeMs = mtimeSec * 1000;
      if (mtimeMs >= todayStart) {
        groups[0].list.push(emoji);
      } else if (mtimeMs >= yesterdayStart) {
        groups[1].list.push(emoji);
      } else if (mtimeMs >= sevenDaysAgoStart) {
        groups[2].list.push(emoji);
      } else {
        groups[3].list.push(emoji);
      }
    });

    groups.forEach((g) => {
      g.list.sort((a, b) => {
        const ta = emojiMtimes.value[a] || 0;
        const tb = emojiMtimes.value[b] || 0;
        return tb - ta;
      });
    });

    // Limit the total number of emojis across all groups to visibleLimit
    let count = 0;
    const limitedGroups = [];
    for (const g of groups) {
      if (g.list.length === 0) continue;
      const remaining = visibleLimit.value - count;
      if (remaining <= 0) break;
      if (g.list.length <= remaining) {
        limitedGroups.push(g);
        count += g.list.length;
      } else {
        limitedGroups.push({
          title: g.title,
          list: g.list.slice(0, remaining)
        });
        count += remaining;
        break;
      }
    }

    return limitedGroups;
  });

  const getEmojiTags = (emoji) => {
    const tags = emojiTagsMap.value.get(emoji);
    return tags ? Array.from(tags).sort() : [];
  };

  return {
    emojiData,
    emojiMtimes,
    tagDescriptions,
    systemPersonas,
    personaTags,
    personaDedicatedTag,
    personaFilter,
    activeCategory,
    tabSearchQuery,
    drawerTagSearchQuery,
    fetchEmojis,
    fetchPersonas,
    fetchPersonaTags,
    savePersonaDedicatedTag,
    filteredCategories,
    filteredDrawerTags,
    emojiTagsMap,
    allEmojisList,
    importableEmojisList,
    activeCategoryTimeGroups,
    getEmojiTags,
    visibleLimit,
  };
}
