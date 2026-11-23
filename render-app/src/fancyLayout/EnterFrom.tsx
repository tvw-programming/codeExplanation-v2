import { useCurrentFrame } from "remotion";
import { enterOffsets, type EnterDirection } from "./layoutMath";

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
  durationInFrames = 18,
  distancePx = 56,
  startFrame = 0,
  reducedMotion = false,
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

  return (
    <div
      className={className}
      style={{
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