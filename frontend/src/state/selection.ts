export const toggleId = (values: string[], id: string) =>
  values.includes(id) ? values.filter((item) => item !== id) : [...values, id];

export const ensureId = (values: string[], id: string) =>
  values.includes(id) ? values : [...values, id];

export const mergeIds = (values: string[], additions: string[]) =>
  Array.from(new Set([...values, ...additions]));
