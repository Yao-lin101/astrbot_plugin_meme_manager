const { ref, watch, onUnmounted } = window.Vue;

const EMPTY_IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export function useImages(emojiMtimes) {
  const imageUrls = ref(new Map());
  const fullyLoadedEmojis = ref(new Set());
  const pendingRequests = new Map();
  let hoverTimer = null;

  const loadImage = (emoji, isThumbnail = false) => {
    if (!emoji) return Promise.resolve(EMPTY_IMAGE);
    const key = JSON.stringify([emoji, emojiMtimes.value[emoji] || 0, isThumbnail]);
    if (imageUrls.value.has(key)) return Promise.resolve(imageUrls.value.get(key) || EMPTY_IMAGE);
    if (pendingRequests.has(key)) return pendingRequests.get(key);

    const request = Promise.resolve().then(async () => {
      const bridge = window.AstrBotPluginPage;
      await bridge.ready();
      const image = await bridge.apiGet('emoji/file_base64', {
        filename: emoji,
        thumbnail: isThumbnail ? '1' : '0'
      });
      if (!image?.base64 || image.status === 'error') {
        throw new Error(image?.message || 'Image data is missing');
      }
      const url = `data:${image.content_type || image.mime || 'image/png'};base64,${image.base64}`;
      if (pendingRequests.get(key) === request) imageUrls.value.set(key, url);
      return url;
    }).catch(error => {
      console.error('Failed to load meme image:', emoji, error);
      // Remember failures until the next list refresh to avoid render retry loops.
      if (pendingRequests.get(key) === request) imageUrls.value.set(key, null);
      return EMPTY_IMAGE;
    }).finally(() => {
      if (pendingRequests.get(key) === request) pendingRequests.delete(key);
    });
    pendingRequests.set(key, request);
    return request;
  };

  const getImageUrl = (emoji, isThumbnail = false) => {
    if (!emoji) return EMPTY_IMAGE;
    const thumbnail = isThumbnail && !fullyLoadedEmojis.value.has(emoji);
    const mtime = emojiMtimes.value[emoji] || 0;
    const key = JSON.stringify([emoji, mtime, thumbnail]);
    if (!imageUrls.value.has(key)) void loadImage(emoji, thumbnail);
    // Keep the thumbnail visible while the original GIF is loading.
    return imageUrls.value.get(key)
      || imageUrls.value.get(JSON.stringify([emoji, mtime, true]))
      || EMPTY_IMAGE;
  };

  const markEmojiFullyLoaded = (emoji) => {
    if (emoji) fullyLoadedEmojis.value.add(emoji);
  };

  const onMouseEnterEmoji = (emoji) => {
    if (!emoji || fullyLoadedEmojis.value.has(emoji)) return;
    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => markEmojiFullyLoaded(emoji), 500);
  };

  const onMouseLeaveEmoji = () => {
    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = null;
  };

  watch(emojiMtimes, (next, previous) => {
    for (const cache of [imageUrls.value, pendingRequests]) {
      for (const key of cache.keys()) {
        const [emoji, mtime] = JSON.parse(key);
        if (cache.get(key) === null || (next[emoji] || 0) !== mtime
          || (emoji in previous && !(emoji in next))) {
          cache.delete(key);
        }
      }
    }
    for (const emoji of fullyLoadedEmojis.value) {
      if (next[emoji] !== previous[emoji]) fullyLoadedEmojis.value.delete(emoji);
    }
  });

  onUnmounted(() => {
    onMouseLeaveEmoji();
    pendingRequests.clear();
    imageUrls.value.clear();
  });

  return { loadImage, getImageUrl, markEmojiFullyLoaded, onMouseEnterEmoji, onMouseLeaveEmoji };
}
