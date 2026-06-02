const { ref, computed } = window.Vue;

export function useApi(showToast, pruneSelections) {
  const emojiData = ref({});
  const emojiMtimes = ref({});
  const emojiDescriptions = ref({});
  const tagDescriptions = ref({});
  const systemPersonas = ref([]);
  const personaTags = ref({});
  const personaUsePreference = ref("");
  const personaCollectPreference = ref("");
  const personaFilter = ref("");
  const activeCategories = ref(['all']);
  
  const tabSearchQuery = ref("");
  const drawerTagSearchQuery = ref("");
  const selectedEmotions = ref([]);
  const visibleLimit = ref(40);

  const fetchEmojis = async () => {
    visibleLimit.value = 40;
    try {
      const personaId = personaFilter.value;
      const pConfig = personaTags.value[personaId] || {};
      personaUsePreference.value = pConfig.meme_use_preference || pConfig.tag || "";
      personaCollectPreference.value = pConfig.meme_preference || "";
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
      emojiDescriptions.value = emojiRes.descriptions || {};
      tagDescriptions.value = tagRes;

      if (pruneSelections) pruneSelections();

      // Default to 'all' if activeCategories is empty or has missing tags
      const categories = Object.keys(emojiData.value);
      if (activeCategories.value.length === 0) {
        activeCategories.value = ['all'];
      } else {
        activeCategories.value = activeCategories.value.filter(
          (cat) => cat === 'all' || categories.includes(cat)
        );
        if (activeCategories.value.length === 0) {
          activeCategories.value = ['all'];
        }
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

  const savePersonaSettings = async () => {
    const personaId = personaFilter.value;
    if (!personaId) return;

    const meme_use_preference = personaUsePreference.value;
    const meme_preference = personaCollectPreference.value;
    try {
      const res = await fetch("/api/persona_tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          persona_id: personaId,
          meme_use_preference: meme_use_preference,
          meme_preference: meme_preference
        })
      });
      if (!res.ok) throw new Error("保存专属配置失败");

      if (!meme_use_preference.trim() && !meme_preference.trim()) {
        delete personaTags.value[personaId];
      } else {
        personaTags.value[personaId] = {
          meme_use_preference: meme_use_preference.trim(),
          meme_preference: meme_preference.trim()
        };
      }
      showToast("专属配置已保存！", "success", "保存成功");
    } catch (e) {
      showToast(e.message, "error", "保存失败");
    }
  };

  const filteredCategories = computed(() => {
    const query = tabSearchQuery.value.trim().toLowerCase();
    const categories = Object.keys(emojiData.value);
    const unselectedCats = categories.filter(cat => !activeCategories.value.includes(cat));
    if (!query) return unselectedCats;
    return unselectedCats.filter(category => category.toLowerCase().includes(query));
  });

  const filteredDrawerTags = computed(() => {
    const query = drawerTagSearchQuery.value.trim().toLowerCase();
    const tags = Object.keys(emojiData.value);
    const unselectedTags = tags.filter(tag => !selectedEmotions.value.includes(tag));
    if (!query) return unselectedTags;
    return unselectedTags.filter(tag => tag.toLowerCase().includes(query));
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

  const activeCategoryEmojisList = computed(() => {
    if (activeCategories.value.includes('all') || activeCategories.value.length === 0) {
      return allEmojisList.value;
    }
    
    const firstCat = activeCategories.value[0];
    let intersection = new Set(emojiData.value[firstCat] || []);
    
    for (let i = 1; i < activeCategories.value.length; i++) {
      const cat = activeCategories.value[i];
      const emojisInCat = new Set(emojiData.value[cat] || []);
      intersection = new Set([...intersection].filter(x => emojisInCat.has(x)));
    }
    
    return Array.from(intersection).sort();
  });

  const importableEmojisList = computed(() => {
    if (activeCategories.value.includes('all') || activeCategories.value.length === 0) return [];
    if (activeCategories.value.length > 1) return [];
    const currentList = emojiData.value[activeCategories.value[0]] || [];
    return allEmojisList.value.filter((emoji) => !currentList.includes(emoji));
  });

  const activeCategoryTimeGroups = computed(() => {
    if (activeCategories.value.length === 0) return [];
    const list = activeCategoryEmojisList.value;
    
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
    emojiDescriptions,
    tagDescriptions,
    systemPersonas,
    personaTags,
    personaUsePreference,
    personaCollectPreference,
    personaFilter,
    activeCategories,
    activeCategoryEmojisList,
    activeEmojisCount: computed(() => activeCategoryEmojisList.value.length),
    tabSearchQuery,
    drawerTagSearchQuery,
    fetchEmojis,
    fetchPersonas,
    fetchPersonaTags,
    savePersonaSettings,
    filteredCategories,
    filteredDrawerTags,
    emojiTagsMap,
    allEmojisList,
    importableEmojisList,
    activeCategoryTimeGroups,
    getEmojiTags,
    visibleLimit,
    selectedEmotions,
  };
}
