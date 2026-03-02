import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock AgencyContext (useTeamMembers calls useAgency for activeTenantId)
vi.mock('../contexts/AgencyContext', () => ({
  useAgency: vi.fn().mockReturnValue({
    activeTenantId: 'test-tenant-id',
    getActiveStore: vi.fn().mockReturnValue(null),
    isAgencyUser: false,
    tenants: [],
    switchTenant: vi.fn(),
  }),
}));

vi.mock('../services/tenantMembersApi', () => ({
  getTeamMembers: vi.fn(),
  inviteMember: vi.fn(),
  updateMemberRole: vi.fn(),
  removeMember: vi.fn(),
  resendInvite: vi.fn(),
}));

// Mock queryClientLite to provide stable hooks that don't infinite-loop in tests.
// useQueryLite's useCallback([queryFn]) creates a new refetch on every render when
// queryFn is an inline closure (as in useTeamMembers), causing an infinite re-fetch
// cycle in the jsdom test environment. This mock provides a simple, stable version.
vi.mock('../hooks/queryClientLite', () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const React = require('react');

  class MockQueryClientLite {
    private versions = new Map<string, number>();
    getVersion(queryKey: readonly unknown[]): number {
      return this.versions.get(JSON.stringify(queryKey)) ?? 0;
    }
    invalidateQueries(queryKey: readonly unknown[]): void {
      const key = JSON.stringify(queryKey);
      const current = this.versions.get(key) ?? 0;
      this.versions.set(key, current + 1);
    }
  }

  const clientInstance = new MockQueryClientLite();

  return {
    useQueryClientLite: () => clientInstance,
    useQueryLite: ({ queryFn }: { queryKey: readonly unknown[]; queryFn: () => Promise<any> }) => {
      const [data, setData] = React.useState<any>(undefined);
      const [isLoading, setIsLoading] = React.useState(true);
      const [error, setError] = React.useState<unknown>(null);

      // Use a ref to hold the latest queryFn to avoid dependency churn
      const queryFnRef = React.useRef(queryFn);
      queryFnRef.current = queryFn;

      const refetch = React.useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
          const nextData = await queryFnRef.current();
          setData(nextData);
          return nextData;
        } catch (err) {
          setError(err);
          throw err;
        } finally {
          setIsLoading(false);
        }
      }, []);

      // Fire once on mount
      React.useEffect(() => {
        refetch().catch(() => undefined);
      }, [refetch]);

      return { data, isLoading, error, refetch };
    },
    useMutationLite: (options: { mutationFn: (vars: any) => Promise<any>; onSuccess?: (data: any, vars: any) => void | Promise<void>; onError?: (err: unknown, vars: any) => void }) => {
      const { mutationFn, onSuccess, onError } = options;
      const [isPending, setIsPending] = React.useState(false);
      const [error, setError] = React.useState<unknown>(null);

      const mutateAsync = React.useCallback(async (variables: any) => {
        setIsPending(true);
        setError(null);
        try {
          const result = await mutationFn(variables);
          await onSuccess?.(result, variables);
          return result;
        } catch (err) {
          setError(err);
          onError?.(err, variables);
          throw err;
        } finally {
          setIsPending(false);
        }
      }, [mutationFn, onError, onSuccess]);

      return React.useMemo(() => ({ mutateAsync, isPending, error }), [error, isPending, mutateAsync]);
    },
  };
});

import {
  REMOVE_UNDO_WINDOW_MS,
  useInviteMember,
  useRemoveMember,
  useTeamMembers,
  useUpdateMemberRole,
} from '../hooks/useTeamMembers';
import * as teamApi from '../services/tenantMembersApi';

const mocked = vi.mocked(teamApi);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  mocked.getTeamMembers.mockResolvedValue([{ id: '1', userId: 'u1', name: 'A', email: 'a@a.com', role: 'admin', status: 'active', joinedDate: '' }]);
  mocked.inviteMember.mockResolvedValue({ id: '2', userId: 'u2', name: 'B', email: 'b@b.com', role: 'viewer', status: 'pending', joinedDate: '' });
  mocked.updateMemberRole.mockResolvedValue({ id: '1', userId: 'u1', name: 'A', email: 'a@a.com', role: 'editor', status: 'active', joinedDate: '' });
  mocked.removeMember.mockResolvedValue({ success: true });
});

