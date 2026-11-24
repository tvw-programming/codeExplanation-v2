import { MyComposition } from "./Composition";
import { CodeExplainerChunkComposition } from "./CodeExplainerChunk";
import { FancyLayoutPrimitivesDemoComposition } from "./fancyLayout/FancyLayoutPrimitivesDemo";
import { BroadcastTemplatesDemoComposition } from "./fancyLayout/broadcast/BroadcastTemplatesDemo";
import { FullVideoComposition, StackVideoCompositions } from "./FullVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <CodeExplainerChunkComposition />
      <FancyLayoutPrimitivesDemoComposition />
      <BroadcastTemplatesDemoComposition />
      <FullVideoComposition />
      <StackVideoCompositions />
    </>
  );
};
