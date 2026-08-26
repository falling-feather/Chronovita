import {
  App as AntdApp,
  Avatar,
  Badge,
  Button,
  Dropdown,
  Input,
  Layout,
  Menu,
  Result,
  Space,
  Tag,
  Tooltip,
  type MenuProps,
} from 'antd';
import {
  BellOutlined,
  CloseOutlined,
  LogoutOutlined,
  ReloadOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuth } from './auth/AuthContext';
import {
  AuthLoadingScreen,
  RequireRoles,
  RoleHome,
} from './auth/RouteGuards';
import {
  ROLE_LABELS,
  principalLandingPath,
  type UserRole,
} from './auth/types';
import { APP_VERSION_LABEL } from './version';
import { bindMessage } from './utils/toast';
import { toast } from './utils/toast';
import { IS_STATIC_PREVIEW } from './runtime';

const LoginPage = lazy(() => import('./pages/LoginPage'));
const HomePage = lazy(() => import('./pages/HomePage'));
const CoursesPage = lazy(() => import('./pages/CoursesPage'));
const CourseDetailPage = lazy(() => import('./pages/CourseDetailPage'));
const LessonPage = lazy(() => import('./pages/lesson/LessonPage'));
const LearningPage = lazy(() => import('./pages/LearningPage'));
const PracticePage = lazy(() => import('./pages/PracticePage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const AdminContentPage = lazy(() => import('./pages/AdminContentPage'));
const AdminContentPreviewPage = lazy(() => import('./pages/AdminContentPreviewPage'));
const AdminAccountsPage = lazy(() => import('./pages/AdminAccountsPage'));
const TeacherLearningReviewPage = lazy(() => import('./pages/TeacherLearningReviewPage'));

const { Header, Content, Footer } = Layout;
const STUDENT_ROLES: UserRole[] = ['student'];
const CONTENT_ROLES: UserRole[] = ['teacher', 'reviewer', 'admin'];
const TEACHER_ROLES: UserRole[] = ['teacher', 'admin'];
const ADMIN_ROLES: UserRole[] = ['admin'];

interface ShellNavItem {
  key: string;
  label: ReactNode;
}

function selectedKey(pathname: string, items: ShellNavItem[]): string {
  return items
    .map((item) => item.key)
    .filter((key) => key === '/' ? pathname === '/' : pathname.startsWith(key))
    .sort((left, right) => right.length - left.length)[0] || '';
}

function Logo() {
  return (
    <Link to={IS_STATIC_PREVIEW ? '/' : '/workspace'} className="chrono-logo" aria-label="返回角色工作区">
      <div className="chrono-logo-mark">历</div>
      <div>
        <div className="chrono-logo-cn">历史未来课堂</div>
        <div className="chrono-logo-en">Chronovita</div>
      </div>
    </Link>
  );
}

function UserSlot() {
  const auth = useAuth();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const isStudent = auth.mode === 'legacy-local' || auth.principal?.roles.includes('student');

  if (IS_STATIC_PREVIEW) {
    return <Tag className="chrono-static-preview-tag" color="cyan">GitHub Pages · 只读预览</Tag>;
  }

  const submitSearch = () => {
    const keyword = q.trim();
    nav(keyword ? `/courses?q=${encodeURIComponent(keyword)}` : '/courses');
  };

  const refresh = async () => {
    try {
      await auth.refreshSession();
      toast.success('课堂会话已安全刷新');
    } catch (error) {
      auth.invalidate();
      toast.error(error instanceof Error ? error.message : '会话刷新失败，请重新登录');
      nav('/login', { replace: true });
    }
  };

  const logout = async () => {
    try {
      await auth.logout();
      nav('/login', { replace: true });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '退出失败');
      nav('/login', { replace: true });
    }
  };

  return (
    <Space size={12} align="center" className="chrono-user-slot">
      {isStudent && (
        <form
          className={`chrono-shell-search${searchOpen ? ' is-open' : ''}`}
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            if (searchOpen) submitSearch(); else setSearchOpen(true);
          }}
        >
          <Button
            type="text"
            htmlType={searchOpen ? 'submit' : 'button'}
            className="chrono-shell-icon-button"
            icon={<SearchOutlined />}
            aria-label={searchOpen ? '提交课程搜索' : '打开课程搜索'}
            aria-expanded={searchOpen}
            onClick={() => {
              if (!searchOpen) setSearchOpen(true);
            }}
          />
          {searchOpen && (
            <Input
              autoFocus
              placeholder="课程、知识点或历史人物"
              variant="borderless"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              onPressEnter={(event) => {
                event.preventDefault();
                submitSearch();
              }}
              suffix={(
                <button
                  type="button"
                  className="chrono-shell-search-close"
                  aria-label="关闭课程搜索"
                  onClick={() => {
                    setQ('');
                    setSearchOpen(false);
                  }}
                >
                  <CloseOutlined />
                </button>
              )}
            />
          )}
        </form>
      )}

      {auth.mode === 'legacy-local' ? (
        <Tooltip title="显式兼容配置：学生资产仍使用本机身份，内容工具使用旧共享令牌。">
          <Tag color="gold">本地兼容</Tag>
        </Tooltip>
      ) : auth.principal ? (
        <>
          {isStudent && (
            <Badge dot>
              <Button
                type="text"
                className="chrono-shell-icon-button"
                icon={<BellOutlined />}
                aria-label="查看学习通知"
                onClick={() => nav('/profile?tab=2')}
              />
            </Badge>
          )}
          <Dropdown
            trigger={['click']}
            menu={{
              items: [
                {
                  key: 'identity',
                  disabled: true,
                  label: (
                    <div className="chrono-user-menu-identity">
                      <strong>{auth.principal.display_name}</strong>
                      <span>@{auth.principal.username}</span>
                      <Space size={[0, 3]} wrap>
                        {auth.principal.roles.map((role) => <Tag key={role}>{ROLE_LABELS[role]}</Tag>)}
                      </Space>
                    </div>
                  ),
                },
                { type: 'divider' },
                {
                  key: 'workspace',
                  icon: <SafetyCertificateOutlined />,
                  label: '我的工作区',
                  onClick: () => nav(principalLandingPath(auth.principal)),
                },
                {
                  key: 'refresh',
                  icon: <ReloadOutlined />,
                  label: '刷新会话',
                  onClick: refresh,
                },
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  danger: true,
                  label: '退出登录',
                  onClick: logout,
                },
              ],
            }}
          >
            <Button type="text" className="chrono-account-trigger">
              <Avatar icon={<UserOutlined />} />
              <span>{auth.principal.display_name}</span>
            </Button>
          </Dropdown>
        </>
      ) : null}
    </Space>
  );
}

