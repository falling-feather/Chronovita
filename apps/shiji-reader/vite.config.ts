import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    base: env.VITE_BASE_PATH || "/",
    plugins: [vue()],
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
