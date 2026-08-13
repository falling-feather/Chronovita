import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  hasAnyRole,
  hasPermission,
  principalLandingPath,
  roleCompatibleReturnPath,
  safeReturnPath,
  type Principal,
  type UserRole,
} from './types';

function principal(role: UserRole): Principal {
  return {
    user_id: `usr-${role}`,
    username: role,
    display_name: role,
    roles: [role],
    session_id: `session-${role}`,
    auth_version: 1,
    synthetic: false,
  };
}

describe('role policy', () => {
  it('keeps the four classroom responsibilities separate', () => {
    const student = principal('student');
    const teacher = principal('teacher');
    const reviewer = principal('reviewer');
    const admin = principal('admin');

    expect(hasPermission(student, 'student.own')).toBe(true);
    expect(hasPermission(student, 'content.read')).toBe(false);
    expect(hasPermission(teacher, 'content.author')).toBe(true);
    expect(hasPermission(teacher, 'content.review')).toBe(false);
    expect(hasPermission(reviewer, 'content.review')).toBe(true);
    expect(hasPermission(reviewer, 'content.author')).toBe(false);
    expect(hasPermission(reviewer, 'content.publish')).toBe(false);
    expect(hasPermission(admin, 'content.publish')).toBe(true);
    expect(hasPermission(admin, 'auth.manage_users')).toBe(true);
  });

  it('selects a role workspace and rejects mismatched route groups', () => {
    expect(principalLandingPath(principal('student'))).toBe('/');
    expect(principalLandingPath(principal('teacher'))).toBe('/admin/content');
    expect(principalLandingPath(principal('reviewer'))).toBe('/admin/content');
    expect(principalLandingPath(principal('admin'))).toBe('/admin/accounts');
    expect(hasAnyRole(principal('student'), ['teacher', 'reviewer', 'admin'])).toBe(false);
    expect(hasAnyRole(principal('reviewer'), ['teacher', 'reviewer', 'admin'])).toBe(true);
  });
});

describe('login return path', () => {
  it('keeps an internal target and rejects open redirects or login loops', () => {
    expect(safeReturnPath('/courses/C-prequin-state?lesson=L101')).toBe(
      '/courses/C-prequin-state?lesson=L101',
    );
    expect(safeReturnPath('//evil.example')).toBeNull();
    expect(safeReturnPath('https://evil.example')).toBeNull();
    expect(safeReturnPath('/login')).toBeNull();
    expect(safeReturnPath(undefined)).toBeNull();
  });

  it('returns only to a workspace compatible with the authenticated role', () => {
    expect(roleCompatibleReturnPath('/', ['admin'])).toBeNull();
    expect(roleCompatibleReturnPath('/', ['student'])).toBe('/');
    expect(roleCompatibleReturnPath('/admin/accounts', ['student'])).toBeNull();
    expect(roleCompatibleReturnPath('/admin/accounts', ['admin'])).toBe('/admin/accounts');
    expect(roleCompatibleReturnPath('/admin/content', ['reviewer'])).toBe('/admin/content');
  });
});

describe('browser credential boundary', () => {
  it('keeps the accounts API client free of browser token persistence', () => {
    const clientSource = readFileSync(new URL('./client.ts', import.meta.url), 'utf8');
    const editorSource = readFileSync(
      new URL('../pages/AdminContentPage.tsx', import.meta.url),
      'utf8',
    );

    expect(clientSource).not.toMatch(/localStorage|sessionStorage|Authorization|access_token/);
    expect(editorSource).not.toContain('localStorage.setItem(TOKEN_KEY');
    expect(editorSource).toContain("auth.mode === 'accounts'");
    expect(editorSource).toContain('COOKIE_AUTH_CREDENTIAL');
  });
});
