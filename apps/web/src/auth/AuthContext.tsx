import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, api, type AccountProfile } from '../utils/api';
import { authApi } from './client';
import {
  hasPermission as principalHasPermission,
  type AuthMode,
  type AuthPermission,
  type Principal,
  type SessionResponse,
} from './types';
import { IS_STATIC_PREVIEW } from '../runtime';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'legacy' | 'unavailable';

interface AuthContextValue {
  mode: AuthMode | null;
  status: AuthStatus;
  principal: Principal | null;
  lastSession: SessionResponse | null;
  login: (username: string, password: string) => Promise<Principal>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<Principal>;
  restore: () => Promise<void>;
  invalidate: () => void;
  can: (permission: AuthPermission) => boolean;
  profile: AccountProfile | null;
  applyProfile: (profile: AccountProfile) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [lastSession, setLastSession] = useState<SessionResponse | null>(null);
  const [storedProfile, setStoredProfile] = useState<AccountProfile | null>(null);
  const profile = storedProfile?.user_id === principal?.user_id ? storedProfile : null;
  const applyProfile = useCallback((value: AccountProfile) => {
    setStoredProfile(value);
    setPrincipal((current) => current?.user_id === value.user_id
      ? { ...current, display_name: value.display_name } : current);
  }, []);

  useEffect(() => {
    let active = true;
    if (mode === 'accounts' && principal?.user_id) {
      api.profile().then((value) => {
        if (active) setStoredProfile((current) => current?.user_id === value.user_id
          && current.revision > value.revision ? current : value);
      }).catch(() => {});
    }
    return () => { active = false; };
  }, [mode, principal?.user_id]);

  useEffect(() => {
    document.documentElement.dataset.readingSize = profile?.reading_size ?? 'standard';
    return () => { delete document.documentElement.dataset.readingSize; };
  }, [profile?.reading_size]);

  const invalidate = useCallback(() => {
    setStoredProfile(null);
    setPrincipal(null);
    setLastSession(null);
    setStatus((current) => current === 'legacy' ? current : 'anonymous');
  }, []);

  const restore = useCallback(async () => {
    setStatus('loading');
    if (IS_STATIC_PREVIEW) {
      setMode('legacy-local');
      setPrincipal(null);
      setLastSession(null);
      setStatus('legacy');
      return;
    }
    let resolvedMode: AuthMode | null = null;
    try {
      const runtime = await authApi.runtime();
      resolvedMode = runtime.mode;
      setMode(runtime.mode);
      setLastSession(null);
      if (runtime.mode === 'legacy-local') {
        setPrincipal(null);
        setStatus('legacy');
        return;
      }
      const response = await authApi.me();
      setPrincipal(response.principal);
      setStatus('authenticated');
    } catch (error) {
      setPrincipal(null);
      setLastSession(null);
      if (error instanceof ApiError && error.status === 401) {
        setStatus('anonymous');
        return;
      }
      if (!resolvedMode) setMode(null);
      setStatus('unavailable');
    }
  }, []);

  useEffect(() => {
    void restore();
  }, [restore]);

  useEffect(() => {
    if (mode !== 'accounts' || status !== 'authenticated') return;
    let active = true;
    const checkCurrentAccount = () => {
      authApi.me().then(({ principal: current }) => {
        if (active) setPrincipal(current);
      }).catch(() => {});
    };
    window.addEventListener('focus', checkCurrentAccount);
    return () => { active = false; window.removeEventListener('focus', checkCurrentAccount); };
  }, [mode, status]);

  useEffect(() => {
    const onSessionInvalid = () => {
      if (mode === 'accounts') invalidate();
    };
    window.addEventListener('chronovita:session-invalid', onSessionInvalid);
    return () => window.removeEventListener('chronovita:session-invalid', onSessionInvalid);
  }, [invalidate, mode]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await authApi.login(username, password);
    setMode('accounts');
    setPrincipal(session.principal);
    setLastSession(session);
    setStatus('authenticated');
    return session.principal;
  }, []);

  const logout = useCallback(async () => {
    if (mode === 'legacy-local') return;
    await authApi.logout();
    invalidate();
  }, [invalidate, mode]);

  const refreshSession = useCallback(async () => {
    const session = await authApi.refresh();
    setPrincipal(session.principal);
    setLastSession(session);
    setStatus('authenticated');
    return session.principal;
  }, []);

  const can = useCallback(
    (permission: AuthPermission) => mode === 'legacy-local'
      || principalHasPermission(principal, permission),
    [mode, principal],
  );

  const value = useMemo<AuthContextValue>(() => ({
    mode,
    status,
    principal,
    lastSession,
    login,
    logout,
    refreshSession,
    restore,
    invalidate,
    can,
    profile,
    applyProfile,
  }), [
    can,
    profile,
    applyProfile,
    invalidate,
    lastSession,
    login,
    logout,
    mode,
    principal,
    refreshSession,
    restore,
    status,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
