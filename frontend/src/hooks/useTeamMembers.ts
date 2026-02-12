import { useMemo, useRef, useState } from 'react';
import {
  getTeamMembers,
  inviteMember,
  removeMember,
  resendInvite,
  updateMemberRole,
} from '../services/tenantMembersApi';
import type { TeamInvite, TeamInviteRole, TeamMember } from '../types/settingsTypes';
import { useMutationLite, useQueryClientLite, useQueryLite } from './queryClientLite';

const TEAM_MEMBERS_QUERY_KEY = ['settings', 'team-members'] as const;

export function useTeamMembers() {
  const query = useQueryLite({
    queryKey: TEAM_MEMBERS_QUERY_KEY,
    queryFn: getTeamMembers,
  });
  const [optimisticMembers, setOptimisticMembers] = useState<TeamMember[] | null>(null);

  const members = useMemo(() => optimisticMembers ?? query.data ?? [], [optimisticMembers, query.data]);

  const replaceMembers = (updater: (members: TeamMember[]) => TeamMember[]) => {
    setOptimisticMembers((current) => {
      const baseMembers = current ?? query.data ?? [];
      return updater(baseMembers);
    });
  };

  const clearOptimisticMembers = () => {
    setOptimisticMembers(null);
  };

  return {
    members,
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refetch: query.refetch,
    replaceMembers,
    clearOptimisticMembers,
  };
}

export function useInviteMember() {
  const queryClient = useQueryClientLite();
  const optimisticIdRef = useRef(0);
  const membersQuery = useTeamMembers();

  return useMutationLite({
    mutationFn: async (invite: TeamInvite) => {
      const optimisticId = `optimistic-member-${optimisticIdRef.current++}`;
      const optimisticMember: TeamMember = {
        id: optimisticId,
        userId: optimisticId,
        name: invite.email,
        email: invite.email,
        role: invite.role,
        status: 'pending',
        joinedDate: new Date().toISOString(),
      };

      membersQuery.replaceMembers((members) => [...members, optimisticMember]);

      try {
        const createdMember = await inviteMember(invite);
        membersQuery.replaceMembers((members) => members.map((member) => (
          member.id === optimisticId ? createdMember : member
        )));
        return createdMember;
      } catch (error) {
        membersQuery.replaceMembers((members) => members.filter((member) => member.id !== optimisticId));
        throw error;
      }
    },
    onSuccess: () => {
      membersQuery.clearOptimisticMembers();
      queryClient.invalidateQueries(TEAM_MEMBERS_QUERY_KEY);
    },
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClientLite();
  const membersQuery = useTeamMembers();

  return useMutationLite({
    mutationFn: async ({ memberId, role }: { memberId: string; role: TeamInviteRole }) => {
      const previousMembers = membersQuery.members;
      membersQuery.replaceMembers((members) => members.map((member) => (
        member.id === memberId ? { ...member, role } : member
      )));

      try {
        return await updateMemberRole(memberId, role);
      } catch (error) {
        membersQuery.replaceMembers(() => previousMembers);
        throw error;
      }
    },
    onSuccess: () => {
      membersQuery.clearOptimisticMembers();
      queryClient.invalidateQueries(TEAM_MEMBERS_QUERY_KEY);
    },
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClientLite();
  const membersQuery = useTeamMembers();

  return useMutationLite({
    mutationFn: async (memberId: string) => {
      const previousMembers = membersQuery.members;
      membersQuery.replaceMembers((members) => members.filter((member) => member.id !== memberId));

      try {
        return await removeMember(memberId);
      } catch (error) {
        membersQuery.replaceMembers(() => previousMembers);
        throw error;
      }
    },
    onSuccess: () => {
      membersQuery.clearOptimisticMembers();
      queryClient.invalidateQueries(TEAM_MEMBERS_QUERY_KEY);
    },
  });
}

export function useResendInvite() {
  return useMutationLite({
    mutationFn: (memberId: string) => resendInvite(memberId),
  });
}

export { TEAM_MEMBERS_QUERY_KEY };
