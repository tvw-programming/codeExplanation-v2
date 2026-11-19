/** The viewer shell.
 *
 *  Starts before the pipeline does (run-local.sh brings it up first,
 *  since a full run is minutes of narration and video), so every piece
 *  of data here is "maybe not yet": the app polls what the pipeline has
 *  published and fills in as it lands.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";

import { loadOverview, loadProject, loadSegments, loadStatus, videoExists } from "./api";
import { FileMeta } from "./FileMeta";
import { findFile } from "./segments";
import { StackTree } from "./StackTree";
import { VideoPanel } from "./VideoPanel";
import type {
  FileOverview,
  PipelineStatus,
  ProjectManifest,
  SegmentIndex,
  StackView,
} from "./types";

const POLL_MS = 3000;

type Selection = { stack: string; filePath: string } | null;

/** ?stack=go&file=api/cmd/server/main.go — so a file view survives a
 *  reload and can be pasted to someone else. */
function selectionFromUrl(): Selection {
  const params = new URLSearchParams(window.location.search);
  const stack = params.get("stack");
  const filePath = params.get("file");
  return stack && filePath ? { stack, filePath } : null;
}

function writeSelectionToUrl(selection: Selection): void {
  const url = new URL(window.location.href);
  if (selection) {
    url.searchParams.set("stack", selection.stack);
    url.searchParams.set("file", selection.filePath);
  } else {
    url.searchParams.delete("stack");
    url.searchParams.delete("file");
  }
  window.history.replaceState(null, "", url);
}

