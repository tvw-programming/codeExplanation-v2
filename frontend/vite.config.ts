import {
  defineConfig,
  type Plugin,
  type PreviewServer,
  type ViteDevServer,
} from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sirv from "sirv";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");

/**
 * Serves the pipeline's own output under /data, straight off disk.
 *
 * The viewer has to start before the pipeline does — a full run takes
 * many minutes — so it cannot be built around a snapshot of the data.
 * Mounting the real directories means a chunk staged five minutes from
 * now is served the moment it lands, with no copy step and nothing to
 * invalidate.
 *
 * sirv (not a hand-rolled readFile handler) because <video> seeking
 * needs HTTP range requests: that is the whole feature — clicking a
 * file jumps to its offset inside a half-hour mp4.
 */
const MOUNTS: Record<string, string> = {
  // Staged chunk bundles, per-stack manifests, segments.json, project.json
  "/data/chunks": path.join(projectRoot, "render-app", "public", "chunks"),
  // Rendered per-stack videos (video-<stack>.mp4)
  "/data/videos": path.join(projectRoot, "output"),
  // Stack logos used by the video compositions, reused in the sidebar
  "/data/visuals": path.join(projectRoot, "render-app", "public", "visuals"),
  // status.json lives at the root of render-app/public
  "/data/state": path.join(projectRoot, "render-app", "public"),
};

function pipelineData(): Plugin {
  const handlers = Object.entries(MOUNTS).map(([mount, dir]) => ({
    mount,
    // dev: true disables caching/etag reuse, so a file rewritten by the
    // pipeline mid-session is never served stale.
    serve: sirv(dir, { dev: true, etag: true, dotfiles: false }),
  }));

  const attach = (server: ViteDevServer | PreviewServer) => {
    for (const { mount, serve } of handlers) {
      // A miss under /data must 404, not fall through to Vite's SPA
      // fallback: that would answer index.html where the app asked for
      // JSON (parsed as "absent", so survivable) or for an mp4 that
      // does not exist yet (not survivable — the player would try to
      // decode a web page). The pipeline's files legitimately appear
      // minutes apart, so "not there yet" has to read as not there.
      server.middlewares.use(mount, (req, res, next) => {
        serve(req, res, () => {
          if (req.method === "GET" || req.method === "HEAD") {
            res.statusCode = 404;
            res.end(req.method === "HEAD" ? undefined : "not found");
            return;
          }
          next();
        });
      });
    }
  };

  return {
    name: "pipeline-data",
    configureServer(server) {
      attach(server);
    },
    configurePreviewServer(server) {
      attach(server);
    },
  };
}

export default defineConfig({
  root: here,
  plugins: [react(), pipelineData()],
  server: {
    port: Number(process.env.WEB_PORT ?? 5174),
    strictPort: true,
  },
  preview: {
    port: Number(process.env.WEB_PORT ?? 5174),
    strictPort: true,
  },
  build: {
    outDir: path.join(here, "dist"),
    emptyOutDir: true,
  },
});
