import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { DiagramHeader, shortFilePath } from "./DiagramHeader";
import { HEADER_HEIGHT } from "./treeLayout";
import type { PhaseStyleMode } from "./phaseStyle";
import { EnterFrom } from "./fancyLayout";
import { resolveFancyPatterns } from "./fancyLayout/phaseLayoutMatrix";
import { resolveMatrixStackKey } from "./fancyLayout/stackResolve";
import {
  type VisualTheme,
  resolveVisualTheme,
} from "./visualTheme";

// The card that introduces each file before its walkthrough starts:
// what the file is, where it sits, what it's built on, what calls it
// and what it calls.
//
// Fields the repository genuinely cannot answer are not shown as empty
// rows — the overview carries a reason for each one (see
// src/narrate/file_overview.py) and the card prints that instead, so a
// gap reads as a known gap rather than as missing data.
//
// The card is on screen for exactly as long as its narration takes to
// read (floored at MIN_FILE_CARD_SECONDS), so the viewer is never read
// a summary that has already left the screen.

export type FileOverview = {
  fileName: string;
  filePath: string;
  purpose: string | null;
  fileType: string;
  layer: string;
  feature: string | null;
  callers: string[];
  callees: string[];
  language: string | null;
  frameworks: string[];
  libraries: string[];
  exports: string[];
  contains: string[];
  routes: string[];
  outboundCalls: string[];
  sideEffects: string[];
  lineCount: number;
  lastModified: string | null;
  tests: string[];
  risks: string[];
  unavailable: Record<string, string>;
};

export type CardNarration = {
  audio: string;
  durationMs: number;
  spoken: string;
  engine: string;
};

const ACCENT = "#60a5fa";
const DIM_TEXT = "#8b9099";
const PANEL_BG = "#1b1e25";
const BORDER = "1px solid rgba(255,255,255,0.07)";

// Card timing lives in segmentTiming.ts (shared with the viewer's
// segment index) and is re-exported here for existing importers.
export { MIN_FILE_CARD_SECONDS, FILE_CARD_TAIL_SECONDS } from "./segmentTiming";

const LAYER_COLORS: Record<string, string> = {
  Frontend: "#60a5fa",
  Backend: "#4ade80",
  Testing: "#fbbf24",
  Agentic: "#c084fc",
  Configuration: "#94a3b8",
};

const shortPath = (path: string): string => shortFilePath(path) || path;

const Badge: React.FC<{ text: string; color: string; textColor?: string }> = ({
  text,
  color,
  textColor = "#0b1020",
}) => (
  <Box
    sx={{
      flexShrink: 0,
      bgcolor: color,
      color: textColor,
      fontFamily: "Helvetica, Arial, sans-serif",
      fontSize: 15,
      fontWeight: 700,
      borderRadius: "6px",
      px: "12px",
      py: "5px",
      whiteSpace: "nowrap",
    }}
  >
    {text}
  </Box>
);

const Card: React.FC<{
  label: string;
  children: React.ReactNode;
  grow?: number;
}> = ({ label, children, grow = 1 }) => (
  <Box
    sx={{
      flex: `${grow} 1 0`,
      minWidth: 0,
      bgcolor: PANEL_BG,
      border: BORDER,
      borderRadius: "10px",
      p: "13px 16px",
      // Height follows the content: a fixed stretch is what left the
      // Exports box mostly empty.
      alignSelf: "flex-start",
    }}
  >
    <Typography
      sx={{
        fontFamily: "Helvetica, Arial, sans-serif",
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: ACCENT,
        fontWeight: 700,
        mb: "7px",
      }}
    >
      {label}
    </Typography>
    {children}
  </Box>
);

const Body: React.FC<{
  children: React.ReactNode;
  dim?: boolean;
  size?: number;
}> = ({ children, dim = false, size = 15 }) => (
  <Typography
    component="div"
    sx={{
      fontFamily: "Helvetica, Arial, sans-serif",
      fontSize: `${size}px`,
      lineHeight: `${Math.round(size * 1.45)}px`,
      color: dim ? DIM_TEXT : "#e8eaed",
    }}
  >
    {children}
  </Typography>
);

