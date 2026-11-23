import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import SearchIcon from "@mui/icons-material/Search";
import FolderIcon from "@mui/icons-material/Folder";
import DescriptionIcon from "@mui/icons-material/Description";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { marked, type Tokens } from "marked";
import type { DocGroup } from "./types";

const DOCS_BASE = "../docs/";
const FILE_ITEM_PREFIX = "file:";

let mermaidReady: Promise<typeof import("mermaid")> | null = null;

function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "strict",
      });
      return mod;
    });
  }
  return mermaidReady;
}

/**
 * marked@12 still invokes renderer.code(code, infostring, escaped) at
 * runtime even though Tokens.Code types suggest a single token object.
 * Accept both shapes so Mermaid fences never crash the page.
 */
function fenceParts(
  codeOrToken: string | Tokens.Code,
  infostring?: string,
): { text: string; lang: string } {
  if (typeof codeOrToken === "string") {
    return { text: codeOrToken, lang: infostring || "" };
  }
  return { text: codeOrToken.text || "", lang: codeOrToken.lang || "" };
}

const mermaidRenderer = {
  code(codeOrToken: string | Tokens.Code, infostring?: string): string {
    const { text, lang } = fenceParts(codeOrToken, infostring);
    // Escape so untrusted fences cannot break out of the pre; Mermaid
    // reads textContent of .mermaid nodes after we set innerHTML.
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    if (lang === "mermaid") {
      return `<pre class="mermaid">${escaped}</pre>`;
    }
    return `<pre><code class="language-${lang}">${escaped}</code></pre>`;
  },
};

marked.use({ renderer: mermaidRenderer });

function slugFor(file: string): string {
  return file.replace(/\.md$/i, "");
}

function fileIdOf(file: string): string {
  return FILE_ITEM_PREFIX + file;
}

