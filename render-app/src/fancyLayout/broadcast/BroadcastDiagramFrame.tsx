import Box from "@mui/material/Box";
import {
  CAPTION_ZONE,
  HEADER_HEIGHT,
  LOWER_THIRD_ZONE,
  TICKER_BAR_HEIGHT,
} from "../zones";
import { Split7030 } from "../Split7030";
import { BROADCAST } from "./broadcastTheme";
import {
  DiagramDescriptionPanel,
  type DiagramDescriptionPanelProps,
} from "./DiagramDescriptionPanel";
import { HonestyCrawlTicker } from "./HonestyCrawlTicker";
import type { BroadcastLayoutMode } from "./layoutMode";
import type { DiagramDescription } from "./diagramDescription";

export type BroadcastDiagramFrameProps = {
  mode: BroadcastLayoutMode;
  description: DiagramDescription;
  diagram: React.ReactNode;
  pathShort?: string | null;
  accentColor?: string;
  crawlText?: string | null;
  teachingBullets?: string[];
  activeBulletIndex?: number | null;
  showCrawl?: boolean;
  reducedMotion?: boolean;
  /** Extra bottom reserve when crawl stacks under band facts. */
  stackCrawl?: boolean;
};

/**
 * Fixed broadcast templates:
 * - band: diagram fills content band; description in bottom nameplate strip
 * - rail: ≈60% diagram / ≈40% description side panel
 */
export const BroadcastDiagramFrame: React.FC<BroadcastDiagramFrameProps> = ({
  mode,
  description,
  diagram,
  pathShort,
  accentColor = "#60a5fa",
  crawlText,
  teachingBullets,
  activeBulletIndex = null,
  showCrawl = false,
  reducedMotion = false,
  stackCrawl = true,
}) => {
  const panelProps: DiagramDescriptionPanelProps = {
    description,
    mode,
    pathShort,
    accentColor,
    teachingBullets,
    activeBulletIndex,
    reducedMotion,
  };

  const crawlBottom = mode === "band" && stackCrawl ? LOWER_THIRD_ZONE + 4 : 8;
  const bandBottomClear =
    LOWER_THIRD_ZONE + (showCrawl && crawlText ? TICKER_BAR_HEIGHT + 6 : 0);

  if (mode === "rail") {
    return (
      <>
        <Split7030
          mainFraction={BROADCAST.railMainFraction}
          asideChrome
          asideTitle={description.segmentTag}
          accentColor={accentColor}
          headerClearance={HEADER_HEIGHT}
          captionClearance={showCrawl && crawlText ? TICKER_BAR_HEIGHT + 12 : 16}
          main={
            <Box sx={{ position: "relative", width: "100%", height: "100%" }}>
              {diagram}
            </Box>
          }
          aside={<DiagramDescriptionPanel {...panelProps} />}
        />
        {showCrawl && crawlText ? (
          <HonestyCrawlTicker
            text={crawlText}
            reducedMotion={reducedMotion}
            accentColor={accentColor}
            bottom={8}
          />
        ) : null}
      </>
    );
  }

  return (
    <>
      <Box
        sx={{
          position: "absolute",
          top: HEADER_HEIGHT,
          left: 0,
          right: 0,
          bottom: bandBottomClear,
          overflow: "hidden",
        }}
      >
        {diagram}
      </Box>
      <DiagramDescriptionPanel {...panelProps} />
      {showCrawl && crawlText ? (
        <HonestyCrawlTicker
          text={crawlText}
          reducedMotion={reducedMotion}
          accentColor={accentColor}
          bottom={crawlBottom}
        />
      ) : null}
    </>
  );
};
