import { MyComposition } from "./Composition";
import { CodeExplainerChunkComposition } from "./CodeExplainerChunk";
import { FancyLayoutPrimitivesDemoComposition } from "./fancyLayout/FancyLayoutPrimitivesDemo";
import { FullVideoComposition, StackVideoCompositions } from "./FullVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <CodeExplainerChunkComposition />
      <FancyLayoutPrimitivesDemoComposition />
      <FullVideoComposition />
      <StackVideoCompositions />
    </>
  );
};
