export const SEND_MODES = Object.freeze({
  STICKER: "sticker",
  IMAGE: "image",
});

export const normalizeSendMode = (mode) => {
  return mode === SEND_MODES.IMAGE ? SEND_MODES.IMAGE : SEND_MODES.STICKER;
};