function MessageBinder() {
  const { message } = AntdApp.useApp();
  useEffect(() => { bindMessage(message); }, [message]);
  return null;
}

function ForbiddenPage() {
  const auth = useAuth();
  const location = useLocation();
  const nav = useNavigate();
  const state = location.state as { from?: string; requiredRoles?: UserRole[] } | null;
  const required = state?.requiredRoles?.map((role) => ROLE_LABELS[role]).join('、');
  return (
    <Result
      status="403"
      title="当前身份不能进入这个工作区"
      subTitle={required
        ? `该页面面向：${required}。你的账号仍保持登录，没有执行任何越权动作。`
        : '服务端与页面都将按角色检查操作权限。'}
      extra={(
        <Space wrap>
          <Button type="primary" onClick={() => nav(principalLandingPath(auth.principal), { replace: true })}>
            返回我的工作区
          </Button>
          {state?.from && <Tag>被拒绝页面：{state.from}</Tag>}
        </Space>
      )}
    />
  );
}

function ShellLayout() {
  const auth = useAuth();
  const location = useLocation();
  const isHome = location.pathname === '/';
  const navItems = useMemo<ShellNavItem[]>(() => {
    if (IS_STATIC_PREVIEW) {
      return [
        { key: '/', label: <Link to="/">首页</Link> },
        { key: '/courses', label: <Link to="/courses">课程中心</Link> },
      ];
    }
    const items: ShellNavItem[] = [];
    if (auth.mode === 'legacy-local' || auth.principal?.roles.includes('student')) {
      items.push(
        { key: '/', label: <Link to="/">首页</Link> },
        { key: '/courses', label: <Link to="/courses">课程中心</Link> },
        { key: '/learning', label: <Link to="/learning">我的学习</Link> },
        { key: '/practice', label: <Link to="/practice">实践课堂</Link> },
        { key: '/profile', label: <Link to="/profile">个人中心</Link> },
      );
    }
    if (auth.mode === 'legacy-local' || auth.can('content.read')) {
      items.push({ key: '/admin/content', label: <Link to="/admin/content">内容工作台</Link> });
    }
    if (auth.mode === 'accounts' && auth.can('student.summary')) {
      items.push({ key: '/teacher/learning', label: <Link to="/teacher/learning">成果批阅</Link> });
    }
    if (auth.mode === 'accounts' && auth.can('auth.manage_users')) {
      items.push({ key: '/admin/accounts', label: <Link to="/admin/accounts">账户管理</Link> });
    }
    return items;
  }, [auth.can, auth.mode, auth.principal]);

  return (
    <Layout
      className={isHome ? 'chrono-shell-layout is-home' : 'chrono-shell-layout'}
      style={{ minHeight: '100vh', background: 'var(--bg-page)' }}
    >
      <Header className="chrono-shell-header">
        <Logo />
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey(location.pathname, navItems)]}
          items={navItems as MenuProps['items']}
          className="chrono-nav"
        />
        <div className="chrono-header-spacer" />
        <UserSlot />
      </Header>
      <Content className={`chrono-shell-content${isHome ? ' is-home' : ''}`}>
        <Suspense fallback={<AuthLoadingScreen />}>
          <Outlet />
        </Suspense>
      </Content>
      {!isHome && (
        <Footer className="chrono-shell-footer">
          Chronovita · {APP_VERSION_LABEL} · {IS_STATIC_PREVIEW ? 'GitHub Pages 只读内容预览' : '本地课堂'}
        </Footer>
      )}
    </Layout>
  );
}

function AppRoutes() {
  return (
    <Suspense fallback={<AuthLoadingScreen />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/workspace" element={<RoleHome />} />
        <Route element={<ShellLayout />}>
          <Route path="/forbidden" element={<ForbiddenPage />} />

          <Route element={<RequireRoles roles={STUDENT_ROLES} />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/courses/:courseId" element={<CourseDetailPage />} />
            <Route path="/courses/:courseId/lessons/:lessonId" element={<LessonPage />} />
            <Route path="/learning" element={<LearningPage />} />
            <Route path="/practice" element={<PracticePage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Route>

          <Route element={<RequireRoles roles={CONTENT_ROLES} />}>
            <Route path="/admin/content" element={<AdminContentPage />} />
            <Route path="/admin/content/preview" element={<AdminContentPreviewPage />} />
          </Route>

          <Route element={<RequireRoles roles={TEACHER_ROLES} allowLegacy={false} />}>
            <Route path="/teacher/learning" element={<TeacherLearningReviewPage />} />
          </Route>

          <Route element={<RequireRoles roles={ADMIN_ROLES} allowLegacy={false} />}>
            <Route path="/admin/accounts" element={<AdminAccountsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <AntdApp>
      <MessageBinder />
      <AppRoutes />
    </AntdApp>
  );
}
