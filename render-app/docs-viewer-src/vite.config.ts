import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Builds the standalone MUI documentation viewer into render-app/public/docs-viewer,
// which Remotion's own dev server (`npm run dev`, i.e. `remotion studio`) already
// serves as static assets alongside the video-rendering UI — so the docs viewer
// ships from the exact same render-app project, using the exact same MUI/React
// dependency versions as every other component in render-app (CodeExplainerChunk,
// Composition), rather than a disconnected second toolchain.
export default defineConfig({
  root: __dirname,
  base: "./",
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../public/docs-viewer"),
    emptyOutDir: true,
  },
});
