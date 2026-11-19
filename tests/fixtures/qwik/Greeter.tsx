import { component$, useSignal } from '@builder.io/qwik';

export const Greeter = component$(() => {
  const name = useSignal('world');
  return (
    <button onClick$={() => { name.value = 'Qwik'; }}>
      Hello {name.value}
    </button>
  );
});
