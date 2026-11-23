export {
  HONESTY_TICKER_LABELS,
  bulletItemOpacity,
  bulletRevealFrames,
  enterOffsets,
  enterProgress,
  split7030Widths,
  tickerOpacity,
  type EnterDirection,
  type EnterOffsets,
  type HonestyTickerLabel,
  type Split7030Columns,
} from "./layoutMath";

export {
  CAPTION_ZONE,
  COMPOSITION_WIDTH,
  HEADER_HEIGHT,
  LEFT_PAD,
  RIGHT_SAFE,
  TICKER_BAR_HEIGHT,
  TICKER_BOTTOM_INSET,
  TICKER_EXTRA_RESERVE,
  contentBandHeight,
  contentBandHeightWithTicker,
} from "./zones";

export { TickerBar, type TickerBarProps } from "./TickerBar";
export { EnterFrom, type EnterFromProps } from "./EnterFrom";
export { Split7030, type Split7030Props } from "./Split7030";
export {
  AnimatedBulletList,
  type AnimatedBulletListProps,
} from "./AnimatedBulletList";

export {
  honestyTickerLabel,
  matrixPhaseParts,
  matrixRowKeys,
  normalizeMatrixStack,
  resolveFancyPatterns,
  type FancyPatternFlags,
  type HonestyHints,
  type LayoutPatternId,
  type PhasePart,
} from "./phaseLayoutMatrix";

export {
  resolveChunkStackId,
  resolveMatrixStackKey,
} from "./stackResolve";