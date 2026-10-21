import { Alert, Button, Result, Spin } from 'antd';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { hasAnyRole, principalLandingPath, type UserRole } from './types';

export function AuthLoadingScreen() {
  return (
    <div className="chrono-auth-loading" role="status" aria-live="polite">
      <Spin size="large" />
      <span>正在恢复课堂身份…</span>
    </div>
  );
}

export function RequireRoles({
  roles,
  allowLegacy = true,
}: {
  roles: readonly UserRole[];
  allowLegacy?: boolean;
}) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === 'loading') return <AuthLoadingScreen />;
  if (auth.status === 'unavailable') {
    return (
      <Result
        status="warning"
        title="暂时无法确认登录状态"
        subTitle="为避免越权，课堂已停止载入。请检查本机服务后重试。"
        extra={<Button onClick={() => void auth.restore()}>重新连接</Button>}
      />
    );
  }
  if (auth.mode === 'legacy-local') {
    return allowLegacy ? <Outlet /> : <Navigate to="/forbidden" replace />;
  }
  if (auth.status !== 'authenticated' || !auth.principal) {
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }
  if (!hasAnyRole(auth.principal, roles)) {
    return (
      <Navigate
        to="/forbidden"
        replace
        state={{ from: location.pathname, requiredRoles: roles }}
      />
    );
  }
  return <Outlet />;
}

export function RoleHome() {
  const auth = useAuth();
  if (auth.status === 'loading') return <AuthLoadingScreen />;
  if (auth.mode === 'legacy-local') return <Navigate to="/" replace />;
  if (!auth.principal) return <Navigate to="/login" replace />;
  return <Navigate to={principalLandingPath(auth.principal)} replace />;
}

export function AuthUnavailableHint() {
  return (
    <Alert
      type="info"
      showIcon
      message="课堂账号由本机统一管理"
      description="密码只发送给当前课堂服务；浏览器通过 HttpOnly Cookie 维持会话，不保存访问令牌。"
    />
  );
}
