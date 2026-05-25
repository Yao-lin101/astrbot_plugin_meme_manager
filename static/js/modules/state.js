// state.js - Centralized state management for the Meme Manager WebUI

export const state = {
  selectionState: {
    enabled: false,
    items: new Map(),
  },
  latestEmojiData: {},
  dangerConfirmResolver: null,
  dangerConfirmStage: "ack",
  dangerConfirmTimer: null,
  dangerConfirmConfig: null,
  longPressState: {
    emojiItem: null,
    pointerId: null,
    startTime: 0,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    timeoutId: null,
    intervalId: null,
  },
  dragModeState: {
    items: [],
    timeoutId: null,
    pointerId: null,
    activeCategory: null,
    isPointerDragging: false,
    captureElement: null,
    autoScrollFrameId: null,
    lastClientX: 0,
    lastClientY: 0,
  },
  clipboardState: {
    items: [],
  },
  contextMenuState: {
    items: [],
    targetCategory: null,
  },
  uploadStateByCategory: new Map(),
  requestState: {
    emojis: { controller: null, seq: 0 },
    syncStatus: { controller: null, seq: 0 },
    imgHostStatus: { controller: null, seq: 0 },
  },
  initialStatusTimerId: null,
  activeCategoryEdit: null,
  pendingMoveTargetItems: [],
  systemPersonas: [],
};

// State helper functions
export function pruneSelectionState() {
  const nextItems = new Map();
  for (const [key, item] of state.selectionState.items.entries()) {
    const list = state.latestEmojiData[item.category];
    if (Array.isArray(list) && list.includes(item.emoji)) {
      nextItems.set(key, item);
    }
  }
  state.selectionState.items = nextItems;
}
