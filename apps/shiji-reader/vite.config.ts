import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
    base: "./",
    plugins: [vue()],
    server: {
      proxy: { "/api": "http://127.0.0.1:8010" },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
});
