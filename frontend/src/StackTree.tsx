/** The left sidebar: one collapsible section per detected technology,
 *  each holding that stack's files as a folder tree.
 *
 *  Section order comes from project.json (frontend first, then
 *  backends, then anything detection could not place) — nothing here
 *  knows the name of a single stack.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ButtonBase from "@mui/material/ButtonBase";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FolderIcon from "@mui/icons-material/FolderOutlined";
import DescriptionIcon from "@mui/icons-material/DescriptionOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import HourglassIcon from "@mui/icons-material/HourglassEmpty";

import { allFolderIds, buildFileTree, collapseChains, type TreeNode } from "./fileTree";
import { formatDuration, formatTime, isReachable } from "./segments";
import { NEUTRAL_STACK_COLOR } from "./theme";
import type { StackView } from "./types";

const ROLE_LABEL: Record<string, string> = {
  frontend: "Frontend",
  backend: "Backend",
  other: "Other",
};

type Props = {
  views: StackView[];
  selected: { stack: string; filePath: string } | null;
  durations: Record<string, number | null>;
  onSelect: (stack: string, filePath: string) => void;
};

const FileRow: React.FC<{
  node: TreeNode;
  depth: number;
  stack: string;
  color: string;
  selected: boolean;
  playable: boolean;
  onSelect: (filePath: string) => void;
}> = ({ node, depth, color, selected, playable, onSelect }) => {
  const file = node.file!;
  const duration = file.endSeconds - file.startSeconds;

  return (
    <Tooltip
      title={
        playable
          ? `${file.purpose ?? file.fileName} — starts at ${formatTime(file.startSeconds)}`
          : "Not in the rendered video yet — click to read what the pipeline found"
      }
      placement="right"
      enterDelay={600}
    >
      <ButtonBase
        onClick={() => onSelect(file.filePath)}
        sx={{
          width: "100%",
          justifyContent: "flex-start",
          pl: `${depth * 14 + 10}px`,
          pr: 1,
          py: 0.5,
          borderRadius: 1,
          borderLeft: selected ? `3px solid ${color}` : "3px solid transparent",
          bgcolor: selected ? "rgba(110,168,254,0.12)" : "transparent",
          "&:hover": { bgcolor: "rgba(255,255,255,0.05)" },
        }}
      >
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ width: "100%" }}>
          {playable ? (
            <PlayArrowIcon sx={{ fontSize: 15, color, flexShrink: 0 }} />
          ) : (
            <HourglassIcon sx={{ fontSize: 14, color: "text.secondary", flexShrink: 0 }} />
          )}
          <DescriptionIcon sx={{ fontSize: 14, color: "text.secondary", flexShrink: 0 }} />
          <Typography
            variant="body2"
            noWrap
            sx={{
              flexGrow: 1,
              textAlign: "left",
              color: playable ? "text.primary" : "text.secondary",
              fontWeight: selected ? 600 : 400,
            }}
          >
            {node.label}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}
          >
            {formatDuration(duration)}
          </Typography>
        </Stack>
      </ButtonBase>
    </Tooltip>
  );
};

const TreeLevel: React.FC<{
  nodes: TreeNode[];
  depth: number;
  stack: string;
  color: string;
  openFolders: Set<string>;
  toggleFolder: (id: string) => void;
  selectedPath: string | null;
  hasVideo: boolean;
  videoDuration: number | null;
  onSelect: (filePath: string) => void;
}> = ({
  nodes,
  depth,
  stack,
  color,
  openFolders,
  toggleFolder,
  selectedPath,
  hasVideo,
  videoDuration,
  onSelect,
}) => (
  <>
    {nodes.map((node) =>
      node.children ? (
        <Box key={node.id}>
          <ButtonBase
            onClick={() => toggleFolder(node.id)}
            sx={{
              width: "100%",
              justifyContent: "flex-start",
              pl: `${depth * 14 + 6}px`,
              py: 0.5,
              borderRadius: 1,
              "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
            }}
          >
            {openFolders.has(node.id) ? (
              <ExpandMoreIcon sx={{ fontSize: 16, color: "text.secondary" }} />
            ) : (
              <ChevronRightIcon sx={{ fontSize: 16, color: "text.secondary" }} />
            )}
            <FolderIcon sx={{ fontSize: 15, color: "text.secondary", mr: 0.75 }} />
            <Typography variant="body2" noWrap sx={{ color: "text.secondary" }}>
              {node.label}
            </Typography>
          </ButtonBase>
          <Collapse in={openFolders.has(node.id)} unmountOnExit>
            <TreeLevel
              nodes={node.children}
              depth={depth + 1}
              stack={stack}
              color={color}
              openFolders={openFolders}
              toggleFolder={toggleFolder}
              selectedPath={selectedPath}
              hasVideo={hasVideo}
              videoDuration={videoDuration}
              onSelect={onSelect}
            />
          </Collapse>
        </Box>
      ) : (
        <FileRow
          key={node.id}
          node={node}
          depth={depth}
          stack={stack}
          color={color}
          selected={selectedPath === node.file!.filePath}
          playable={isReachable(node.file!, { hasVideo, videoDuration })}
          onSelect={onSelect}
        />
      ),
    )}
  </>
);

const StackSection: React.FC<{
  view: StackView;
  selectedPath: string | null;
  videoDuration: number | null;
  onSelect: (stack: string, filePath: string) => void;
}> = ({ view, selectedPath, videoDuration, onSelect }) => {
  const hasVideo = Boolean(view.videoUrl);
  const color = view.index?.theme?.onDark ?? view.index?.theme?.primary ?? NEUTRAL_STACK_COLOR;
  const tree = useMemo(
    () => collapseChains(buildFileTree(view.index?.files ?? [])),
    [view.index],
  );
  const [openFolders, setOpenFolders] = useState<Set<string>>(new Set());
  const [expandedOnce, setExpandedOnce] = useState(false);
  const [sectionOpen, setSectionOpen] = useState(true);

  // Open everything the first time a tree arrives: the point of the
  // sidebar is seeing the whole repo, and it is never large enough to
  // need hiding.
  if (!expandedOnce && tree.length > 0) {
    setOpenFolders(new Set(allFolderIds(tree)));
    setExpandedOnce(true);
  }

  const toggleFolder = (id: string) =>
    setOpenFolders((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Box sx={{ mb: 1.5 }}>
      <ButtonBase
        onClick={() => setSectionOpen((open) => !open)}
        sx={{
          width: "100%",
          justifyContent: "flex-start",
          px: 1,
          py: 1,
          borderRadius: 1,
          borderLeft: `3px solid ${color}`,
          bgcolor: "rgba(255,255,255,0.03)",
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center" sx={{ width: "100%" }}>
          {sectionOpen ? (
            <ExpandMoreIcon sx={{ fontSize: 18, color }} />
          ) : (
            <ChevronRightIcon sx={{ fontSize: 18, color }} />
          )}
          <Typography sx={{ fontWeight: 700, color, textTransform: "capitalize" }}>
            {view.stack.name}
          </Typography>
          <Chip
            size="small"
            label={ROLE_LABEL[view.stack.role] ?? view.stack.role}
            sx={{ height: 18, fontSize: 11, bgcolor: "rgba(255,255,255,0.07)" }}
          />
          <Box sx={{ flexGrow: 1 }} />
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {hasVideo
              ? `${view.stack.chunkCount} file${view.stack.chunkCount === 1 ? "" : "s"}`
              : "video not rendered yet"}
          </Typography>
        </Stack>
      </ButtonBase>

      <Collapse in={sectionOpen} unmountOnExit>
        <Box sx={{ mt: 0.5 }}>
          {tree.length === 0 ? (
            <Typography variant="caption" sx={{ pl: 2, color: "text.secondary" }}>
              Waiting for this stack's segment index…
            </Typography>
          ) : (
            <TreeLevel
              nodes={tree}
              depth={0}
              stack={view.stack.name}
              color={color}
              openFolders={openFolders}
              toggleFolder={toggleFolder}
              selectedPath={selectedPath}
              hasVideo={hasVideo}
              videoDuration={videoDuration}
              onSelect={(filePath) => onSelect(view.stack.name, filePath)}
            />
          )}
        </Box>
      </Collapse>
    </Box>
  );
};

export const StackTree: React.FC<Props> = ({ views, selected, durations, onSelect }) => (
  <Box sx={{ p: 1.5 }}>
    {views.map((view) => (
      <StackSection
        key={view.stack.name}
        view={view}
        selectedPath={selected?.stack === view.stack.name ? selected.filePath : null}
        videoDuration={durations[view.stack.name] ?? null}
        onSelect={onSelect}
      />
    ))}
  </Box>
);
