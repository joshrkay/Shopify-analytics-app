import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getTeamMembers,
  inviteMember,
  removeMember,
  resendInvite,
  updateMemberRole,
} from '../services/tenantMembersApi';
import type { TeamInvite, TeamInviteRole, TeamMember } from '../types/settingsTypes';

export function useTeamMembers() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  useEffect(() => () => {
    isMountedRef.current = false;
  }, []);

  const refetch = useCallback(async () => {
    try {
      if (isMountedRef.current) {
        setIsLoading(true);
        setError(null);
      }
      const nextMembers = await getTeamMembers();
      if (isMountedRef.current) {
        setMembers(nextMembers);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load team members');
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { members, isLoading, error, refetch, setMembers };
}

export function useInviteMember() {
  return useCallback((invite: TeamInvite) => inviteMember(invite), []);
}

export function useUpdateMemberRole() {
  return useCallback((memberId: string, role: TeamInviteRole) => updateMemberRole(memberId, role), []);
}

export function useRemoveMember() {
  return useCallback((memberId: string) => removeMember(memberId), []);
}

export function useResendInvite() {
  return useCallback((memberId: string) => resendInvite(memberId), []);
}
