import { useCallback, useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  staticFile,
  useCurrentFrame,
  useDelayRender,
} from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { DiagramHeader } from "./DiagramHeader";
import { HEADER_HEIGHT as DIAGRAM_HEADER_HEIGHT } from "./treeLayout";
import type { PhaseStyleMode } from "./phaseStyle";
import {
  AnimatedBulletList,
  Split7030,
  TickerBar,
} from "./fancyLayout";
import {
  honestyTickerLabel,
  resolveFancyPatterns,
  type HonestyHints,
} from "./fancyLayout/phaseLayoutMatrix";
import { resolveMatrixStackKey } from "./fancyLayout/stackResolve";
import { type VisualTheme, themeForStack } from "./visualTheme";

// Shared per-chunk view, used by both the single-chunk demo composition
// (CodeExplainerChunk, reading from public/sample-chunk/) and the
// full-repo video (FullVideo, reading from public/chunks/<chunkId>/ —
// one sequence per chunk, laid out back-to-back by <Series> in
// FullVideo.tsx). `useCurrentFrame()` here is relative to whichever
// <Series.Sequence> this instance is mounted inside, so the same
// highlight-timing logic works unchanged in both places.
//
// Layout is a fixed grid rather than flow layout because the code
// panel's scroll position is computed in pixels from a known line
// height — the panel has to scroll to whichever line the narrator is
// talking about, and that math only holds if every line is exactly
// LINE_HEIGHT tall.

export type HighlightCue = {
  id: string;
  lineRange: [number, number];
  fromFrame: number;
  toFrame: number;
  // Window the highlight is actually shown for: held for a readable
  // minimum and until the next cue starts (see highlight_config.py).
  // Older bundles have only the anchor frames, hence the fallback.
  displayFromFrame?: number;
  displayToFrame?: number;
  displayShifted?: boolean;
  assumed: boolean;
  note: string | null;
};

export type NarrationSegment = {
  label: string;
  kind?: string;
  // Short line for the list. `spoken` is the fuller narration that is
  // actually being read aloud; the active item shows it so the panel
  // carries the detail while the rest stay scannable.
  text: string;
  spoken?: string;
  fromFrame: number;
  toFrame: number;
  assumed: boolean;
  note: string | null;
};

/** Summaries are written as "name — what it does"; the name is pulled
 *  out so it can be shown as a heading for the item. */
function splitSummary(text: string): { title: string | null; detail: string } {
  const separator = text.indexOf(" — ");
  if (separator === -1) {
    return { title: null, detail: text };
  }
  return {
    title: text.slice(0, separator).trim(),
    detail: text.slice(separator + 3).trim(),
  };
}

export type Bundle = {
  chunkId: string;
  filePath?: string | null;
  featureName?: string | null;
  durationMs: number;
  alignmentSource: string;
  ttsEngine?: string;
  cleanText: string;
  narrationSegments?: NarrationSegment[];
  highlightConfig: HighlightCue[];
  visualTheme?: VisualTheme | null;
  stack?: string | null;
};


const WIDTH = 1280;
const HEIGHT = 720;
/** Match DiagramHeader / FullVideo chrome height. */
const HEADER_HEIGHT = DIAGRAM_HEADER_HEIGHT;
const NARRATION_WIDTH = 400;

const CODE_FONT_SIZE = 15;
const LINE_HEIGHT = 24;
const CODE_PAD_Y = 20;
const CODE_PAD_X = 22;
const GUTTER_WIDTH = 46;

const CODE_VIEWPORT_HEIGHT = HEIGHT - HEADER_HEIGHT - CODE_PAD_Y * 2;
const VISIBLE_LINES = Math.floor(CODE_VIEWPORT_HEIGHT / LINE_HEIGHT);

// Frames spent easing from one scroll position to the next.
const SCROLL_RAMP = 14;

