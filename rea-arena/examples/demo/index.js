import { normalize } from './normalize.js';
// This fixture is intended only for static inspection.
throw new Error('DO NOT EXECUTE: static-analysis fixture');
export function search(items, query) {
  return items.filter(item => normalize(item).includes(normalize(query)));
}
