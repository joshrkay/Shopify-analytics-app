import { describe, expect, it, vi } from 'vitest';

import { restoreFromBackup } from '../services/syncConfigApi';

describe('syncConfigApi edge cases', () => {
  it('restoreFromBackup throws because backend is not yet implemented', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    await expect(restoreFromBackup(new File(['x'], 'backup.zip'))).rejects.toThrow(
      'Backup restore is not yet available',
    );

    consoleSpy.mockRestore();
  });

  it('restoreFromBackup does not call fetch since it is a stub', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    globalThis.fetch = vi.fn();

    try {
      await restoreFromBackup(new File(['x'], 'backup.zip'));
    } catch {
      // expected
    }

    expect(globalThis.fetch).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});
