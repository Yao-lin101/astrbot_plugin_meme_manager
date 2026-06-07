const { ref } = window.Vue;

export function useConfigApi(showToast) {
  const configSchema = ref(null);
  const configValues = ref(null);
  const loading = ref(false);

  const fetchConfig = async () => {
    loading.value = true;
    try {
      // Fetch schema
      const schemaRes = await fetch("config/schema");
      if (!schemaRes.ok) throw new Error("获取配置 Schema 失败");
      configSchema.value = await schemaRes.json();

      // Fetch values
      const valuesRes = await fetch("config/values");
      if (!valuesRes.ok) throw new Error("获取配置值失败");
      configValues.value = await valuesRes.json();
    } catch (e) {
      console.error(e);
      showToast(e.message, "error", "加载配置失败");
    } finally {
      loading.value = false;
    }
  };

  const saveConfig = async (values) => {
    loading.value = true;
    try {
      const res = await fetch("config/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || "保存配置失败");
      showToast(data.message || "保存成功，插件重载中...", "success", "保存配置");
      configValues.value = JSON.parse(JSON.stringify(values));
    } catch (e) {
      console.error(e);
      showToast(e.message, "error", "保存配置失败");
      throw e;
    } finally {
      loading.value = false;
    }
  };

  return {
    configSchema,
    configValues,
    loading,
    fetchConfig,
    saveConfig,
  };
}
