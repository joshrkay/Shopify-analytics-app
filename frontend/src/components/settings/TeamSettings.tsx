import { useMemo, useState } from 'react';
import { Crown, Eye, Plus, Shield, Trash2, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
  status: 'active' | 'pending';
  avatar?: string;
  joinedDate: string;
}

interface RoleDefinition {
  id: TeamMember['role'];
  name: string;
  icon: LucideIcon;
  permissions: string[];
}

const roles: RoleDefinition[] = [
  {
    id: 'owner',
    name: 'Owner',
    icon: Crown,
    permissions: [
      'Full access to all features',
      'Manage billing and subscription',
      'Add/remove team members',
      'Delete workspace',
    ],
  },
  {
    id: 'admin',
    name: 'Admin',
    icon: Shield,
    permissions: [
      'Manage data sources',
      'Create and edit dashboards',
      'Add/remove team members (except owner)',
      'Configure settings',
    ],
  },
  {
    id: 'editor',
    name: 'Editor',
    icon: Eye,
    permissions: [
      'Create and edit dashboards',
      'View all data sources',
      'Export reports',
      'No access to settings',
    ],
  },
  {
    id: 'viewer',
    name: 'Viewer',
    icon: Eye,
    permissions: [
      'View dashboards',
      'View reports',
      'No editing permissions',
      'No access to settings',
    ],
  },
];

const INVITE_ROLE_OPTIONS: Exclude<TeamMember['role'], 'owner'>[] = ['admin', 'editor', 'viewer'];

function isValidEmail(email: string): boolean {
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailPattern.test(email.trim());
}

export function TeamSettings() {
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Exclude<TeamMember['role'], 'owner'>>('viewer');

  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([
    {
      id: '1',
      name: 'John Doe',
      email: 'john@example.com',
      role: 'owner',
      status: 'active',
      joinedDate: 'Jan 15, 2026',
    },
    {
      id: '2',
      name: 'Sarah Smith',
      email: 'sarah@example.com',
      role: 'admin',
      status: 'active',
      joinedDate: 'Jan 20, 2026',
    },
    {
      id: '3',
      name: 'Mike Johnson',
      email: 'mike@example.com',
      role: 'editor',
      status: 'active',
      joinedDate: 'Feb 1, 2026',
    },
    {
      id: '4',
      name: 'Emily Chen',
      email: 'emily@example.com',
      role: 'viewer',
      status: 'pending',
      joinedDate: 'Invited Feb 10, 2026',
    },
  ]);

  const trimmedEmail = inviteEmail.trim();
  const canSendInvite = isValidEmail(trimmedEmail);

  const selectedRoleSummary = useMemo(
    () => roles.find((role) => role.id === inviteRole)?.permissions[0],
    [inviteRole],
  );

  const handleSendInvite = () => {
    if (!canSendInvite) {
      return;
    }

    const newMember: TeamMember = {
      id: Date.now().toString(),
      name: trimmedEmail.split('@')[0],
      email: trimmedEmail,
      role: inviteRole,
      status: 'pending',
      joinedDate: `Invited ${new Date().toLocaleDateString()}`,
    };

    setTeamMembers((members) => [...members, newMember]);
    setInviteEmail('');
    setInviteRole('viewer');
    setShowInviteModal(false);
  };

  const removeMember = (id: string) => {
    setTeamMembers((members) => members.filter((member) => member.id !== id));
  };

  const updateRole = (id: string, newRole: Exclude<TeamMember['role'], 'owner'>) => {
    setTeamMembers((members) => members.map((member) => (
      member.id === id ? { ...member, role: newRole } : member
    )));
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200" data-testid="team-settings">
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Team Management</h2>
            <p className="text-gray-600">Manage team members and their permissions</p>
          </div>
          <button
            type="button"
            onClick={() => setShowInviteModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
          >
            <Plus className="w-4 h-4" />
            Invite Member
          </button>
        </div>
      </div>

      <div className="p-6">
        <div className="space-y-3">
          {teamMembers.map((member) => {
            const roleInfo = roles.find((role) => role.id === member.role);
            const RoleIcon = roleInfo?.icon ?? Eye;

            return (
              <div
                key={member.id}
                className="border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-semibold">
                      {member.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900">{member.name}</h3>
                        {member.status === 'pending' && (
                          <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs rounded-full">
                            Pending
                          </span>
                        )}
                        {member.role === 'owner' && (
                          <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full flex items-center gap-1">
                            <Crown className="w-3 h-3" />
                            You
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600">{member.email}</p>
                      <p className="text-xs text-gray-500 mt-1">{member.joinedDate}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {member.role !== 'owner' ? (
                      <select
                        value={member.role}
                        onChange={(event) => updateRole(member.id, event.target.value as Exclude<TeamMember['role'], 'owner'>)}
                        className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
                      >
                        <option value="admin">Admin</option>
                        <option value="editor">Editor</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    ) : (
                      <div className="flex items-center gap-2 px-3 py-2 bg-purple-50 border border-purple-200 rounded-lg">
                        <RoleIcon className="w-4 h-4 text-purple-600" />
                        <span className="text-sm font-medium text-purple-900">Owner</span>
                      </div>
                    )}

                    {member.role !== 'owner' && (
                      <button
                        type="button"
                        onClick={() => removeMember(member.id)}
                        className="p-2 hover:bg-red-50 rounded-lg text-red-600"
                        aria-label={`Remove ${member.name}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 pt-8 border-t border-gray-200">
          <h3 className="font-semibold text-gray-900 mb-4">Role Permissions</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {roles.map((role) => {
              const Icon = role.icon;
              return (
                <div key={role.id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Icon className="w-5 h-5 text-gray-600" />
                    <h4 className="font-semibold text-gray-900">{role.name}</h4>
                  </div>
                  <ul className="space-y-2 text-sm text-gray-600">
                    {role.permissions.map((permission) => (
                      <li key={permission} className="flex items-start gap-2">
                        <span className="text-green-600 mt-0.5">✓</span>
                        {permission}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-900">Invite Team Member</h3>
              <button
                type="button"
                onClick={() => setShowInviteModal(false)}
                className="p-2 hover:bg-gray-100 rounded-lg"
                aria-label="Close invite modal"
              >
                <X className="w-5 h-5 text-gray-600" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="team-invite-email" className="block text-sm font-medium text-gray-900 mb-2">
                  Email Address
                </label>
                <input
                  id="team-invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                  placeholder="colleague@example.com"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              <div>
                <label htmlFor="team-invite-role" className="block text-sm font-medium text-gray-900 mb-2">
                  Role
                </label>
                <select
                  id="team-invite-role"
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value as Exclude<TeamMember['role'], 'owner'>)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                >
                  {INVITE_ROLE_OPTIONS.map((roleId) => (
                    <option key={roleId} value={roleId}>{roles.find((role) => role.id === roleId)?.name}</option>
                  ))}
                </select>
                <p className="text-xs text-gray-600 mt-2">{selectedRoleSummary}</p>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm text-blue-900">
                  An invitation email will be sent to {trimmedEmail || 'the email address'} with instructions to join your workspace.
                </p>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                type="button"
                onClick={() => setShowInviteModal(false)}
                className="flex-1 px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSendInvite}
                disabled={!canSendInvite}
                className="flex-1 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                Send Invite
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default TeamSettings;
