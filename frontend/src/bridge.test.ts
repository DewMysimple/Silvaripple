import { describe, expect, it } from 'vitest';
import { invoke, isMockBridge } from './bridge';
import type { Bootstrap } from './types';

describe('desktop bridge adapter', () => {
  it('uses structured mock data without a desktop host', async () => {
    const data = await invoke<Bootstrap>('bootstrap');
    expect(isMockBridge()).toBe(true);
    expect(data.settings.theme).toBe('system');
    expect(data.settings.download_missing_media_default).toBe(true);
    expect(data.settings.allow_legacy_http_media_default).toBe(true);
    expect(data.settings.visual_download_limit_mib).toBe(50);
    expect(data.settings.large_download_limit_mib).toBe(500);
    expect(data.accounts[0].coverage.complete).toBe(true);
  });

  it('stores the persistent media defaults separately from export payload fields', async () => {
    const data = await invoke<{ settings: Record<string, unknown> }>('save_settings', { theme: 'dark' });
    expect(data.settings.allow_legacy_http_media).toBeUndefined();
    expect(data.settings.allow_legacy_http_media_default).toBe(true);
  });
});