describe('useTeamMembers', () => {
  it('useTeamMembers returns member list', async () => {
    const { result } = renderHook(() => useTeamMembers());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.members).toHaveLength(1);
  });

  it('useInviteMember adds pending member optimistically', async () => {
    const membersHook = renderHook(() => useTeamMembers());
    const inviteHook = renderHook(() => useInviteMember());

    await waitFor(() => expect(membersHook.result.current.isLoading).toBe(false));

    mocked.inviteMember.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
      return { id: '2', userId: 'u2', name: 'B', email: 'b@b.com', role: 'viewer', status: 'pending', joinedDate: '' };
    });

    let mutationPromise: Promise<unknown> | null = null;
    await act(async () => {
      mutationPromise = inviteHook.result.current.mutateAsync({ email: 'b@b.com', role: 'viewer' });
    });

    await waitFor(() => expect(membersHook.result.current.members.length).toBeGreaterThan(1));
    expect(membersHook.result.current.members.some((member) => member.id.startsWith('optimistic-member-'))).toBe(true);

    await act(async () => {
      await mutationPromise;
    });

    await waitFor(() => expect(mocked.inviteMember).toHaveBeenCalledWith('test-tenant-id', { email: 'b@b.com', role: 'viewer' }));
  });

  it('useUpdateMemberRole optimistic role change', async () => {
    const membersHook = renderHook(() => useTeamMembers());
    const updateHook = renderHook(() => useUpdateMemberRole());

    await waitFor(() => expect(membersHook.result.current.isLoading).toBe(false));

    mocked.updateMemberRole.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      return { id: '1', userId: 'u1', name: 'A', email: 'a@a.com', role: 'editor', status: 'active', joinedDate: '' };
    });

    let mutationPromise: Promise<unknown> | null = null;
    await act(async () => {
      mutationPromise = updateHook.result.current.mutateAsync({ memberId: '1', role: 'editor' });
    });

    await waitFor(() => expect(membersHook.result.current.members[0]?.role).toBe('editor'));

    await act(async () => {
      await mutationPromise;
    });

    expect(mocked.updateMemberRole).toHaveBeenCalledWith('test-tenant-id', '1', 'editor');
  });

  it('useRemoveMember supports undo within toast window', async () => {
    const membersHook = renderHook(() => useTeamMembers());
    const removeHook = renderHook(() => useRemoveMember());

    await waitFor(() => expect(membersHook.result.current.isLoading).toBe(false));

    let mutationPromise: Promise<{ success: boolean; undone?: boolean }> | null = null;
    await act(async () => {
      mutationPromise = removeHook.result.current.mutateAsync('1');
    });

    await waitFor(() => expect(removeHook.result.current.undoMemberId).toBe('1'));

    await act(async () => {
      removeHook.result.current.undoLastRemove();
    });

    await waitFor(() => expect(membersHook.result.current.members.find((member) => member.id === '1')).toBeDefined());

    await expect(mutationPromise!).resolves.toMatchObject({ undone: true });
    expect(mocked.removeMember).not.toHaveBeenCalled();
  });

  it('Query invalidation after mutations executes delete after undo window', async () => {
    const membersHook = renderHook(() => useTeamMembers());
    const removeHook = renderHook(() => useRemoveMember());

    await waitFor(() => expect(membersHook.result.current.isLoading).toBe(false));
    vi.useFakeTimers();

    const mutationPromise = removeHook.result.current.mutateAsync('1');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REMOVE_UNDO_WINDOW_MS + 1);
    });

    await expect(mutationPromise).resolves.toEqual({ success: true });
    expect(mocked.removeMember).toHaveBeenCalledWith('test-tenant-id', '1');
  });
});
