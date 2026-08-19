import React, { useState, useEffect } from 'react';
import { Shield, UserPlus, Users, Key, CheckCircle2, Lock, Users2, Globe, Plus } from 'lucide-react';



interface SettingsRBACProps {
  token: string;
}

export const SettingsRBAC: React.FC<SettingsRBACProps> = ({ token }) => {
  const [users, setUsers] = useState<any[]>([]);
  const [groups, setGroups] = useState<any[]>([]);
  const [roles, setRoles] = useState<Record<string, string[]>>({});
  const [projects, setProjects] = useState<any[]>([]);

  // Active view tab inside RBAC settings: 'users' | 'groups' | 'roles'
  const [rbacTab, setRbacTab] = useState<'users' | 'groups' | 'roles'>('users');

  // New user form state
  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState('Developer');
  const [newGroup, setNewGroup] = useState('Healthcare Data Engineering');
  const [newTenant, setNewTenant] = useState('healthcare_prod_workspace');
  const [userMsg, setUserMsg] = useState<string | null>(null);

  // New group form state
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupRole, setNewGroupRole] = useState('Developer');
  const [newGroupWorkspace, setNewGroupWorkspace] = useState('healthcare_prod_workspace');

  const fetchRBACData = async () => {
    try {
      const uRes = await fetch('/rbac/users', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (uRes.ok) {
        const uData = await uRes.json();
        setUsers(uData.users || []);
      }

      const gRes = await fetch('/rbac/groups', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (gRes.ok) {
        const gData = await gRes.json();
        setGroups(gData.groups || []);
      }

      const rRes = await fetch('/rbac/roles', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (rRes.ok) {
        const rData = await rRes.json();
        setRoles(rData.roles || {});
      }

      const pRes = await fetch('/projects', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (pRes.ok) {
        const pData = await pRes.json();
        setProjects(pData.projects || []);
      }
    } catch (err) {
      console.error('Error fetching RBAC data:', err);
    }
  };

  useEffect(() => {
    fetchRBACData();
  }, []);

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim()) return;
    setUserMsg(null);

    try {
      const res = await fetch('/rbac/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          username: newUsername.trim(),
          role: newRole,
          group: newGroup,
          tenant_id: newTenant,
        }),
      });

      if (res.ok) {
        setUserMsg(`Successfully assigned role '${newRole}' and group '${newGroup}' to user '${newUsername}'`);
        setNewUsername('');
        fetchRBACData();
      }
    } catch (err: any) {
      setUserMsg(`Error: ${err.message}`);
    }
  };

  const handleAddGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;

    try {
      const res = await fetch('/rbac/groups', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newGroupName.trim(),
          default_role: newGroupRole,
          default_workspace: newGroupWorkspace,
        }),
      });

      if (res.ok) {
        setNewGroupName('');
        fetchRBACData();
      }
    } catch (err: any) {
      console.error('Failed to create group:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Security, RBAC & Group-Based Access Control (GBAC)</h2>
            <p className="text-xs text-slate-500">Manage user access, user groups, global platform admin permissions, and workspace scoping</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={() => setRbacTab('users')}
              className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                rbacTab === 'users' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Users ({users.length})
            </button>
            <button
              onClick={() => setRbacTab('groups')}
              className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                rbacTab === 'groups' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              User Groups ({groups.length})
            </button>
            <button
              onClick={() => setRbacTab('roles')}
              className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                rbacTab === 'roles' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Roles Matrix
            </button>
          </div>

          <div className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-200 flex items-center gap-1.5">
            <Lock className="w-3.5 h-3.5" /> GBAC Enforced
          </div>
        </div>
      </div>

      {/* VIEW 1: USERS & USER PROVISIONING */}
      {rbacTab === 'users' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Users List Table */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Users className="w-4 h-4 text-indigo-600" /> User Accounts & Group Assignments
              </h3>
              <span className="text-xs font-semibold text-slate-500">{users.length} Provisioned Users</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <th className="py-2.5 px-3">User ID</th>
                    <th className="py-2.5 px-3">Username</th>
                    <th className="py-2.5 px-3">User Group</th>
                    <th className="py-2.5 px-3">Assigned Role</th>
                    <th className="py-2.5 px-3">Tenant Workspace Scope</th>
                    <th className="py-2.5 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-slate-400">{u.id}</td>
                      <td className="py-2.5 px-3 font-semibold text-slate-900">{u.username}</td>
                      <td className="py-2.5 px-3 text-slate-600 font-medium">{u.group || 'General'}</td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                            u.role === 'SuperAdmin' || u.role === 'PlatformAdmin'
                              ? 'bg-purple-50 text-purple-700 border-purple-200'
                              : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                          }`}
                        >
                          {u.role}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px]">
                        {u.tenant_id.includes('*') ? (
                          <span className="inline-flex items-center gap-1 text-purple-700 font-bold bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                            <Globe className="w-3 h-3" /> Global Platform Scope
                          </span>
                        ) : (
                          <span className="text-slate-700">{u.tenant_id}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-semibold">
                          {u.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* User Provisioning Form */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
              <UserPlus className="w-4 h-4 text-indigo-600" /> Provision New User
            </h3>

            {userMsg && (
              <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-800 text-xs font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" /> {userMsg}
              </div>
            )}

            <form onSubmit={handleAddUser} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Username</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="e.g. platform_ops_lead"
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs text-slate-900 focus:outline-none focus:border-indigo-600"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Assigned User Group</label>
                <select
                  value={newGroup}
                  onChange={(e) => setNewGroup(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-medium text-slate-900"
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.name}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Platform Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-medium text-slate-900"
                >
                  <option value="PlatformAdmin">PlatformAdmin (Global Scope)</option>
                  <option value="SuperAdmin">SuperAdmin (Full Platform Control)</option>
                  <option value="ProjectAdmin">ProjectAdmin (Workspace Scope)</option>
                  <option value="Developer">Developer (Pipeline Authoring)</option>
                  <option value="Operator">Operator (Lifecycle & DLQ Replay)</option>
                  <option value="Viewer">Viewer (Read-Only)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Tenant Workspace Scope</label>
                <select
                  value={newTenant}
                  onChange={(e) => setNewTenant(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-semibold text-slate-900"
                >
                  <option value="* (Global Scope)">* (Global Scope — Platform Admin / All Projects)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.id})
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-sm flex items-center justify-center gap-1.5"
              >
                <UserPlus className="w-3.5 h-3.5" /> Provision Account
              </button>
            </form>
          </div>
        </div>
      )}

      {/* VIEW 2: USER GROUPS & GROUP-BASED ACCESS CONTROL (GBAC) */}
      {rbacTab === 'groups' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Users2 className="w-4 h-4 text-indigo-600" /> Defined User Groups & Inherited Workspace Policies
              </h3>
              <span className="text-xs font-semibold text-slate-500">{groups.length} Active Groups</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {groups.map((grp) => (
                <div key={grp.id} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="text-xs font-bold text-slate-900">{grp.name}</h4>
                      <div className="text-[11px] font-mono text-slate-500">{grp.id}</div>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 text-[10px] font-bold font-mono">
                      {grp.members_count} Members
                    </span>
                  </div>

                  <div className="space-y-1 text-xs pt-2 border-t border-slate-200/60">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Default Role:</span>
                      <span className="font-semibold text-slate-800">{grp.default_role}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Workspace Scope:</span>
                      <span className="font-mono text-indigo-700 font-semibold">{grp.default_workspace}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Create User Group Form */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
              <Plus className="w-4 h-4 text-indigo-600" /> Create User Group
            </h3>

            <form onSubmit={handleAddGroup} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Group Name</label>
                <input
                  type="text"
                  placeholder="e.g. Risk Compliance Group"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs text-slate-900 focus:outline-none focus:border-indigo-600"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Default Role</label>
                <select
                  value={newGroupRole}
                  onChange={(e) => setNewGroupRole(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-medium text-slate-900"
                >
                  <option value="Developer">Developer</option>
                  <option value="Operator">Operator</option>
                  <option value="ProjectAdmin">ProjectAdmin</option>
                  <option value="Viewer">Viewer</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Default Workspace Scope</label>
                <select
                  value={newGroupWorkspace}
                  onChange={(e) => setNewGroupWorkspace(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-semibold text-slate-900"
                >
                  <option value="* (Global Scope)">* (Global Scope)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-sm flex items-center justify-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" /> Create Group
              </button>
            </form>
          </div>
        </div>
      )}

      {/* VIEW 3: ROLE PERMISSIONS MATRIX */}
      {rbacTab === 'roles' && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
            <Key className="w-4 h-4 text-indigo-600" /> Platform Role Permissions Matrix
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(roles).map(([rName, pList]) => (
              <div key={rName} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <div className="font-bold text-xs text-indigo-900 flex items-center justify-between">
                  <span>{rName}</span>
                  <span className="text-[10px] text-slate-500 font-mono">{pList.length} permissions</span>
                </div>
                <div className="space-y-1">
                  {pList.map((p, i) => (
                    <div key={i} className="text-[11px] font-mono text-slate-700 bg-white px-2 py-0.5 rounded border border-slate-200">
                      ✓ {p}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
