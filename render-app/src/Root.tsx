import { MyComposition } from "./Composition";
import { CodeExplainerChunkComposition } from "./CodeExplainerChunk";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <CodeExplainerChunkComposition />
    </>
  );
};
