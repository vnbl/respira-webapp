import { nanoquery } from '@nanostores/query';

export const [createFetcherStore, createMutatorStore] = nanoquery({
  fetcher: (...keys) => {
    return fetch(keys.join('')).then((r) =>r.json())
}   
});