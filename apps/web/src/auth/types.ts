export type AuthMode = 'accounts' | 'legacy-local';
export type UserRole = 'student' | 'teacher' | 'reviewer' | 'admin';
export type AuthPermission =
  | 'student.own'
  | 'content.read'
  | 'content.author'
  | 'content.review'
  | 'content.publish'
  | 'student.feedback'
  | 'student.summary'
  | 'audit.review'
  | 'auth.manage_users'
  | 'audit.read';

export interface Principal {
  user_id: string;
  username: string;
  display_name: string;
  roles: UserRole[];
  session_id?: string | null;
  auth_version: number;
  synthetic: boolean;
}

export interface UserAccount {
  user_id: string;
  username: string;
  display_name: string;
  roles: UserRole[];
  enabled: boolean;
  auth_version: number;
  created_at: string;
  updated_at: string;
}

export interface SessionResponse {
  transport: 'cookie';
  expires_at: string;
  absolute_expires_at: string;
  principal: Principal;
}

export interface AuthRuntimeResponse {
  mode: AuthMode;
  browser_transport: 'http-only-cookie';
}

export const ROLE_LABELS: Record<UserRole, string> = {
  student: '学生',
  teacher: '教师',
  reviewer: '审校者',
  admin: '管理员',
};

const ROLE_PERMISSIONS: Record<UserRole, readonly AuthPermission[]> = {
  student: ['student.own'],
  teacher: ['content.read', 'content.author', 'student.summary', 'student.feedback'],
  reviewer: ['content.read', 'content.review', 'audit.review'],
  admin: [
    'auth.manage_users',
    'audit.read',
    'content.read',
    'content.author',
    'content.review',
    'content.publish',
    'student.feedback',
    'student.summary',
  ],
};

export function hasAnyRole(
  principal: Principal | null,
  roles: readonly UserRole[],
): boolean {
  return Boolean(principal?.roles.some((role) => roles.includes(role)));
}

export function hasPermission(
  principal: Principal | null,
  permission: AuthPermission,
): boolean {
  return Boolean(principal?.roles.some((role) => ROLE_PERMISSIONS[role].includes(permission)));
}

export function principalLandingPath(principal: Principal | null): string {
  if (!principal) return '/login';
  if (principal.roles.includes('admin')) return '/admin/accounts';
  if (principal.roles.includes('teacher')) return '/teacher/learning';
  if (principal.roles.includes('reviewer')) return '/admin/content';
  return '/';
}

export function safeReturnPath(candidate: unknown): string | null {
  if (typeof candidate !== 'string') return null;
  if (!candidate.startsWith('/') || candidate.startsWith('//')) return null;
  if (candidate === '/login' || candidate.startsWith('/login?')) return null;
  return candidate;
}

export function roleCompatibleReturnPath(
  candidate: string | null,
  roles: readonly UserRole[],
): string | null {
  if (!candidate) return null;
  if (candidate === '/admin/accounts' || candidate.startsWith('/admin/accounts/')) {
    return roles.includes('admin') ? candidate : null;
  }
  if (candidate === '/admin/content' || candidate.startsWith('/admin/content/')) {
    return roles.some((role) => role === 'teacher' || role === 'reviewer' || role === 'admin')
      ? candidate
      : null;
  }
  if (candidate === '/teacher/learning' || candidate.startsWith('/teacher/learning/')) {
    return roles.some((role) => role === 'teacher' || role === 'admin') ? candidate : null;
  }
  if (
    candidate === '/'
    || candidate.startsWith('/courses')
    || candidate.startsWith('/learning')
    || candidate.startsWith('/practice')
    || candidate.startsWith('/profile')
  ) {
    return roles.includes('student') ? candidate : null;
  }
  return candidate;
}
