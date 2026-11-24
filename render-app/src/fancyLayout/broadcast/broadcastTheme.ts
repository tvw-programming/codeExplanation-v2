/**
 * CEV News Desk tokens — fixed broadcast chrome (not per-clip ad-hoc CSS).
 * Honesty-only copy slots; no stock-news fiction.
 */

export const BROADCAST = {
  urgentRed: "#E11D2E",
  liveRed: "#FF2D2D",
  tickerBg: "rgba(8, 12, 18, 0.96)",
  lowerThirdBg: "rgba(10, 14, 20, 0.94)",
  lowerThirdBorder: "rgba(255, 255, 255, 0.12)",
  panelBg: "rgba(12, 17, 24, 0.96)",
  factMuted: "#9CA3AF",
  factPrimary: "#F3F4F6",
  assumedAmber: "#F59E0B",
  crawlSpeedPxPerFrame: 1.15,
  lowerThirdInFrames: 14,
  breakingFlashMax: 18,
  railMainFraction: 0.6,
  /** Footprint below this share of usable width → 60/40 rail; else full + bottom band. */
  railFootprintMaxRatio: 0.6,
} as const;

export type BroadcastColorToken = keyof typeof BROADCAST;