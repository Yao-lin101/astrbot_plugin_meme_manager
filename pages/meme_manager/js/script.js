import { useToasts } from './modules/toasts.js';
import { useModals } from './modules/modals.js';
import { useApi } from './modules/api.js';
import { useSelection } from './modules/selection.js';
import { useSync } from './modules/sync.js';
import { useCategories } from './modules/categories.js';
import { useEmojiActions } from './modules/emojiActions.js';
import { useDedup } from './modules/dedup.js';

const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

createApp({
  setup() {
    // 1. Toasts
    const { toasts, showToast, removeToast } = useToasts();

    // 2. Modals
    const modals = useModals(showToast);

    // 3. Selection & API
    let pruneSelectionsRef = () => {};
    const api = useApi(showToast, () => pruneSelectionsRef());

    const selection = useSelection(api.emojiData, api.allEmojisList);
    pruneSelectionsRef = selection.pruneSelections;

    // 4. Sync
    const sync = useSync(showToast, api.fetchEmojis);

    // 5. Categories
    const categories = useCategories(
      showToast,
      api.fetchEmojis,
      sync.checkSyncStatus,
      modals.renameCategoryModal,
      modals.addCategoryForm,
      api.emojiData,
      api.activeCategories,
      modals.confirm,
      modals.showDangerConfirm
    );

    // 6. Emoji Actions
    const emojiActions = useEmojiActions({
      showToast,
      fetchEmojis: api.fetchEmojis,
      activeCategories: api.activeCategories,
      selectionEnabled: selection.selectionEnabled,
      selectedEmojis: selection.selectedEmojis,
      systemPersonas: api.systemPersonas,
      emojiData: api.emojiData,
      allEmojisList: api.allEmojisList,
      getEmojiTags: api.getEmojiTags,
      confirm: modals.confirm,
      showDangerConfirm: modals.showDangerConfirm,
      moveModal: modals.moveModal,
      batchPersonaModal: modals.batchPersonaModal,
      importModal: modals.importModal,
      closeImportModal: modals.closeImportModal,
      drawerTagSearchQuery: api.drawerTagSearchQuery,
      selectedEmotions: api.selectedEmotions,
    });

    // 7. Dedup
    const dedup = useDedup(showToast, api.fetchEmojis);

    // Local UI states
    const syncDrawerVisible = ref(false);
    const isDrawerInputFocused = ref(false);

    const getImageUrl = (emoji) => {
      if (!emoji) return '';
      return `/api/file/meme_manager/memes/file/${encodeURIComponent(emoji)}`;
    };

    const activeCategory = computed(() => {
      if (api.activeCategories.value.includes('all')) return 'all';
      if (api.activeCategories.value.length === 0) return 'all';
      return api.activeCategories.value[0];
    });

    const activeCategoriesDisplayName = computed(() => {
      if (api.activeCategories.value.includes('all') || api.activeCategories.value.length === 0) {
        return '全部表情';
      }
      return api.activeCategories.value.join(' & ');
    });

    const selectCategory = (category) => {
      if (category === 'all') {
        api.activeCategories.value = ['all'];
      } else {
        const allIdx = api.activeCategories.value.indexOf('all');
        if (allIdx > -1) api.activeCategories.value.splice(allIdx, 1);

        const idx = api.activeCategories.value.indexOf(category);
        if (idx > -1) {
          api.activeCategories.value.splice(idx, 1);
        } else {
          api.activeCategories.value.push(category);
        }

        if (api.activeCategories.value.length === 0) {
          api.activeCategories.value = ['all'];
        }
      }
      api.visibleLimit.value = 40;
      emojiActions.closeDetailDrawer();
    };

    const sortedActiveEmojisList = computed(() => {
      const list = [...api.activeCategoryEmojisList.value];
      list.sort((a, b) => {
        const ta = api.emojiMtimes.value[a] || 0;
        const tb = api.emojiMtimes.value[b] || 0;
        return tb - ta;
      });
      return list;
    });

    const currentEmojiIndex = computed(() => {
      if (!emojiActions.activeDetailEmoji.value) return -1;
      return sortedActiveEmojisList.value.indexOf(emojiActions.activeDetailEmoji.value);
    });

    const hasPreviousEmoji = computed(() => {
      return currentEmojiIndex.value > 0;
    });

    const hasNextEmoji = computed(() => {
      const idx = currentEmojiIndex.value;
      return idx > -1 && idx < sortedActiveEmojisList.value.length - 1;
    });

    const navigateToSiblingEmoji = (direction) => {
      const idx = currentEmojiIndex.value;
      if (idx === -1) return;
      const targetIdx = idx + direction;
      if (targetIdx >= 0 && targetIdx < sortedActiveEmojisList.value.length) {
        const targetEmoji = sortedActiveEmojisList.value[targetIdx];
        emojiActions.toggleDetailDrawer(activeCategory.value, targetEmoji);
      }
    };

    // Scroll listener for client-side pagination (infinite scroll)
    const handleScroll = () => {
      if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
        const total = api.activeEmojisCount.value;
        if (api.visibleLimit.value < total) {
          api.visibleLimit.value += 20;
        }
      }
    };

    // Lifecycle hooks
    onMounted(async () => {
      if (window.AstrBotPluginPage) {
        await window.AstrBotPluginPage.ready();
      }
      await api.fetchPersonaTags();
      await api.fetchEmojis();
      await api.fetchPersonas();
      void sync.checkSyncStatus(false);
      
      window.addEventListener("scroll", handleScroll);
    });

    onUnmounted(() => {
      window.removeEventListener("scroll", handleScroll);
    });

    return {
      // API States & Computed
      emojiData: api.emojiData,
      emojiMtimes: api.emojiMtimes,
      tagDescriptions: api.tagDescriptions,
      systemPersonas: api.systemPersonas,
      personaTags: api.personaTags,
      personaDedicatedTag: api.personaDedicatedTag,
      personaFilter: api.personaFilter,
      activeCategories: api.activeCategories,
      activeCategory,
      activeCategoriesDisplayName,
      activeCategoryEmojisList: api.activeCategoryEmojisList,
      activeEmojisCount: api.activeEmojisCount,
      tabSearchQuery: api.tabSearchQuery,
      drawerTagSearchQuery: api.drawerTagSearchQuery,
      fetchEmojis: api.fetchEmojis,
      fetchPersonas: api.fetchPersonas,
      fetchPersonaTags: api.fetchPersonaTags,
      savePersonaDedicatedTag: api.savePersonaDedicatedTag,
      filteredCategories: api.filteredCategories,
      filteredDrawerTags: api.filteredDrawerTags,
      emojiTagsMap: api.emojiTagsMap,
      allEmojisList: api.allEmojisList,
      importableEmojisList: api.importableEmojisList,
      activeCategoryTimeGroups: api.activeCategoryTimeGroups,
      getEmojiTags: api.getEmojiTags,
      visibleLimit: api.visibleLimit,

      // Toasts
      toasts,
      showToast,
      removeToast,

      // Selection
      selectedEmojis: selection.selectedEmojis,
      selectionEnabled: selection.selectionEnabled,
      pruneSelections: selection.pruneSelections,
      toggleSelectionMode: selection.toggleSelectionMode,
      isEmojiSelected: selection.isEmojiSelected,
      toggleEmojiSelection: selection.toggleEmojiSelection,
      getCategorySelectedCount: selection.getCategorySelectedCount,
      getVisibleSelectedCount: selection.getVisibleSelectedCount,
      isAllSelectedInCategory: selection.isAllSelectedInCategory,
      toggleCategorySelection: selection.toggleCategorySelection,

      // Modals
      confirmDialog: modals.confirmDialog,
      dangerConfirmDialog: modals.dangerConfirmDialog,
      moveModal: modals.moveModal,
      batchPersonaModal: modals.batchPersonaModal,
      addCategoryForm: modals.addCategoryForm,
      renameCategoryModal: modals.renameCategoryModal,
      importModal: modals.importModal,
      confirm: modals.confirm,
      handleConfirm: modals.handleConfirm,
      showDangerConfirm: modals.showDangerConfirm,
      startDangerCountdown: modals.startDangerCountdown,
      handleDangerConfirm: modals.handleDangerConfirm,
      cancelDangerConfirm: modals.cancelDangerConfirm,
      openBatchPersonaModal: modals.openBatchPersonaModal,
      closeBatchPersonaModal: modals.closeBatchPersonaModal,
      togglePersonaInBatch: modals.togglePersonaInBatch,
      openMoveModal: modals.openMoveModal,
      closeMoveModal: modals.closeMoveModal,
      openImportModal: modals.openImportModal,
      closeImportModal: modals.closeImportModal,
      toggleImportEmoji: modals.toggleImportEmoji,

      // UI States & Navigation
      syncDrawerVisible,
      selectCategory,
      hasPreviousEmoji,
      hasNextEmoji,
      navigateToSiblingEmoji,

      // Sync
      syncChecking: sync.syncChecking,
      syncStatus: sync.syncStatus,
      imgHostSyncing: sync.imgHostSyncing,
      imgHostStatus: sync.imgHostStatus,
      checkSyncStatus: sync.checkSyncStatus,
      syncConfig: sync.syncConfig,
      restoreCategory: sync.restoreCategory,
      removeFromConfig: sync.removeFromConfig,
      checkImgHostSyncStatus: sync.checkImgHostSyncStatus,
      syncToRemote: sync.syncToRemote,
      syncFromRemote: sync.syncFromRemote,

      // Categories
      openRenameCategory: categories.openRenameCategory,
      saveRenameCategory: categories.saveRenameCategory,
      saveNewCategory: categories.saveNewCategory,
      clearCategory: categories.clearCategory,
      deleteCategory: categories.deleteCategory,

      // Emoji Actions
      activeDetailEmoji: emojiActions.activeDetailEmoji,
      detailMetadata: emojiActions.detailMetadata,
      selectedEmotions: api.selectedEmotions,
      selectedPersonas: emojiActions.selectedPersonas,
      detailDrawerLoading: emojiActions.detailDrawerLoading,
      uploadStateByCategory: emojiActions.uploadStateByCategory,
      contextMenu: emojiActions.contextMenu,
      clipboardItems: emojiActions.clipboardItems,
      toggleDetailDrawer: emojiActions.toggleDetailDrawer,
      closeDetailDrawer: emojiActions.closeDetailDrawer,
      toggleTagInDrawer: emojiActions.toggleTagInDrawer,
      togglePersonaInDrawer: emojiActions.togglePersonaInDrawer,
      saveEmojiAttributes: emojiActions.saveEmojiAttributes,
      deleteEmoji: emojiActions.deleteEmoji,
      batchDeleteSelected: emojiActions.batchDeleteSelected,
      batchConvertToGif: emojiActions.batchConvertToGif,
      saveBatchPersonas: emojiActions.saveBatchPersonas,
      handleMoveTarget: emojiActions.handleMoveTarget,
      clearAllEmojiFiles: emojiActions.clearAllEmojiFiles,
      submitImport: emojiActions.submitImport,
      onDragStart: emojiActions.onDragStart,
      onDropEmoji: emojiActions.onDropEmoji,
      triggerFileInput: emojiActions.triggerFileInput,
      onFileSelected: emojiActions.onFileSelected,
      onUploadDrop: emojiActions.onUploadDrop,
      openContextMenu: emojiActions.openContextMenu,
      closeContextMenu: emojiActions.closeContextMenu,
      contextMenuDelete: emojiActions.contextMenuDelete,
      contextMenuMove: emojiActions.contextMenuMove,
      contextMenuCopy: emojiActions.contextMenuCopy,
      contextMenuConvertToGif: emojiActions.contextMenuConvertToGif,
      contextMenuPaste: emojiActions.contextMenuPaste,
      onEmojiClick: emojiActions.onEmojiClick,
      handleCreateTagInDrawer: emojiActions.handleCreateTagInDrawer,
      handleBackspace: emojiActions.handleBackspace,
      isDrawerInputFocused,
      getImageUrl,

      // Dedup
      duplicateModal: dedup.duplicateModal,
      similarityThreshold: dedup.similarityThreshold,
      duplicateGroups: dedup.duplicateGroups,
      formatBytes: dedup.formatBytes,
      openDuplicateModal: dedup.openDuplicateModal,
      closeDuplicateModal: dedup.closeDuplicateModal,
      scanDuplicates: dedup.scanDuplicates,
      toggleMemeAction: dedup.toggleMemeAction,
      resolveDuplicates: dedup.resolveDuplicates,
      totalDeletesCount: dedup.totalDeletesCount,
    };
  },
}).mount("#app");