const NARRATION_PAD = 22;
const NARRATION_VIEWPORT_HEIGHT = HEIGHT - HEADER_HEIGHT - NARRATION_PAD * 2;
const NARRATION_FONT_SIZE = 15;
const NARRATION_LINE_HEIGHT = 21;
const NARRATION_ITEM_GAP = 13;
const NARRATION_BADGE_COLUMN = 30;
// Rough average advance width of the sans-serif face at
// NARRATION_FONT_SIZE, used only to predict how many lines a segment
// wraps to so the list can scroll the active item into view.
const NARRATION_CHAR_WIDTH = 7.7;

const ACCENT = "#60a5fa";
const DIM_TEXT = "#8b9099";

// Width of the bar down the left of a selected block.
const SELECTION_BAR_WIDTH = 4;
// How far unselected code fades back while a block is selected.
const UNSELECTED_DIM = 0.45;

// Timing now lives in segmentTiming.ts so the viewer's segment index
// and this video are laid out by the same function — re-exported here
// so every existing import keeps working.
export { bundleDurationInFrames } from "./segmentTiming";

export async function fetchBundle(chunkDir: string): Promise<Bundle> {
  const res = await fetch(staticFile(`${chunkDir}/bundle.json`));
  return res.json();
}

function cueWindow(cue: HighlightCue): [number, number] {
  const from = cue.displayFromFrame ?? cue.fromFrame;
  const to = cue.displayToFrame ?? cue.toFrame;
  return [from, Math.max(to, from + 1)];
}

/** Scroll offset, in pixels, that brings a cue's lines into view:
 *  centred when the range fits on screen, top-aligned with a couple of
 *  lines of lead-in when it is taller than the viewport. */
function scrollForCue(cue: HighlightCue, totalLines: number): number {
  const [start, end] = cue.lineRange;
  const span = Math.max(1, end - start + 1);
  const firstVisible =
    span >= VISIBLE_LINES
      ? start - 1 - 2
      : start - 1 - Math.floor((VISIBLE_LINES - span) / 2);
  const maxScroll = Math.max(0, totalLines - VISIBLE_LINES);
  return Math.min(Math.max(firstVisible, 0), maxScroll) * LINE_HEIGHT;
}

/** Builds strictly-increasing interpolate() inputs; equal or
 *  out-of-order frames (cues packed tighter than the ramp) would make
 *  interpolate throw. */
function monotonic(frames: number[]): number[] {
  const out: number[] = [];
  frames.forEach((f, i) => {
    out.push(i === 0 ? f : Math.max(f, out[i - 1] + 1));
  });
  return out;
}

function estimateSegmentHeight(text: string): number {
  const charsPerLine = Math.max(
    1,
    Math.floor((NARRATION_WIDTH - NARRATION_PAD * 2 - NARRATION_BADGE_COLUMN) / NARRATION_CHAR_WIDTH),
  );
  const lines = Math.max(1, Math.ceil(text.length / charsPerLine));
  return lines * NARRATION_LINE_HEIGHT + NARRATION_ITEM_GAP;
}

