import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { afterEach, test } from 'node:test';
import { setImmediate as nextTurn } from 'node:timers/promises';
import vm from 'node:vm';

const vue = vm.runInNewContext(
  `${readFileSync(new URL('../pages/meme_manager/vendor/vue.global.prod.js', import.meta.url), 'utf8')}; Vue;`,
  { console, setTimeout, clearTimeout }
);
const cleanups = [];
globalThis.window = {
  Vue: { ...vue, onUnmounted: callback => cleanups.push(callback) }
};
const { useImages } = await import(new URL('../pages/meme_manager/js/modules/images.js', import.meta.url));

afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup());
});

function setup(apiGet, mtimes = {}) {
  const calls = [];
  window.AstrBotPluginPage = {
    ready: async () => {},
    apiGet: async (endpoint, params) => {
      calls.push({ endpoint, params });
      return apiGet(params);
    }
  };
  const timestamps = vue.ref(mtimes);
  const scope = vue.effectScope();
  cleanups.push(() => scope.stop());
  const images = scope.run(() => useImages(timestamps));
  return { images, calls, timestamps };
}

test('loads on demand, deduplicates bridge requests, and reuses Base64 images', async () => {
  let resolveImage;
  const { images, calls } = setup(() => new Promise(resolve => { resolveImage = resolve; }));
  assert.equal(calls.length, 0);
  const filename = '表情 & + % #.gif';
  const placeholder = images.getImageUrl(filename, true);
  assert.ok(placeholder.startsWith('data:image/'));
  images.getImageUrl(filename, true);
  await nextTurn();
  assert.deepEqual(calls, [{ endpoint: 'emoji/file_base64', params: { filename, thumbnail: '1' } }]);
  resolveImage({ content_type: 'image/webp', base64: 'dGh1bWI=' });
  await nextTurn();
  assert.equal(images.getImageUrl(filename, true), 'data:image/webp;base64,dGh1bWI=');
  assert.equal(await images.loadImage(filename, true), 'data:image/webp;base64,dGh1bWI=');
  assert.equal(calls.length, 1);
});

test('keeps the thumbnail visible while the original GIF loads', async () => {
  let resolveOriginal;
  const { images, calls } = setup(params => params.thumbnail === '1'
    ? { content_type: 'image/webp', base64: 'dGh1bWI=' }
    : new Promise(resolve => { resolveOriginal = resolve; }));
  const thumbnail = await images.loadImage('animated.gif', true);
  images.markEmojiFullyLoaded('animated.gif');
  assert.equal(images.getImageUrl('animated.gif', true), thumbnail);
  await nextTurn();
  assert.equal(calls.at(-1).params.thumbnail, '0');
  resolveOriginal({ mime: 'image/gif', base64: 'Z2lm' });
  await nextTurn();
  assert.equal(images.getImageUrl('animated.gif', true), 'data:image/gif;base64,Z2lm');
});

test('refreshes changed images and ignores outdated in-flight responses', async () => {
  const resolvers = [];
  const { images, calls, timestamps } = setup(
    () => new Promise(resolve => resolvers.push(resolve)), { 'image.png': 1 }
  );
  images.getImageUrl('image.png', true);
  await nextTurn();
  timestamps.value = { 'image.png': 2 };
  await vue.nextTick();
  images.getImageUrl('image.png', true);
  await nextTurn();
  assert.equal(calls.length, 2);
  resolvers[1]({ mime: 'image/png', base64: 'bmV3' });
  await nextTurn();
  resolvers[0]({ mime: 'image/png', base64: 'b2xk' });
  await nextTurn();
  assert.equal(images.getImageUrl('image.png', true), 'data:image/png;base64,bmV3');
});

test('does not loop on failures and retries after a list refresh', async t => {
  t.mock.method(console, 'error', () => {});
  let failed = true;
  const { images, calls, timestamps } = setup(() => {
    if (failed) throw new Error('Missing image');
    return { mime: 'image/png', base64: 'b2s=' };
  }, { 'image.png': 1 });
  images.getImageUrl('image.png', true);
  await nextTurn();
  images.getImageUrl('image.png', true);
  await nextTurn();
  assert.equal(calls.length, 1);
  failed = false;
  timestamps.value = { 'image.png': 1 };
  await vue.nextTick();
  images.getImageUrl('image.png', true);
  await nextTurn();
  assert.equal(calls.length, 2);
  assert.equal(images.getImageUrl('image.png', true), 'data:image/png;base64,b2s=');
});

test('switches to the original after hovering and cancels when the pointer leaves', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { images, calls } = setup(params => ({
    content_type: params.thumbnail === '1' ? 'image/webp' : 'image/gif', base64: 'b2s='
  }));
  await images.loadImage('animated.gif', true);
  images.onMouseEnterEmoji('animated.gif');
  t.mock.timers.tick(499);
  assert.equal(images.getImageUrl('animated.gif', true), 'data:image/webp;base64,b2s=');
  images.onMouseLeaveEmoji();
  t.mock.timers.tick(1);
  images.getImageUrl('animated.gif', true);
  await nextTurn();
  assert.equal(calls.length, 1);

  images.onMouseEnterEmoji('animated.gif');
  t.mock.timers.tick(500);
  images.getImageUrl('animated.gif', true);
  await nextTurn();
  assert.equal(images.getImageUrl('animated.gif', true), 'data:image/gif;base64,b2s=');
  assert.equal(calls.length, 2);
});
