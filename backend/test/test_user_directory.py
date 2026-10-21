import unittest
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, Tenant, TenantMember, Group, GroupMember, Friendship
from app.routers.users import user_directory


class UserDirectoryTests(unittest.TestCase):
    def test_directory_excludes_other_tenants_unaccepted_friends_and_private_groups(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([User(id=i, username=f'user{i}') for i in range(1, 7)])
            tenant = Tenant(id=1, name='Enterprise')
            db.add_all([tenant, Tenant(id=2, name='Other')])
            db.add_all([TenantMember(tenant_id=1, user_id=1), TenantMember(tenant_id=1, user_id=2),
                        TenantMember(tenant_id=1, user_id=3, status='invited'), TenantMember(tenant_id=2, user_id=4)])
            db.add_all([Friendship(requester_id=1, addressee_id=5, status='accepted'),
                        Friendship(requester_id=1, addressee_id=6, status='pending')])
            db.add_all([Group(id=1, name='Visible', created_by=1, tenant_id=1),
                        Group(id=2, name='Private', created_by=4, tenant_id=2)])
            db.add_all([GroupMember(group_id=1, user_id=1), GroupMember(group_id=1, user_id=5), GroupMember(group_id=2, user_id=4)])
            db.commit()
            result = user_directory(db, SimpleNamespace(user=db.get(User, 1), tenant=tenant, is_tenant_admin=False))
            self.assertEqual([p['id'] for p in result['enterprise']['members']], [1, 2])
            self.assertEqual([p['user_id'] for p in result['friends']], [5])
            self.assertEqual([g['id'] for g in result['groups']], [1])
        engine.dispose()
