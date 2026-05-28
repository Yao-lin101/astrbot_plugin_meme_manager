const { ref } = window.Vue;

export function useToasts() {
  const toasts = ref([]);
  let toastIdCounter = 0;

  const showToast = (message, type = "info", title = "系统提示", duration = 3000) => {
    const id = toastIdCounter++;
    toasts.value.push({ id, message, type, title });
    setTimeout(() => {
      removeToast(id);
    }, duration);
  };

  const removeToast = (id) => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  };

  return {
    toasts,
    showToast,
    removeToast,
  };
}
