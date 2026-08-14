import { ArrowRightOutlined, LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Space, Tag } from 'antd';
import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { AuthLoadingScreen, AuthUnavailableHint } from '../auth/RouteGuards';
import {
  principalLandingPath,
  roleCompatibleReturnPath,
  safeReturnPath,
} from '../auth/types';
import { ApiError } from '../utils/api';

interface LoginValues {
  username: string;
  password: string;
}

function loginErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '账号或密码不正确，请重新输入。';
    if (error.status === 429) return '尝试次数较多，请稍后再试。';
    if (error.status === 409) return '当前服务未启用统一账户模式。';
  }
  return error instanceof Error ? error.message : '登录失败，请检查本机课堂服务。';
}

export default function LoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestedPath = safeReturnPath(
    (location.state as { from?: unknown } | null)?.from,
  );

  if (auth.status === 'loading') return <AuthLoadingScreen />;
  if (auth.mode === 'legacy-local') return <Navigate to="/" replace />;
  if (auth.status === 'authenticated' && auth.principal) {
    return <Navigate
      to={roleCompatibleReturnPath(requestedPath, auth.principal.roles)
        || principalLandingPath(auth.principal)}
      replace
    />;
  }

  const submit = async (values: LoginValues) => {
    setBusy(true);
    setError('');
    try {
      const principal = await auth.login(values.username, values.password);
      navigate(
        roleCompatibleReturnPath(requestedPath, principal.roles)
          || principalLandingPath(principal),
        { replace: true },
      );
    } catch (caught) {
      setError(loginErrorText(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="chrono-login-page">
      <section className="chrono-login-story" aria-label="课堂学习流程">
        <div className="chrono-login-brand">
          <div className="chrono-logo-mark">历</div>
          <div>
            <div className="chrono-logo-cn">历史未来课堂</div>
            <div className="chrono-logo-en">Chronovita · V0.10.11</div>
          </div>
        </div>
        <div className="chrono-login-copy">
          <Tag bordered={false}>本地课堂 · 统一入口</Tag>
          <h1>进入历史现场，<br />把选择写成证据。</h1>
          <p>同一入口识别学生、教师、审校者与管理员；每个人只进入自己的课堂职责。</p>
          <ol className="chrono-login-route">
            <li><span>01</span><strong>踏勘</strong><small>观察遗址、地图与史料边界</small></li>
            <li><span>02</span><strong>抉择</strong><small>在六回合中承担治理代价</small></li>
            <li><span>03</span><strong>召见</strong><small>只依据当前课程证据追问</small></li>
            <li><span>04</span><strong>卷宗</strong><small>把选择与解释留在知识画板</small></li>
          </ol>
        </div>
      </section>

      <section className="chrono-login-panel">
        <div className="chrono-login-form-wrap">
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <span className="chrono-course-eyeline">UNIFIED CLASSROOM ACCOUNT</span>
            <h2>账号登录</h2>
            <p className="chrono-login-lead">使用教师分配的课堂账号继续学习或内容工作。</p>
          </Space>

          {requestedPath && (
            <Alert
              className="chrono-login-return"
              type="info"
              showIcon
              message="登录后返回原页面"
              description={requestedPath}
            />
          )}
          {auth.status === 'unavailable' && (
            <Alert
              type="warning"
              showIcon
              message="课堂服务暂不可用"
              description="请确认本机服务已启动，然后重试。"
              action={<Button size="small" onClick={() => void auth.restore()}>重试</Button>}
            />
          )}
          {error && <Alert type="error" showIcon message={error} />}

          <Form<LoginValues>
            layout="vertical"
            requiredMark={false}
            onFinish={submit}
            autoComplete="on"
          >
            <Form.Item
              label="账号"
              name="username"
              rules={[{ required: true, message: '请输入课堂账号' }]}
            >
              <Input
                size="large"
                prefix={<UserOutlined />}
                autoComplete="username"
                autoFocus
                placeholder="例如 student.dayu"
              />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined />}
                autoComplete="current-password"
                placeholder="输入课堂密码"
              />
            </Form.Item>
            <Button
              block
              size="large"
              type="primary"
              htmlType="submit"
              loading={busy}
              icon={<ArrowRightOutlined />}
              iconPosition="end"
            >
              进入我的工作区
            </Button>
          </Form>

          <AuthUnavailableHint />
          <p className="chrono-login-footnote">没有账号或忘记密码，请联系本课堂管理员重置。</p>
        </div>
      </section>
    </main>
  );
}