export const ChunkView: React.FC<{
  chunkDir: string;
  visualTheme?: VisualTheme | null;
  filePath?: string | null;
  phaseStyle?: PhaseStyleMode;
  stackId?: string | null;
}> = ({ chunkDir, visualTheme, filePath, phaseStyle = "classic", stackId }) => {
  const frame = useCurrentFrame();
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [sourceLines, setSourceLines] = useState<string[] | null>(null);
  const { delayRender, continueRender, cancelRender } = useDelayRender();
  const [handle] = useState(() => delayRender(`ChunkView(${chunkDir})`));

  const load = useCallback(async () => {
    try {
      const [bundleRes, sourceRes] = await Promise.all([
        fetch(staticFile(`${chunkDir}/bundle.json`)),
        fetch(staticFile(`${chunkDir}/source.tsx`)),
      ]);
      setBundle(await bundleRes.json());
      setSourceLines((await sourceRes.text()).split("\n"));
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [chunkDir, continueRender, cancelRender, handle]);

  useEffect(() => {
    load();
  }, [load]);

  if (!bundle || !sourceLines) {
    return null;
  }

  const cues = [...bundle.highlightConfig].sort(
    (a, b) => cueWindow(a)[0] - cueWindow(b)[0],
  );

  const activeCue =
    cues.find((c) => {
      const [from, to] = cueWindow(c);
      return frame >= from && frame < to;
    }) ?? null;

  // Scroll the code panel so the narrated line is actually on screen.
  let scrollTop = 0;
  if (cues.length === 1) {
    scrollTop = scrollForCue(cues[0], sourceLines.length);
  } else if (cues.length > 1) {
    const rawFrames: number[] = [];
    const values: number[] = [];
    cues.forEach((cue, i) => {
      const target = scrollForCue(cue, sourceLines.length);
      const [from] = cueWindow(cue);
      rawFrames.push(from, from + SCROLL_RAMP);
      if (i === 0) {
        values.push(target, target);
      } else {
        values.push(values[values.length - 1], target);
      }
    });
    scrollTop = interpolate(frame, monotonic(rawFrames), values, {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  let highlightFade = 0;
  let highlightRange: [number, number] | null = null;
  if (activeCue) {
    const [from, to] = cueWindow(activeCue);
    // Fade in only. Cue windows are butted up against each other, so
    // fading back out at the end of one would dip the selection to
    // nothing for a few frames at every single transition — the code
    // would look unhighlighted exactly when the narration moves from
    // one item to the next. Holding full strength until the window
    // ends makes the selection appear to jump to the next block, which
    // is what a selection moving actually looks like.
    const fadeIn = Math.max(1, Math.min(6, Math.floor((to - from) / 2)));
    highlightFade = interpolate(frame, monotonic([from, from + fadeIn]), [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    highlightRange = activeCue.lineRange;
  }

  const segments = bundle.narrationSegments ?? [];
  const activeSegmentIndex = segments.findIndex(
    (s) => frame >= s.fromFrame && frame < s.toFrame,
  );

  // Keep the active narration item in view once the list runs past the
  // bottom of the panel. The active item renders its fuller spoken
  // text, so it is measured with that rather than its summary.
  const bodyTextFor = (segment: NarrationSegment, active: boolean): string => {
    const { detail } = splitSummary(segment.text);
    return active ? segment.spoken || detail : detail;
  };

  let narrationScroll = 0;
  if (segments.length > 0 && activeSegmentIndex >= 0) {
    const heights = segments.map((s, i) =>
      estimateSegmentHeight(bodyTextFor(s, i === activeSegmentIndex))
      + (splitSummary(s.text).title ? NARRATION_LINE_HEIGHT : 0),
    );
    const totalHeight = heights.reduce((a, b) => a + b, 0);
    const offsetOfActive = heights
      .slice(0, activeSegmentIndex)
      .reduce((a, b) => a + b, 0);
    const maxScroll = Math.max(0, totalHeight - NARRATION_VIEWPORT_HEIGHT);
    // Park the active item a third of the way down the panel.
    const desired = offsetOfActive - NARRATION_VIEWPORT_HEIGHT / 3;
    narrationScroll = Math.min(Math.max(desired, 0), maxScroll);
  }

  const pathForHeader = filePath || bundle.filePath || bundle.chunkId;
  const theme = visualTheme ?? bundle.visualTheme ?? themeForStack(bundle.stack);

  const treeSitterTeach = bundle.highlightConfig.some((c) => {
    const note = (c.note || "").toLowerCase();
    return note.includes("tree-sitter") || note.includes("tree_sitter");
  });
  const stackKey = resolveMatrixStackKey(stackId ?? bundle.stack ?? theme.stack, {
    treeSitterTeach,
  });
  const honesty: HonestyHints = {
    hasAssumed:
      segments.some((s) => s.assumed) || bundle.highlightConfig.some((c) => c.assumed),
    treeSitter: treeSitterTeach,
    showSkip: segments.some((s) => (s.note || "").toUpperCase().includes("SKIP")),
  };
  const patterns = resolveFancyPatterns(phaseStyle, "chunkView", stackKey, honesty);
  const tickerLabel = patterns.l1 ? honestyTickerLabel(honesty) : null;
  const fancyL3 = patterns.l3;
  const codePanelWidth = fancyL3 ? "100%" : `${WIDTH - NARRATION_WIDTH}px`;

  const bulletItems =
    fancyL3 && segments.length > 0
      ? segments.map((segment, i) => {
          const text = bodyTextFor(segment, i === activeSegmentIndex);
          return text.length > 140 ? `${text.slice(0, 137)}…` : text;
        })
      : [];
  const bulletReveal =
    fancyL3 && segments.length > 0
      ? segments.map((s) => Math.max(0, s.fromFrame))
      : [];

  const codePanel = (
        <Box
          sx={{
            width: codePanelWidth,
            height: "100%",
            overflow: "hidden",
            position: "relative",
            py: `${CODE_PAD_Y}px`,
            boxSizing: "border-box",
          }}
        >
          <Box
            sx={{
              transform: `translateY(${-scrollTop}px)`,
              fontFamily: "Menlo, monospace",
              fontSize: `${CODE_FONT_SIZE}px`,
              lineHeight: `${LINE_HEIGHT}px`,
              whiteSpace: "pre",
            }}
          >
            {sourceLines.map((line, idx) => {
              const lineNumber = idx + 1;
              const isHighlighted =
                highlightRange !== null &&
                lineNumber >= highlightRange[0] &&
                lineNumber <= highlightRange[1];
              const opacity = isHighlighted ? highlightFade : 0;

              // The selected block is drawn like a text selection: a
              // solid fill, a bar down the left, and a rule closing it
              // off at the top and bottom so it reads as one region
              // rather than a few tinted rows. All of it is painted
              // with inset shadows rather than borders — a real border
              // would add height and break the line-height arithmetic
              // the scroll position depends on.
              const shadows: string[] = [];
              if (isHighlighted) {
                shadows.push(`inset ${SELECTION_BAR_WIDTH}px 0 0 0 rgba(147, 197, 253, ${opacity})`);
                if (lineNumber === highlightRange![0]) {
                  shadows.push(`inset 0 2px 0 0 rgba(147, 197, 253, ${0.8 * opacity})`);
                }
                if (lineNumber === highlightRange![1]) {
                  shadows.push(`inset 0 -2px 0 0 rgba(147, 197, 253, ${0.8 * opacity})`);
                }
              }

              return (
                <Box
                  key={lineNumber}
                  sx={{
                    display: "flex",
                    height: `${LINE_HEIGHT}px`,
                    bgcolor: isHighlighted
                      ? `rgba(37, 99, 195, ${0.55 * opacity})`
                      : "transparent",
                    boxShadow: shadows.join(", "),
                    // Everything outside the selection recedes while a
                    // selection is up, so the block being talked about
                    // is unmistakable without becoming unreadable.
                    opacity: isHighlighted ? 1 : 1 - UNSELECTED_DIM * highlightFade,
                  }}
                >
                  <Box
                    sx={{
                      width: `${GUTTER_WIDTH}px`,
                      flexShrink: 0,
                      textAlign: "right",
                      pr: 1.5,
                      boxSizing: "border-box",
                      color: isHighlighted
                        ? `rgba(219, 234, 254, ${0.5 + 0.5 * opacity})`
                        : "#4b5057",
                      fontWeight: isHighlighted && opacity > 0.5 ? 700 : 400,
                    }}
                  >
                    {lineNumber}
                  </Box>
                  <Box
                    sx={{
                      pl: `${CODE_PAD_X - 12}px`,
                      color: isHighlighted ? "#ffffff" : "#c8ccd2",
                      fontWeight: isHighlighted && opacity > 0.5 ? 600 : 400,
                    }}
                  >
                    {line}
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>
  );

  const narrationPanel = (
        <Box
          sx={{
            width: `${NARRATION_WIDTH}px`,
            height: "100%",
            bgcolor: "#1b1e25",
            borderLeft: "1px solid rgba(255,255,255,0.08)",
            overflow: "hidden",
            p: `${NARRATION_PAD}px`,
            boxSizing: "border-box",
          }}
        >
          {segments.length === 0 ? (
            <Typography
              component="div"
              sx={{
                fontFamily: "Helvetica, Arial, sans-serif",
                fontSize: `${NARRATION_FONT_SIZE}px`,
                lineHeight: `${NARRATION_LINE_HEIGHT}px`,
                color: "#e5e7eb",
              }}
            >
              {bundle.cleanText}
            </Typography>
          ) : (
            <Box sx={{ transform: `translateY(${-narrationScroll}px)` }}>
              {segments.map((segment, i) => {
                const isActive = i === activeSegmentIndex;
                const { title } = splitSummary(segment.text);
                return (
                  <Box
                    key={segment.label}
                    sx={{
                      display: "flex",
                      mb: `${NARRATION_ITEM_GAP}px`,
                      alignItems: "flex-start",
                    }}
                  >
                    <Box
                      sx={{
                        width: 21,
                        height: 21,
                        mr: `${NARRATION_BADGE_COLUMN - 21}px`,
                        flexShrink: 0,
                        borderRadius: "4px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontFamily: "Helvetica, Arial, sans-serif",
                        fontSize: 12,
                        fontWeight: 700,
                        bgcolor: isActive ? ACCENT : "transparent",
                        color: isActive ? "#0b1020" : DIM_TEXT,
                        border: isActive
                          ? "1px solid transparent"
                          : "1px solid rgba(139,144,153,0.4)",
                      }}
                    >
                      {segment.label}
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      {title ? (
                        <Typography
                          component="div"
                          sx={{
                            fontFamily: "Menlo, monospace",
                            fontSize: `${NARRATION_FONT_SIZE}px`,
                            lineHeight: `${NARRATION_LINE_HEIGHT}px`,
                            fontWeight: 700,
                            color: isActive ? ACCENT : DIM_TEXT,
                          }}
                        >
                          {title}
                        </Typography>
                      ) : null}
                      <Typography
                        component="div"
                        sx={{
                          fontFamily: "Helvetica, Arial, sans-serif",
                          fontSize: `${NARRATION_FONT_SIZE}px`,
                          lineHeight: `${NARRATION_LINE_HEIGHT}px`,
                          color: isActive ? "#ffffff" : DIM_TEXT,
                          fontWeight: isActive ? 500 : 400,
                        }}
                      >
                        {bodyTextFor(segment, isActive)}
                      </Typography>
                    </Box>
                  </Box>
                );
              })}
            </Box>
          )}
        </Box>
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#15171c" }}>
      <Audio src={staticFile(`${chunkDir}/narration.wav`)} />

      <DiagramHeader
        theme={theme}
        filePath={pathForHeader}
        eyebrow={bundle.featureName || "Code walkthrough"}
        titleFallback={bundle.chunkId}
      />

      {fancyL3 ? (
        <Split7030
          main={codePanel}
          aside={
            segments.length > 0 ? (
              <AnimatedBulletList
                items={bulletItems}
                revealAtFrames={bulletReveal}
                activeIndex={activeSegmentIndex >= 0 ? activeSegmentIndex : null}
                accentColor={ACCENT}
              />
            ) : (
              <Typography sx={{ color: DIM_TEXT, fontSize: 14 }}>{bundle.cleanText}</Typography>
            )
          }
        />
      ) : (
        <Box sx={{ display: "flex", height: `${HEIGHT - HEADER_HEIGHT}px`, mt: `${HEADER_HEIGHT}px` }}>
          {codePanel}
          {narrationPanel}
        </Box>
      )}

      {tickerLabel ? (
        <TickerBar label={tickerLabel} showFromFrame={10} hideAtFrame={null} />
      ) : null}
    </AbsoluteFill>
  );
};
