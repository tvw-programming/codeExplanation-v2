import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { CEV_FG_MUTED, CEV_FG_PRIMARY } from "../../visualTheme";
import { AnimatedBulletList } from "../AnimatedBulletList";
import { BROADCAST } from "./broadcastTheme";
import type { DiagramDescription, DiagramFactTone } from "./diagramDescription";
import { LowerThirdNameplate } from "./LowerThirdNameplate";
import type { BroadcastLayoutMode } from "./layoutMode";

const TONE_COLOR: Record<DiagramFactTone, string> = {
  default: CEV_FG_PRIMARY,
  assumed: BROADCAST.assumedAmber,
  accent: "#60a5fa",
};

export type DiagramDescriptionPanelProps = {
  description: DiagramDescription;
  mode: BroadcastLayoutMode;
  /** Short path for nameplate secondary line. */
  pathShort?: string | null;
  accentColor?: string;
  /** Optional teaching bullets (breakdown rail) — still grounded in graph. */
  teachingBullets?: string[];
  activeBulletIndex?: number | null;
  startFrame?: number;
  reducedMotion?: boolean;
};

function FactChips({
  facts,
  accentColor,
}: {
  facts: DiagramDescription["facts"];
  accentColor: string;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        flexWrap: "wrap",
        gap: 0.75,
        mt: 0.75,
      }}
    >
      {facts.map((f, i) => (
        <Box
          key={`${f.label}-${i}`}
          sx={{
            px: 1,
            py: 0.35,
            borderRadius: "4px",
            border: `1px solid ${
              f.tone === "assumed"
                ? `${BROADCAST.assumedAmber}66`
                : `${accentColor}33`
            }`,
            bgcolor: "rgba(0,0,0,0.35)",
          }}
        >
          <Typography
            sx={{
              color: TONE_COLOR[f.tone || "default"],
              fontSize: 11,
              fontWeight: 600,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              lineHeight: 1.2,
            }}
          >
            {f.label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

/**
 * Smart description chrome — bottom band (100% diagram) or 40% side rail.
 */
export const DiagramDescriptionPanel: React.FC<DiagramDescriptionPanelProps> = ({
  description,
  mode,
  pathShort,
  accentColor = "#60a5fa",
  teachingBullets,
  activeBulletIndex = null,
  startFrame = 4,
  reducedMotion = false,
}) => {
  const secondary =
    pathShort ||
    description.kicker ||
    description.honestyKeyword ||
    null;
  const variant =
    description.honestyKeyword && mode === "band" ? "B" : ("A" as const);

  if (mode === "rail") {
    const bullets =
      teachingBullets && teachingBullets.length > 0
        ? teachingBullets
        : [
            description.headline,
            ...description.facts.map((f) => f.label),
            ...(description.legend ? [description.legend] : []),
          ].filter(Boolean);

    return (
      <Box
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          boxSizing: "border-box",
        }}
      >
        <LowerThirdNameplate
          primary={description.segmentTag}
          secondary={secondary}
          variant={variant}
          accentColor={accentColor}
          startFrame={startFrame}
          reducedMotion={reducedMotion}
        />
        <Typography
          sx={{
            color: CEV_FG_PRIMARY,
            fontSize: 14,
            fontWeight: 600,
            mt: 1.5,
            mb: 1,
            lineHeight: 1.35,
          }}
        >
          {description.headline}
        </Typography>
        {description.legend ? (
          <Typography
            sx={{
              color: CEV_FG_MUTED,
              fontSize: 11,
              mb: 1,
              letterSpacing: 0.6,
              textTransform: "uppercase",
            }}
          >
            {description.legend}
          </Typography>
        ) : null}
        <Box sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
          <AnimatedBulletList
            items={bullets.slice(0, 10)}
            activeIndex={activeBulletIndex}
            accentColor={accentColor}
            reducedMotion={reducedMotion}
            startFrame={startFrame + 4}
            staggerFrames={7}
          />
        </Box>
      </Box>
    );
  }

  // band — bottom news strip under full-width diagram
  return (
    <Box
      sx={{
        position: "absolute",
        left: 16,
        right: 16,
        bottom: 10,
        zIndex: 4,
        pointerEvents: "none",
        display: "flex",
        flexDirection: "column",
        gap: 0.5,
        maxWidth: 1248,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-end",
          gap: 2,
          minWidth: 0,
        }}
      >
        <LowerThirdNameplate
          primary={description.segmentTag}
          secondary={secondary}
          variant={variant}
          accentColor={accentColor}
          startFrame={startFrame}
          reducedMotion={reducedMotion}
        />
        <Box sx={{ flex: 1, minWidth: 0, pb: 0.5 }}>
          <Typography
            sx={{
              color: CEV_FG_PRIMARY,
              fontSize: 15,
              fontWeight: 600,
              lineHeight: 1.3,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {description.headline}
          </Typography>
          {description.legend ? (
            <Typography
              sx={{
                color: CEV_FG_MUTED,
                fontSize: 11,
                mt: 0.25,
              }}
            >
              {description.legend}
            </Typography>
          ) : null}
        </Box>
      </Box>
      <FactChips facts={description.facts.slice(0, 5)} accentColor={accentColor} />
    </Box>
  );
};
