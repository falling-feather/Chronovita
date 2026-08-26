import { apiResponseError } from '../utils/api';
import type {
  AuthRuntimeResponse,
  Principal,
  SessionResponse,
  UserAccount,
  UserRole,
} from './types';

const AUTH_BASE = '/api/v1/auth';

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(AUTH_BASE + path, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event('chronovita:session-invalid'));
    }
    throw await apiResponseError(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const authApi = {
  runtime: (signal?: AbortSignal) =>
    authFetch<AuthRuntimeResponse>('/config', { signal }),
  me: (signal?: AbortSignal) =>
    authFetch<{ principal: Principal; source: string }>('/me', { signal }),
  login: (username: string, password: string) =>
    authFetch<SessionResponse>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  refresh: () =>
    authFetch<SessionResponse>('/refresh', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  logout: () => authFetch<void>('/logout', { method: 'POST' }),
  revokeOwnSessions: () =>
    authFetch<{ user: UserAccount; revoked_sessions: number }>('/sessions/revoke-all', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  users: (signal?: AbortSignal) =>
    authFetch<{ items: UserAccount[] }>('/users', { signal }),
  createUser: (body: {
    username: string;
    password: string;
    display_name: string;
    roles: UserRole[];
  }) => authFetch<UserAccount>('/users', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  updateUser: (
    userId: string,
    body: { display_name?: string; roles?: UserRole[]; enabled?: boolean },
  ) => authFetch<UserAccount>(`/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),
  resetPassword: (userId: string, password: string) =>
    authFetch<UserAccount>(`/users/${encodeURIComponent(userId)}/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  revokeUserSessions: (userId: string) =>
    authFetch<{ user: UserAccount; revoked_sessions: number }>(
      `/users/${encodeURIComponent(userId)}/sessions/revoke`,
      { method: 'POST', body: JSON.stringify({}) },
    ),
};
