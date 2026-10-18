import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  // The Python server exposes bundled UI assets under /ui/.
  base: "/ui/",
  // Encode multiline dependency strings so generated assets have no trailing-space lines.
  esbuild: { supported: { "template-literal": false } },
  plugins: [react(), tailwindcss(), {
    name: "quasar-asset-allowlist",
    generateBundle(_options, bundle) {
      this.emitFile({type: "asset", fileName: "assets.json", source: JSON.stringify({files: Object.keys(bundle).filter(name => /\.(js|css)$/.test(name))})});
    },
  }],
  resolve: { alias: { "@": fileURLToPath(new URL("./frontend", import.meta.url)) } },
  build: {
    outDir: "quasar/static/ui",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: "frontend/main.tsx",
      output: { entryFileNames: "assets/app-shell-[hash].js", chunkFileNames: "assets/[name]-[hash].js", assetFileNames: "assets/[name]-[hash][extname]" },
    },
  },
});
