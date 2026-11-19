/** The player. One long video per stack; a selected file is a span
 *  inside it, so selecting one seeks to its start and stops at its end.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { videoUrl } from "./api";
import {
  chapterAt,
  formatTime,
  looksLikePreview,
  progressWithin,
  seekTarget,
  shouldPause,
  stopAt,
} from "./segments";
import { NEUTRAL_STACK_COLOR } from "./theme";
import type { Chapter, SegmentFile, StackView } from "./types";

const SPEEDS = [1, 1.25, 1.5, 2];

type Props = {
  view: StackView | null;
  file: SegmentFile | null;
  onDuration: (stack: string, duration: number | null) => void;
};

export const VideoPanel: React.FC<Props> = ({ view, file, onDuration }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState<number | null>(null);
  const [continuous, setContinuous] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [failed, setFailed] = useState(false);

  const stack = view?.stack.name ?? null;
  const src = view?.videoUrl ? videoUrl(view.videoUrl) : null;
  const color = view?.index?.theme?.onDark ?? view?.index?.theme?.primary ?? NEUTRAL_STACK_COLOR;

  // A new video file: forget the old one's duration before anything
  // reads it, so a stale length can never gate the wrong tree.
  useEffect(() => {
    setDuration(null);
    setFailed(false);
    setChapter(null);
  }, [src]);

  /** Seek to wherever the selection points, once the video knows its
   *  own length. Called both from the selection effect and from
   *  loadedmetadata, because which happens first depends on the cache. */
  const seekToSelection = useCallback(
    (target: SegmentFile | null, within: Chapter | null) => {
      const element = videoRef.current;
      if (!element || !target) return;
      const known = Number.isFinite(element.duration) ? element.duration : null;
      element.currentTime = seekTarget(target, known, within);
      void element.play().catch(() => {
        // Autoplay can be refused (no user gesture yet); the frame is
        // still parked on the right moment, so the user just presses play.
      });
    },
    [],
  );

  useEffect(() => {
    setChapter(null);
    if (file) seekToSelection(file, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file?.chunkId, src]);

  useEffect(() => {
    const element = videoRef.current;
    if (element) element.playbackRate = speed;
  }, [speed, src]);

  const handleLoadedMetadata = () => {
    const element = videoRef.current;
    if (!element) return;
    const known = Number.isFinite(element.duration) ? element.duration : null;
    setDuration(known);
    if (stack) onDuration(stack, known);
    element.playbackRate = speed;
    if (file) seekToSelection(file, chapter);
  };

  const handleTimeUpdate = () => {
    const element = videoRef.current;
    if (!element) return;
    setCurrentTime(element.currentTime);
    const stop = stopAt(file, { continuous, chapter });
    if (shouldPause(element.currentTime, stop)) {
      element.pause();
    }
  };

  const playChapter = (next: Chapter) => {
    setChapter(next);
    const element = videoRef.current;
    if (!element || !file) return;
    const known = Number.isFinite(element.duration) ? element.duration : null;
    element.currentTime = seekTarget(file, known, next);
    void element.play().catch(() => undefined);
  };

  if (!view) {
    return (
      <Box sx={{ p: 4 }}>
        <Typography color="text.secondary">
          No technology has been staged yet. The tree fills in as the pipeline finishes
          each stack.
        </Typography>
      </Box>
    );
  }

  const activeChapter = chapterAt(file, currentTime);
  const isPreview = looksLikePreview(view.index, duration);
  const outOfRange = Boolean(
    file && duration !== null && file.startSeconds >= duration,
  );

  return (
    <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 1.5, height: "100%" }}>
      <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap">
        <Typography variant="h6" sx={{ fontFamily: "ui-monospace, monospace" }}>
          {file ? file.filePath : view.stack.name}
        </Typography>
        {file?.featureName ? (
          <Chip size="small" label={file.featureName} sx={{ bgcolor: "rgba(255,255,255,0.07)" }} />
        ) : null}
        <Box sx={{ flexGrow: 1 }} />
        {file ? (
          <Typography variant="caption" color="text.secondary">
            {formatTime(file.startSeconds)} – {formatTime(file.endSeconds)} of{" "}
            {view.stack.name} video
          </Typography>
        ) : null}
      </Stack>

      {!src ? (
        <Alert severity="info" variant="outlined">
          <strong>{view.stack.name}</strong>'s video has not been rendered yet. The file
          tree and every file's analysis are already readable — the player becomes live
          when <code>output/{view.stack.video}</code> lands.
        </Alert>
      ) : null}

      {failed && src ? (
        <Alert severity="warning" variant="outlined">
          Could not load <code>{view.videoUrl}</code>. It may still be being written —
          this page retries on its own as the pipeline reports progress.
        </Alert>
      ) : null}

      {isPreview && !failed ? (
        <Alert severity="info" variant="outlined">
          This is a <code>--preview</code> render: only the first{" "}
          {formatTime(duration ?? 0)} of {formatTime(view.index?.totalSeconds ?? 0)} exists,
          so files past that point are greyed out. Re-run{" "}
          <code>./run-local.sh</code> without <code>--preview</code> for the whole thing.
        </Alert>
      ) : null}

      {outOfRange ? (
        <Alert severity="warning" variant="outlined">
          <strong>{file?.fileName}</strong> starts at {formatTime(file?.startSeconds ?? 0)},
          past the end of the video that exists.
        </Alert>
      ) : null}

      <Box
        sx={{
          position: "relative",
          bgcolor: "#000",
          borderRadius: 2,
          overflow: "hidden",
          flexGrow: 1,
          minHeight: 0,
          display: "flex",
        }}
      >
        {src ? (
          <video
            ref={videoRef}
            key={src}
            src={src}
            controls
            preload="metadata"
            onLoadedMetadata={handleLoadedMetadata}
            onTimeUpdate={handleTimeUpdate}
            onError={() => setFailed(true)}
            style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
          />
        ) : null}
      </Box>

      {file ? (
        <Box>
          <LinearProgress
            variant="determinate"
            value={progressWithin(file, currentTime) * 100}
            sx={{
              height: 4,
              borderRadius: 2,
              bgcolor: "rgba(255,255,255,0.08)",
              "& .MuiLinearProgress-bar": { bgcolor: color },
            }}
          />
          <Stack
            direction="row"
            spacing={0.75}
            sx={{ mt: 1, flexWrap: "wrap", rowGap: 0.75 }}
            alignItems="center"
          >
            {file.chapters.map((entry) => (
              <Chip
                key={entry.kind}
                size="small"
                label={`${entry.label} · ${formatTime(entry.endSeconds - entry.startSeconds)}`}
                onClick={() => playChapter(entry)}
                variant={activeChapter?.kind === entry.kind ? "filled" : "outlined"}
                sx={{
                  cursor: "pointer",
                  borderColor: "rgba(255,255,255,0.15)",
                  bgcolor:
                    activeChapter?.kind === entry.kind ? `${color}33` : "transparent",
                }}
              />
            ))}
            <Box sx={{ flexGrow: 1 }} />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={continuous}
                  onChange={(event) => setContinuous(event.target.checked)}
                />
              }
              label={
                <Typography variant="caption" color="text.secondary">
                  Keep playing past this file
                </Typography>
              }
            />
            <ButtonGroup size="small" variant="outlined">
              {SPEEDS.map((rate) => (
                <Button
                  key={rate}
                  onClick={() => setSpeed(rate)}
                  variant={speed === rate ? "contained" : "outlined"}
                >
                  {rate}×
                </Button>
              ))}
            </ButtonGroup>
          </Stack>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Pick a file on the left to jump straight to its explanation.
        </Typography>
      )}
    </Box>
  );
};
