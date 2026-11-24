import { useCurrentFrame } from "remotion";
import { enterOffsets, type EnterDirection } from "./layoutMath";
import { HEADER_HEIGHT } from "./zones";

export type EnterFromProps = {
  direction: EnterDirection;
  children: React.ReactNode;
  /** Travel + opacity ramp length in frames. */
  durationInFrames?: number;
  /** Pixel travel at t=0. */
  distancePx?: number;
  /** Delay entrance relative to parent Sequence start. */
  startFrame?: number;
  reducedMotion?: boolean;
  /**
   * Position this wrapper below DiagramHeader so absolutely positioned
   * children (e.g. VisualGraphDiagram's inset-0 SVG) size correctly.
   * Without this, transform on the wrapper collapses the containing block.
   */
  fillBelowHeader?: boolean;
  style?: React.CSSProperties;
  className?: string;
};

/**
 * L2 — one directional entrance per wrapped block (left / top / right).
 * Wrap clip sections when phaseStyle=fancy and matrix marks L2D.
 */
export const EnterFrom: React.FC<EnterFromProps> = ({
  direction,
  children,
  durationInFrames = 22,
  distancePx = 80,
  startFrame = 0,
  reducedMotion = false,
  fillBelowHeader = false,
  style,
  className,
}) => {
  const frame = useCurrentFrame();
  const { x, y, opacity } = enterOffsets(
    frame,
    direction,
    durationInFrames,
    distancePx,
    startFrame,
    reducedMotion,
  );

  const frameStyle: React.CSSProperties = fillBelowHeader
    ? {
        position: "absolute",
        top: HEADER_HEIGHT,
        left: 0,
        right: 0,
        bottom: 0,
      }
    : {};

  return (
    <div
      className={className}
      style={{
        ...frameStyle,
        transform: `translate(${x}px, ${y}px)`,
        opacity,
        willChange: reducedMotion ? undefined : "transform, opacity",
        ...style,
      }}
    >
      {children}
    </div>
  );
};