import { MyComposition } from "./Composition";
import { CodeExplainerChunkComposition } from "./CodeExplainerChunk";
import { FullVideoComposition, StackVideoCompositions } from "./FullVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <CodeExplainerChunkComposition />
      <FullVideoComposition />
      <StackVideoCompositions />
    </>
  );
};