const Chips: React.FC<{ items: string[]; max?: number }> = ({ items, max = 6 }) => (
  <Box sx={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
    {items.slice(0, max).map((item) => (
      <Box
        key={item}
        sx={{
          fontFamily: "Menlo, monospace",
          fontSize: 13,
          color: "#dbeafe",
          bgcolor: "rgba(96,165,250,0.14)",
          borderRadius: "5px",
          px: "7px",
          py: "2px",
        }}
      >
        {item}
      </Box>
    ))}
    {items.length > max ? (
      <Box sx={{ fontFamily: "Helvetica, Arial, sans-serif", fontSize: 13, color: DIM_TEXT, alignSelf: "center" }}>
        +{items.length - max} more
      </Box>
    ) : null}
  </Box>
);

/** Long purpose text steps down in size rather than being cut off —
 *  the card has the room, it was the fixed font that did not. */
function purposeFontSize(text: string): number {
  if (text.length > 520) return 15;
  if (text.length > 340) return 17;
  if (text.length > 200) return 19;
  return 21;
}

const KeyValue: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Box sx={{ display: "flex", gap: "8px", alignItems: "baseline", mb: "3px" }}>
    <Typography
      sx={{
        fontFamily: "Helvetica, Arial, sans-serif",
        fontSize: 13,
        color: DIM_TEXT,
        width: 74,
        flexShrink: 0,
      }}
    >
      {label}
    </Typography>
    <Typography
      component="div"
      sx={{
        fontFamily: "Menlo, monospace",
        fontSize: 14,
        color: "#e8eaed",
        minWidth: 0,
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      {value}
    </Typography>
  </Box>
);

export const FileCard: React.FC<{
  overview: FileOverview;
  narration?: CardNarration | null;
  chunkDir?: string;
  position?: { index: number; total: number };
  sectionSeconds?: number;
  visualTheme?: VisualTheme | null;
  /** classic = today's layout; fancy reserved for L1–L4 matrix (later PRs). */
  phaseStyle?: PhaseStyleMode;
  stackId?: string | null;
}> = ({
  overview,
  narration,
  chunkDir,
  position,
  sectionSeconds,
  visualTheme,
  phaseStyle = "classic",
  stackId,
}) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const rise = interpolate(frame, [0, 12], [12, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const purpose = overview.purpose;
  const layerColor = LAYER_COLORS[overview.layer] ?? ACCENT;
  const theme = resolveVisualTheme(visualTheme, overview.frameworks, overview.language);

  const subtitleBits: string[] = [];
  if (position) subtitleBits.push(`File ${position.index} of ${position.total}`);
  if (overview.feature) subtitleBits.push(`feature: ${overview.feature}`);
  if (sectionSeconds && sectionSeconds > 0) {
    const minutes = Math.floor(sectionSeconds / 60);
    const seconds = Math.round(sectionSeconds % 60);
    subtitleBits.push(`section runs ${minutes}m ${String(seconds).padStart(2, "0")}s`);
  }

  const interfaceItems = overview.routes.length > 0 ? overview.routes : overview.outboundCalls;
  const interfaceLabel = overview.routes.length > 0 ? "Routes served" : "Outbound calls";

  const stackKey = resolveMatrixStackKey(stackId ?? theme.stack);
  const patterns = resolveFancyPatterns(phaseStyle, "fileCard", stackKey);
  const useFancyEnter = patterns.l2;
  const motionY = useFancyEnter ? 0 : rise;

  const cardBody = (
      <Box sx={{ transform: `translateY(${motionY}px)`, height: "100%", display: "flex", flexDirection: "column" }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
          <Typography
            sx={{
              fontFamily: "Menlo, monospace",
              fontSize: 42,
              fontWeight: 700,
              color: "#ffffff",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {overview.fileName}
          </Typography>
          <Box sx={{ display: "flex", gap: "8px", flexShrink: 0 }}>
            <Badge text={overview.layer} color={layerColor} />
            <Badge
              text={overview.fileType}
              color="rgba(255,255,255,0.14)"
              textColor="#e8eaed"
            />
          </Box>
        </Box>

        {subtitleBits.length > 0 ? (
          <Typography
            sx={{
              fontFamily: "Helvetica, Arial, sans-serif",
              fontSize: 14,
              color: "#6b7280",
              mt: "3px",
            }}
          >
            {subtitleBits.join("  ·  ")}
          </Typography>
        ) : null}

        <Box sx={{ display: "flex", flexDirection: "column", gap: "11px", mt: "16px", flex: 1, minHeight: 0 }}>
          <Card label="Purpose">
            {purpose ? (
              <Body size={purposeFontSize(purpose)}>{purpose}</Body>
            ) : (
              <Body dim>Not stated: {overview.unavailable.purpose}.</Body>
            )}
          </Card>

          <Box sx={{ display: "flex", gap: "11px", alignItems: "flex-start" }}>
            <Card label="Stack" grow={1}>
              <KeyValue label="Language" value={overview.language ?? "unknown"} />
              <KeyValue
                label="Framework"
                value={overview.frameworks.length > 0 ? overview.frameworks.join(", ") : "none"}
              />
              <KeyValue
                label="Libraries"
                value={overview.libraries.length > 0 ? overview.libraries.join(", ") : "none"}
              />
              <KeyValue label="Size" value={`${overview.lineCount} lines`} />
            </Card>

            <Card label="Relationships" grow={1}>
              <Box sx={{ mb: "7px" }}>
                <Body dim size={13}>Called by</Body>
                {overview.callers.length > 0 ? (
                  <Chips items={overview.callers.map(shortPath)} max={3} />
                ) : (
                  <Body dim size={14}>No importers in this repository.</Body>
                )}
              </Box>
              <Box>
                <Body dim size={13}>Calls</Body>
                {overview.callees.length > 0 ? (
                  <Chips items={overview.callees.map(shortPath)} max={3} />
                ) : (
                  <Body dim size={14}>No internal imports.</Body>
                )}
              </Box>
            </Card>

            <Card label="Contains" grow={1}>
              {overview.contains.length > 0 ? (
                <Body size={14}>{overview.contains.join(" · ")}</Body>
              ) : (
                <Body dim size={14}>Nothing named at the top level.</Body>
              )}
              {overview.exports.length > 0 ? (
                <Box sx={{ mt: "7px" }}>
                  <Body dim size={13}>Exports</Body>
                  <Chips items={overview.exports} max={5} />
                </Box>
              ) : null}
              {overview.sideEffects.length > 0 ? (
                <Box sx={{ mt: "7px" }}>
                  <Body dim size={13}>Side effects</Body>
                  <Body size={14}>{overview.sideEffects.join(", ")}</Body>
                </Box>
              ) : null}
            </Card>
          </Box>

          {interfaceItems.length > 0 ? (
            <Card label={interfaceLabel}>
              <Chips items={interfaceItems} max={8} />
            </Card>
          ) : null}

          {overview.risks.length > 0 ? (
            <Card label="Worth knowing">
              <Body dim size={14}>{overview.risks.join("; ")}.</Body>
            </Card>
          ) : null}
        </Box>
      </Box>
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#15171c", opacity: fade }}>
      <DiagramHeader
        theme={theme}
        filePath={overview.filePath}
        eyebrow="File overview"
        titleFallback={overview.fileName}
      />
      {narration && chunkDir ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}

      <Box
        sx={{
          position: "absolute",
          top: HEADER_HEIGHT,
          left: 0,
          right: 0,
          bottom: 0,
          px: "46px",
          pt: "24px",
          pb: "28px",
          boxSizing: "border-box",
        }}
      >
        {useFancyEnter ? (
          <EnterFrom direction={patterns.l2Direction} durationInFrames={20}>
            {cardBody}
          </EnterFrom>
        ) : (
          cardBody
        )}
      </Box>
    </AbsoluteFill>
  );
};
