/**
 * Cursor canvas template — React interactive breakdown (Q3 B primary).
 *
 * Usage: paste the contents of visuals/react/<chunkId>/interactive.json
 * into EMBEDDED_PAYLOAD below (or replace the placeholder). No fetch.
 * Click a node to show developer detail (props, children, file:line).
 *
 * This file is a repo template; open it as a Cursor .canvas.tsx (or copy
 * into the canvas editor) when exploring a chunk graph in chat.
 */
import { useMemo, useState, type CSSProperties } from "react";

type VisualNode = {
  id: string;
  kind: string;
  label: string;
  filePath?: string;
  line?: number | null;
  assumed?: boolean;
  meta?: { props?: Array<{ name: string; valuePreview?: string | null }> };
};

type VisualEdge = {
  id: string;
  kind: string;
  from: string;
  to: string;
  assumed?: boolean;
};

type Payload = {
  chunkId: string;
  filePath: string;
  stack: string;
  visualGraph: { rootId: string; nodes: VisualNode[]; edges: VisualEdge[] };
  lifecycleFlows?: unknown[];
  securityFlags?: Array<{ id: string; message: string; nodeIds?: string[] }>;
  visualTheme?: { primary: string; onDark?: string };
  visualAvailability?: { interactiveBreakdown?: string; reasons?: Record<string, string> };
};

// Replace with interactive.json contents (self-contained — no URLs).
const EMBEDDED_PAYLOAD: Payload | null = null;

const BG = "#111827";
const FG = "#F3F4F6";
const MUTED = "#9CA3AF";
const SECURITY = "#F59E0B";

export default function ReactBreakdownCanvas() {
  const payload = EMBEDDED_PAYLOAD;
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const unavailable =
    !payload ||
    payload.visualAvailability?.interactiveBreakdown === "unavailable" ||
    !payload.visualGraph?.edges?.length;

  const themePrimary = payload?.visualTheme?.primary || "#61DAFB";
  const nodes = payload?.visualGraph?.nodes || [];
  const mounts = (payload?.visualGraph?.edges || []).filter((e) => e.kind === "mounts");
  const selected = nodes.find((n) => n.id === selectedId) || null;
  const childIds = useMemo(
    () => mounts.filter((e) => e.from === selectedId).map((e) => e.to),
    [mounts, selectedId],
  );
  const flags = (payload?.securityFlags || []).filter(
    (f) => selectedId && (f.nodeIds || []).includes(selectedId),
  );

  if (unavailable) {
    const reason =
      payload?.visualAvailability?.reasons?.interactiveBreakdown ||
      "interactiveBreakdown unavailable for this chunk";
    return (
      <div style={{ ...rootStyle, padding: 24 }}>
        <p style={{ color: MUTED }}>{reason}</p>
      </div>
    );
  }

  return (
    <div style={rootStyle}>
      <header style={headerStyle}>
        <div>
          <div style={{ color: MUTED, fontSize: 12, letterSpacing: 1 }}>REACT · FILE GRAPH</div>
          <div style={{ color: FG, fontSize: 18, fontWeight: 700 }}>{payload!.filePath}</div>
        </div>
        <img
          src="" // host may inject; Remotion uses public/visuals/logos/react.svg
          alt=""
          width={24}
          height={24}
          style={{ opacity: 0.88, pointerEvents: "none" }}
        />
        <div
          style={{
            position: "absolute",
            top: 16,
            right: 16,
            width: 24,
            height: 24,
            borderRadius: 4,
            background: `${themePrimary}40`,
            pointerEvents: "none",
            border: `1px solid ${themePrimary}`,
          }}
          title="React"
        />
      </header>

      <div style={{ display: "flex", gap: 16, padding: 16, minHeight: 360 }}>
        <div style={{ flex: 1 }}>
          {nodes.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => setSelectedId(n.id)}
              style={{
                ...nodeBtn,
                borderColor: themePrimary,
                background: selectedId === n.id ? `${themePrimary}55` : `${themePrimary}22`,
                opacity: n.assumed ? 0.75 : 1,
              }}
            >
              {n.label}
            </button>
          ))}
          <svg width="100%" height="120" style={{ marginTop: 12 }}>
            {mounts.map((e) => (
              <text key={e.id} x={10} y={20} fill={MUTED} fontSize={11}>
                {e.from} {e.assumed ? "-.->" : "-->"} {e.to}
              </text>
            ))}
          </svg>
        </div>

        <aside style={detailStyle}>
          {!selected ? (
            <p style={{ color: MUTED }}>Select a node</p>
          ) : (
            <>
              <div style={{ color: themePrimary, fontSize: 12 }}>{selected.kind}</div>
              <div style={{ color: FG, fontSize: 18, fontWeight: 700 }}>{selected.label}</div>
              <div style={{ color: MUTED, fontSize: 13, marginTop: 8 }}>
                {selected.filePath}
                {selected.line != null ? `:${selected.line}` : ""}
              </div>
              <div style={{ marginTop: 12, color: FG, fontSize: 13 }}>
                Children: {childIds.length}
              </div>
              <ul style={{ color: MUTED, fontSize: 13 }}>
                {(selected.meta?.props || []).map((p) => (
                  <li key={p.name}>
                    {p.name}
                    {p.valuePreview ? ` = ${p.valuePreview}` : ""}
                  </li>
                ))}
              </ul>
              {flags.map((f) => (
                <div key={f.id} style={{ color: SECURITY, fontSize: 12, marginTop: 8 }}>
                  {f.message}
                </div>
              ))}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

const rootStyle: CSSProperties = {
  background: BG,
  color: FG,
  fontFamily: "ui-sans-serif, system-ui, sans-serif",
  minHeight: 420,
  position: "relative",
};

const headerStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "16px 20px",
  borderBottom: "1px solid #1f2937",
  position: "relative",
};

const nodeBtn: CSSProperties = {
  display: "inline-block",
  margin: 4,
  padding: "8px 12px",
  borderRadius: 8,
  borderWidth: 2,
  borderStyle: "solid",
  color: FG,
  cursor: "pointer",
};

const detailStyle: CSSProperties = {
  width: 280,
  background: "#0b1220",
  borderRadius: 8,
  padding: 16,
  border: "1px solid #1f2937",
};