export const App: React.FC = () => {
  const [project, setProject] = useState<ProjectManifest | null>(null);
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [indexes, setIndexes] = useState<Record<string, SegmentIndex>>({});
  const [videoFiles, setVideoFiles] = useState<Record<string, { file: string; preview: boolean }>>(
    {},
  );
  const [durations, setDurations] = useState<Record<string, number | null>>({});
  const [selection, setSelection] = useState<Selection>(selectionFromUrl);
  const [overview, setOverview] = useState<FileOverview | null>(null);
  const [firstLoadDone, setFirstLoadDone] = useState(false);

  // Keeps the poll loop from stacking requests if the disk is slow.
  const pollingRef = useRef(false);

  const poll = useCallback(async () => {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const [nextProject, nextStatus] = await Promise.all([loadProject(), loadStatus()]);
      if (nextProject) setProject(nextProject);
      if (nextStatus) setStatus(nextStatus);

      const stacks = nextProject?.stacks ?? [];
      if (stacks.length > 0) {
        const loaded = await Promise.all(
          stacks.map(async (stack) => {
            const index = await loadSegments(stack.name);
            // Prefer the full render; fall back to the --preview file so
            // a quick run is still watchable.
            const full = await videoExists(stack.video);
            const preview = full ? false : await videoExists(stack.previewVideo);
            return {
              name: stack.name,
              index,
              video: full
                ? { file: stack.video, preview: false }
                : preview
                  ? { file: stack.previewVideo, preview: true }
                  : null,
            };
          }),
        );

        setIndexes((previous) => {
          const next = { ...previous };
          for (const entry of loaded) if (entry.index) next[entry.name] = entry.index;
          return next;
        });
        setVideoFiles((previous) => {
          const next = { ...previous };
          for (const entry of loaded) {
            if (entry.video) next[entry.name] = entry.video;
            else delete next[entry.name];
          }
          return next;
        });
      }
    } finally {
      pollingRef.current = false;
      setFirstLoadDone(true);
    }
  }, []);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => {
      // Keep polling until the run is finished: the last thing to land
      // is a video, and that is exactly what the player is waiting for.
      if (status?.done && Object.keys(videoFiles).length >= (project?.stacks.length ?? 0)) {
        return;
      }
      void poll();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [poll, status?.done, videoFiles, project?.stacks.length]);

  const views = useMemo<StackView[]>(
    () =>
      (project?.stacks ?? []).map((stack) => {
        const video = videoFiles[stack.name] ?? null;
        return {
          stack,
          index: indexes[stack.name] ?? null,
          videoUrl: video?.file ?? null,
          isPreview: video?.preview ?? false,
          previewSeconds: null,
        };
      }),
    [project, indexes, videoFiles],
  );

  const activeView = useMemo(
    () =>
      views.find((view) => view.stack.name === selection?.stack) ??
      views.find((view) => view.index) ??
      views[0] ??
      null,
    [views, selection],
  );

  const activeFile = useMemo(
    () => findFile(activeView?.index ?? null, selection?.filePath ?? null),
    [activeView, selection],
  );

  // The analysis for a file is readable long before its video exists,
  // so it is fetched on selection regardless of render state.
  useEffect(() => {
    let cancelled = false;
    if (!activeView || !activeFile) {
      setOverview(null);
      return;
    }
    void loadOverview(activeView.stack.name, activeFile.chunkId).then((next) => {
      if (!cancelled) setOverview(next);
    });
    return () => {
      cancelled = true;
    };
  }, [activeView?.stack.name, activeFile?.chunkId]);

  const select = (stack: string, filePath: string) => {
    const next = { stack, filePath };
    setSelection(next);
    writeSelectionToUrl(next);
  };

  const onDuration = useCallback((stack: string, duration: number | null) => {
    setDurations((previous) =>
      previous[stack] === duration ? previous : { ...previous, [stack]: duration },
    );
  }, []);

  const progress =
    status && status.chunksTotal > 0
      ? (status.chunksRendered / status.chunksTotal) * 100
      : null;

  return (
    <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <AppBar position="static" color="transparent" elevation={0}>
        <Toolbar variant="dense" sx={{ gap: 1.5, borderBottom: 1, borderColor: "divider" }}>
          <Typography sx={{ fontWeight: 700 }}>
            {project?.repoName ?? "Code explanation"}
          </Typography>
          {project?.projectType.architecture ? (
            <Chip
              size="small"
              label={project.projectType.architecture}
              sx={{ height: 20, bgcolor: "rgba(255,255,255,0.06)" }}
            />
          ) : null}
          <Box sx={{ flexGrow: 1 }} />
          {status ? (
            <Stack direction="row" spacing={1} alignItems="center">
              {!status.done ? <CircularProgress size={14} /> : null}
              <Typography variant="caption" color="text.secondary">
                {status.phaseLabel}
                {status.chunksTotal > 0 && !status.done
                  ? ` — ${status.chunksRendered}/${status.chunksTotal} chunks`
                  : ""}
              </Typography>
            </Stack>
          ) : null}
        </Toolbar>
        {progress !== null && !status?.done ? (
          <LinearProgress variant="determinate" value={progress} sx={{ height: 2 }} />
        ) : null}
      </AppBar>

      {status?.error ? (
        <Alert severity="error" variant="outlined" sx={{ m: 2 }}>
          The pipeline reported: {status.error}
        </Alert>
      ) : null}

      <Box sx={{ display: "flex", flexGrow: 1, minHeight: 0 }}>
        <Box
          sx={{
            width: 340,
            flexShrink: 0,
            borderRight: 1,
            borderColor: "divider",
            overflowY: "auto",
          }}
        >
          {views.length > 0 ? (
            <StackTree
              views={views}
              selected={selection}
              durations={durations}
              onSelect={select}
            />
          ) : (
            <Box sx={{ p: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {!firstLoadDone
                  ? "Loading…"
                  : status && !status.done
                    ? `The pipeline is running (${status.phaseLabel.toLowerCase()}). ` +
                      "The technologies it detects will appear here as soon as their " +
                      "chunks are staged."
                  : "Nothing has been analysed yet. Run ./run-local.sh to analyse the " +
                    "repo in pipeline.config.yaml."}
              </Typography>
            </Box>
          )}
        </Box>

        <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <VideoPanel view={activeView} file={activeFile} onDuration={onDuration} />
        </Box>

        <Divider orientation="vertical" flexItem />
        <Box sx={{ width: 300, flexShrink: 0, overflowY: "auto" }}>
          <FileMeta file={activeFile} overview={overview} />
        </Box>
      </Box>
    </Box>
  );
};
