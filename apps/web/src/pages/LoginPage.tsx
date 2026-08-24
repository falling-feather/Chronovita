import {
  ArrowRightOutlined,
  CaretRightOutlined,
  LockOutlined,
  PauseOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Alert, Button, Form, Input } from 'antd';
import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { AuthLoadingScreen } from '../auth/RouteGuards';
import {
  principalLandingPath,
  roleCompatibleReturnPath,
  safeReturnPath,
} from '../auth/types';
import { ApiError } from '../utils/api';
import { APP_VERSION_LABEL } from '../version';

interface LoginValues {
  username: string;
  password: string;
}

interface LoginGalleryScene {
  id: string;
  era: string;
  title: string;
  src: string;
  srcSet: string;
}

const LOGIN_GALLERY_SCENES: readonly LoginGalleryScene[] = [
  {
    id: 'flood',
    era: '先秦',
    title: '治水齐心',
    src: '/assets/entry/login-flood-420.webp',
    srcSet: '/assets/entry/login-flood-420.webp 420w, /assets/entry/login-flood-640.webp 640w',
  },
  {
    id: 'qin-reform',
    era: '战国秦',
    title: '制度之辩',
    src: '/assets/entry/login-qin-reform-420.webp',
    srcSet: '/assets/entry/login-qin-reform-420.webp 420w, /assets/entry/login-qin-reform-640.webp 640w',
  },
  {
    id: 'han-caravan',
    era: '汉',
    title: '西行交往',
    src: '/assets/entry/login-han-caravan-420.webp',
    srcSet: '/assets/entry/login-han-caravan-420.webp 420w, /assets/entry/login-han-caravan-640.webp 640w',
  },
  {
    id: 'tang-city',
    era: '唐',
    title: '长安万象',
    src: '/assets/entry/login-tang-city-420.webp',
    srcSet: '/assets/entry/login-tang-city-420.webp 420w, /assets/entry/login-tang-city-640.webp 640w',
  },
] as const;

const LOGIN_GALLERY_TRACKS = [
  [0, 3, 2, 1],
  [1, 2, 0, 3],
  [3, 0, 1, 2],
] as const;

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
  const [galleryPaused, setGalleryPaused] = useState(false);
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
    <main className={`chrono-login-page${galleryPaused ? ' is-gallery-paused' : ''}`}>
      <section className="chrono-login-gallery" aria-label="中国历史教学插画长卷">
        <div className="chrono-login-brand">
          <div className="chrono-logo-mark">历</div>
          <div>
            <div className="chrono-logo-cn">历史未来课堂</div>
            <div className="chrono-logo-en">Chronovita · {APP_VERSION_LABEL}</div>
          </div>
        </div>
        <div className="chrono-login-gallery-tracks" aria-hidden="true">
          {LOGIN_GALLERY_TRACKS.map((sequence, trackIndex) => (
            <div className={`chrono-login-gallery-column is-column-${trackIndex + 1}`} key={sequence.join('-')}>
              <div className="chrono-login-gallery-track">
                {[...sequence, ...sequence].map((sceneIndex, itemIndex) => {
                  const scene = LOGIN_GALLERY_SCENES[sceneIndex];
                  return (
                    <figure key={`${scene.id}-${itemIndex}`}>
                      <img
                        src={scene.src}
                        srcSet={scene.srcSet}
                        sizes="(max-width: 980px) 68vw, 24vw"
                        alt=""
                        decoding="async"
                      />
                      <figcaption><strong>{scene.title}</strong><span>{scene.era}</span></figcaption>
                    </figure>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="chrono-login-gallery-shade" aria-hidden="true" />
        <p className="chrono-login-gallery-boundary">教学插画 · 非史料影像</p>
        <button
          type="button"
          className="chrono-login-gallery-toggle"
          aria-label={galleryPaused ? '继续播放历史画卷' : '暂停历史画卷'}
          aria-pressed={galleryPaused}
          onClick={() => setGalleryPaused((paused) => !paused)}
        >
          {galleryPaused ? <CaretRightOutlined /> : <PauseOutlined />}
        </button>
      </section>

      <section className="chrono-login-panel">
        <div className="chrono-login-paper" aria-labelledby="login-title">
          <div className="chrono-login-paper-mark" aria-hidden="true">历</div>
          <header>
            <div className="chrono-login-paper-brand">历史未来课堂</div>
            <h1 id="login-title">账号登录</h1>
          </header>

          {requestedPath && (
            <p className="chrono-login-return" title={requestedPath}>
              <ArrowRightOutlined /> 登录后返回原页面
            </p>
          )}
          {auth.status === 'unavailable' && (
            <Alert
              className="chrono-login-alert"
              type="warning"
              showIcon
              message="课堂服务暂不可用"
              action={<Button size="small" onClick={() => void auth.restore()}>重试</Button>}
            />
          )}
          {error && <Alert className="chrono-login-alert" type="error" showIcon message={error} />}

          <Form<LoginValues>
            className="chrono-login-form"
            layout="vertical"
            requiredMark={false}
            onFinish={submit}
            autoComplete="on"
          >
            <Form.Item
              label="课堂账号"
              name="username"
              rules={[{ required: true, message: '请输入课堂账号' }]}
            >
              <Input
                size="large"
                prefix={<UserOutlined />}
                autoComplete="username"
                autoFocus
                placeholder="请输入课堂账号"
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
              进入课堂
            </Button>
          </Form>

          <p className="chrono-login-security"><SafetyCertificateOutlined /> 本机安全会话</p>
          <p className="chrono-login-footnote">没有账号？请联系课堂管理员</p>
        </div>
      </section>
    </main>
  );
}
