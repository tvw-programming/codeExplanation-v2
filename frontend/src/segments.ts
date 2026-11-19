/** Playback arithmetic: which seconds of which video a clicked file is,
 *  and when to stop. Pure, so it is tested directly (segments.test.ts).
 *
 *  The pipeline renders one long video per stack. A file's explanation
 *  is a span inside it, published by
 *  render-app/scripts/build-segment-index.ts — so "play middleware.go"
 *  is: load video-go.mp4, seek to its startSeconds, stop at endSeconds.
 */

import type { Chapter, SegmentFile, SegmentIndex } from "./types";

/** Tolerance for comparing a video's currentTime against a boundary.
 *  Browsers report time in fractions of a frame, and a stop that fires
 *  a frame early is better than one that spills into the next file. */
export const BOUNDARY_EPSILON = 0.05;

export function findFile(
  index: SegmentIndex | null,
  filePath: string | null,
): SegmentFile | null {
  if (!index || !filePath) return null;
  return index.files.find((file) => file.filePath === filePath) ?? null;
}

/** The chapter playing at `seconds`, for highlighting the strip under
 *  the player. Returns null outside the file. */
export function chapterAt(file: SegmentFile | null, seconds: number): Chapter | null {
  if (!file) return null;
  return (
    file.chapters.find(
      (chapter) => seconds >= chapter.startSeconds && seconds < chapter.endSeconds,
    ) ?? null
  );
}

/** How far through the selected file playback is, 0..1. */
export function progressWithin(file: SegmentFile | null, seconds: number): number {
  if (!file) return 0;
  const span = file.endSeconds - file.startSeconds;
  if (span <= 0) return 0;
  const offset = seconds - file.startSeconds;
  return Math.min(1, Math.max(0, offset / span));
}

/**
 * Whether this file is actually reachable in the video that exists.
 *
 * `./run-local.sh --preview` renders only the opening stretch to
 * video-<stack>-preview.mp4. Everything past that window is in the
 * index but not in the file, so a click would seek past the end and
 * play nothing — the sidebar greys those out instead.
 *
 * `videoDuration` is what the <video> element reported; null means the
 * video has not loaded (or does not exist) yet.
 */
export function isPlayable(file: SegmentFile, videoDuration: number | null): boolean {
  if (videoDuration === null || !Number.isFinite(videoDuration)) return false;
  return file.startSeconds < videoDuration - BOUNDARY_EPSILON;
}

/**
 * What the sidebar shows: playable, or waiting on a render.
 *
 * Only the stack currently in the player has reported a duration —
 * the others have no <video> element to ask. Treating "no duration" as
 * "not playable" would mark every other stack's files unavailable even
 * though their videos are sitting on disk, so a stack with a video is
 * playable until its own duration proves otherwise (which it does as
 * soon as the user switches to it and a --preview window shows up).
 */
export function isReachable(
  file: SegmentFile,
  options: { hasVideo: boolean; videoDuration: number | null },
): boolean {
  if (!options.hasVideo) return false;
  if (options.videoDuration === null || !Number.isFinite(options.videoDuration)) return true;
  return isPlayable(file, options.videoDuration);
}

/** True when the loaded video is visibly shorter than the index says
 *  the full render is — i.e. we are looking at a --preview render. */
export function looksLikePreview(
  index: SegmentIndex | null,
  videoDuration: number | null,
): boolean {
  if (!index || videoDuration === null || !Number.isFinite(videoDuration)) return false;
  return videoDuration < index.totalSeconds - 1;
}

/** Where to seek for a file (or one of its chapters), clamped to what
 *  the loaded video actually contains. */
export function seekTarget(
  file: SegmentFile,
  videoDuration: number | null,
  chapter?: Chapter | null,
): number {
  const start = chapter ? chapter.startSeconds : file.startSeconds;
  if (videoDuration === null || !Number.isFinite(videoDuration)) return start;
  return Math.min(start, Math.max(0, videoDuration - BOUNDARY_EPSILON));
}

/**
 * Where playback should stop.
 *
 * Returns null when nothing should stop it — "play the whole stack
 * video" mode, where the point is to watch straight through.
 */
export function stopAt(
  file: SegmentFile | null,
  options: { continuous: boolean; chapter?: Chapter | null },
): number | null {
  if (!file || options.continuous) return null;
  return options.chapter ? options.chapter.endSeconds : file.endSeconds;
}

/** True when playback has reached the stop point and should pause. */
export function shouldPause(currentSeconds: number, stop: number | null): boolean {
  if (stop === null) return false;
  return currentSeconds >= stop - BOUNDARY_EPSILON;
}

/** mm:ss, for the chapter strip and the file rows. */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/** "3 min 12 s" style duration for a file's total length. */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes === 0) return `${rest}s`;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}
