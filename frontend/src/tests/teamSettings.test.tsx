import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { TeamSettings } from '../components/settings/TeamSettings';

describe('TeamSettings', () => {
  it('renders seeded team members and role permissions', () => {
    render(<TeamSettings />);
    expect(screen.getByText('Team Management')).toBeInTheDocument();
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('Role Permissions')).toBeInTheDocument();
    expect(screen.getByText('Full access to all features')).toBeInTheDocument();
  });

  it('invites a member with validated email and shows pending badge', async () => {
    const user = userEvent.setup();
    render(<TeamSettings />);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'Invite Member' }));
    });
    const sendButton = screen.getByRole('button', { name: 'Send Invite' });
    expect(sendButton).toBeDisabled();

    await act(async () => {
      await user.type(screen.getByLabelText('Email Address'), 'new.user@example.com');
    });
    expect(sendButton).toBeEnabled();

    await act(async () => {
      await user.click(sendButton);
    });
    expect(screen.getByText('new.user@example.com')).toBeInTheDocument();
    expect(screen.getAllByText('Pending').length).toBeGreaterThan(0);
  });

  it('updates member role and removes non-owner members', async () => {
    const user = userEvent.setup();
    render(<TeamSettings />);

    const selects = screen.getAllByRole('combobox');
    await act(async () => {
      await user.selectOptions(selects[0], 'viewer');
    });
    expect((selects[0] as HTMLSelectElement).value).toBe('viewer');

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'Remove Sarah Smith' }));
    });
    expect(screen.queryByText('Sarah Smith')).not.toBeInTheDocument();
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });
});
