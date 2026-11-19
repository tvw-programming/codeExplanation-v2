import { createSignal } from 'solid-js';

export function Counter() {
  const [count, setCount] = createSignal(0);
  return (
    <div>
      <Button onClick={() => setCount(count() + 1)} />
      <span>{count()}</span>
    </div>
  );
}
