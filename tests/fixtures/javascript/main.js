import { helper } from './helper.js';

export function boot() {
  document.addEventListener('click', onClick);
}

function onClick() {
  helper();
}