export default function App() {
  const [groups, setGroups] = useState<DocGroup[]>([]);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [html, setHtml] = useState<string>("");
  const [contentError, setContentError] = useState<string | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [search, setSearch] = useState("");
  const [expandedItems, setExpandedItems] = useState<string[]>([]);

  // Load the manifest once.
  useEffect(() => {
    fetch(DOCS_BASE + "manifest.json")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: DocGroup[]) => {
        setGroups(data);
        setExpandedItems(data.map((g) => "group:" + g.group));
      })
      .catch((err) => setManifestError(String(err.message || err)));
  }, []);

  // Pick a file from the URL hash, defaulting to the first doc.
  useEffect(() => {
    if (groups.length === 0) return;
    const slug = decodeURIComponent((location.hash || "").replace(/^#/, ""));
    let match: string | null = null;
    for (const g of groups) {
      for (const it of g.items) {
        if (slugFor(it.file) === slug) match = it.file;
      }
    }
    setSelectedFile(match || groups[0]?.items[0]?.file || null);
  }, [groups]);

  // Fetch + render the selected doc's markdown.
  useEffect(() => {
    if (!selectedFile) return;
    setLoadingDoc(true);
    setContentError(null);
    fetch(DOCS_BASE + selectedFile)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((md) => {
        setHtml(marked.parse(md) as string);
        location.hash = slugFor(selectedFile);
      })
      .catch((err) => setContentError(String(err.message || err)))
      .finally(() => setLoadingDoc(false));
  }, [selectedFile]);

  // Render Mermaid fences after the markdown HTML is mounted.
  // Escaped entities in the HTML string become real text via innerHTML,
  // which Mermaid reads from each pre.mermaid node. Loaded on demand so
  // Remotion's video bundle never pays for Mermaid.
  useEffect(() => {
    if (loadingDoc || !html) return;
    const host = document.querySelector("main div[data-docs-body]");
    if (!host) return;
    const nodes = host.querySelectorAll("pre.mermaid");
    if (nodes.length === 0) return;
    // Per-fence render: one bad fence must not invent SVG or blank siblings.
    void loadMermaid().then(async (mod) => {
      for (const node of Array.from(nodes)) {
        try {
          await mod.default.run({ nodes: [node] });
        } catch {
          if (node.getAttribute("data-mermaid-error")) continue;
          node.setAttribute("data-mermaid-error", "1");
          const note = document.createElement("p");
          note.className = "mermaid-skip-reason";
          note.textContent =
            "Mermaid parse skipped (invalid fence kept as source — no invented diagram).";
          node.parentElement?.insertBefore(note, node);
        }
      }
    });
  }, [html, loadingDoc]);

  const filteredGroups = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return groups;
    return groups
      .map((g) => ({
        ...g,
        items: g.items.filter((it) => it.title.toLowerCase().includes(term)),
      }))
      .filter((g) => g.items.length > 0);
  }, [groups, search]);

  useEffect(() => {
    if (search.trim()) {
      setExpandedItems(filteredGroups.map((g) => "group:" + g.group));
    }
  }, [search, filteredGroups]);

  return (
    <Box sx={{ display: "flex", height: "100vh", bgcolor: "background.default" }}>
      <Paper
        elevation={0}
        square
        sx={{
          width: 300,
          minWidth: 230,
          maxWidth: 380,
          flexShrink: 0,
          borderRight: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <Box sx={{ px: 2, pt: 2, pb: 1, borderBottom: 1, borderColor: "divider" }}>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ letterSpacing: 1, fontSize: 12 }}
          >
            codeExplanation-v2 docs
          </Typography>
        </Box>
        <Box sx={{ p: 1.5 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Filter docs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </Box>
        <Box sx={{ flex: 1, overflowY: "auto", pb: 2 }}>
          {manifestError ? (
            <Alert severity="error" sx={{ m: 1.5 }}>
              Could not load manifest: {manifestError}
            </Alert>
          ) : (
            <SimpleTreeView
              expandedItems={expandedItems}
              onExpandedItemsChange={(_e, ids) => setExpandedItems(ids)}
              selectedItems={selectedFile ? fileIdOf(selectedFile) : null}
              onSelectedItemsChange={(_e, itemId) => {
                if (typeof itemId === "string" && itemId.startsWith(FILE_ITEM_PREFIX)) {
                  setSelectedFile(itemId.slice(FILE_ITEM_PREFIX.length));
                }
              }}
              sx={{ px: 0.5 }}
            >
              {filteredGroups.map((g) => (
                <TreeItem
                  key={g.group}
                  itemId={"group:" + g.group}
                  label={
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        letterSpacing: 0.4,
                        textTransform: "uppercase",
                        color: "text.secondary",
                      }}
                    >
                      {g.group}
                    </Typography>
                  }
                  slots={{ icon: FolderIcon }}
                >
                  {g.items.map((it) => (
                    <TreeItem
                      key={it.file}
                      itemId={fileIdOf(it.file)}
                      label={
                        <Typography variant="body2" noWrap>
                          {it.title}
                        </Typography>
                      }
                      slots={{ icon: DescriptionIcon }}
                    />
                  ))}
                </TreeItem>
              ))}
            </SimpleTreeView>
          )}
        </Box>
      </Paper>

      <Box component="main" sx={{ flex: 1, overflowY: "auto" }}>
        <Box
          sx={{
            maxWidth: 880,
            mx: "auto",
            px: 4,
            py: 5,
            "& h1": {
              fontSize: 30,
              borderBottom: 1,
              borderColor: "divider",
              pb: 1.5,
            },
            "& h2": {
              fontSize: 22,
              mt: 4,
              borderBottom: 1,
              borderColor: "divider",
              pb: 1,
            },
            "& h3": { fontSize: 17, mt: 3, color: "primary.main" },
            "& a": { color: "primary.main" },
            "& code": {
              bgcolor: "#1d2130",
              px: 0.6,
              py: 0.2,
              borderRadius: 1,
              fontSize: "0.9em",
            },
            "& pre": {
              bgcolor: "#1d2130",
              p: 2,
              borderRadius: 2,
              overflowX: "auto",
              border: 1,
              borderColor: "divider",
            },
            "& pre code": { bgcolor: "transparent", p: 0 },
            "& pre.mermaid": {
              bgcolor: "#12151f",
              display: "flex",
              justifyContent: "center",
              p: 2,
            },
            "& pre.mermaid svg": { maxWidth: "100%", height: "auto" },
            "& table": {
              width: "100%",
              borderCollapse: "collapse",
              my: 2,
              fontSize: 14.5,
            },
            "& th, & td": {
              border: 1,
              borderColor: "divider",
              px: 1.25,
              py: 0.75,
              textAlign: "left",
              verticalAlign: "top",
            },
            "& th": { bgcolor: "background.paper", color: "text.secondary" },
            "& blockquote": {
              borderLeft: 3,
              borderColor: "primary.main",
              my: 2,
              px: 2,
              color: "text.secondary",
            },
            "& ul": { pl: 2.5 },
            "& li code": { fontSize: "0.85em" },
            "& .mermaid-skip-reason": {
              color: "text.secondary",
              fontSize: 13,
              fontStyle: "italic",
              my: 1,
            },
            lineHeight: 1.65,
            fontSize: 16,
          }}
        >
          {loadingDoc && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary" }}>
              <CircularProgress size={18} />
              <Typography>Loading…</Typography>
            </Box>
          )}
          {contentError && <Alert severity="error">Could not load doc: {contentError}</Alert>}
          {!loadingDoc && !contentError && (
            // eslint-disable-next-line react/no-danger
            <div data-docs-body dangerouslySetInnerHTML={{ __html: html }} />
          )}
        </Box>
      </Box>
    </Box>
  );
}
