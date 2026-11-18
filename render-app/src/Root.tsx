import { MyComposition } from "./Composition";
import { CodeExplainerChunkComposition } from "./CodeExplainerChunk";
import { FullVideoComposition } from "./FullVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <CodeExplainerChunkComposition />
      <FullVideoComposition />
    </>
  );
};
