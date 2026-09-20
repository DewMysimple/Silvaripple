export type Envelope<T> =
  { ok: true; data: T } | { ok: false; error: string; code?: string };
