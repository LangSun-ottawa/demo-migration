import { createdRecordCard } from './created-record';

describe('Created record cards', () => {
  it('uses the explicit created record, not the last snapshot entry', () => {
    const card = createdRecordCard('call-1', 'create_admin_profile', {
      profiles: [{ id: 999, name: 'Unrelated' }],
      created_record: { resource: 'profiles', record: { id: 6, name: 'New Profile', access_level: 'readonly' } },
    });
    expect(card?.id).toBe(6);
    expect(card?.name).toBe('New Profile');
    expect(card?.route).toBe('/admin-profiles');
    expect(card?.fields).toEqual([{ label: 'Access', value: 'readonly' }]);
  });

  it('does not invent a card for snapshots or mismatched tools', () => {
    expect(createdRecordCard('call-1', 'create_admin_profile', { profiles: [{ id: 6 }] })).toBeNull();
    expect(createdRecordCard('call-1', 'create_admin_user', {
      created_record: { resource: 'profiles', record: { id: 6, name: 'Wrong resource' } },
    })).toBeNull();
  });
});
