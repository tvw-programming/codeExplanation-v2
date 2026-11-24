/**
 * Safe-zone constants for fancy layout primitives (L1–L4).
 * Keep in sync with treeLayout.ts header/caption reserves.
 */
import { CAPTION_ZONE, HEADER_HEIGHT, LEFT_PAD, RIGHT_SAFE } from "../treeLayout";

export { CAPTION_ZONE, HEADER_HEIGHT, LEFT_PAD, RIGHT_SAFE };

/** Standard 1280×720 composition width (FullVideo). */
export const COMPOSITION_WIDTH = 1280;

/** Thin honesty callout strip (L1); sits in the caption reserve, not over header. */
export const TICKER_BAR_HEIGHT = 28;

/** Bottom inset for L1 bar inside the caption band. */
export const TICKER_BOTTOM_INSET = 10;

/** Extra bottom reserve when a clip stacks L1 on top of captions. */
export const TICKER_EXTRA_RESERVE = TICKER_BAR_HEIGHT + TICKER_BOTTOM_INSET;

/** Usable vertical band between header and caption (no L1). */
export function contentBandHeight(frameHeight: number): number {
  return frameHeight - HEADER_HEIGHT - CAPTION_ZONE;
}

/** Usable vertical band when L1 ticker may show. */
export function contentBandHeightWithTicker(frameHeight: number): number {
  return frameHeight - HEADER_HEIGHT - CAPTION_ZONE - TICKER_EXTRA_RESERVE;
}