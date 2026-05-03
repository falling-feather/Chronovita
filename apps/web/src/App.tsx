import { App as AntdApp, Layout, Menu, Input, Avatar, Badge, Space } from 'antd';
import { BellOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons';
import { Link, Route, Routes, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import HomePage from './pages/HomePage';
import CoursesPage from './pages/CoursesPage';
import CourseDetailPage from './pages/CourseDetailPage';
import LessonPage from './pages/lesson/LessonPage';
import LearningPage from './pages/LearningPage';
import PracticePage from './pages/PracticePage';
import ProfilePage from './pages/ProfilePage';
import { bindMessage } from './utils/toast';

const { Header, Content, Footer } = Layout;

const navItems = [
  { key: '/', label: <Link to="/">首页</Link> },
  { key: '/courses', label: <Link to="/courses">课程中心</Link> },
  { key: '/learning', label: <Link to="/learning">我的学习</Link> },
  { key: '/practice', label: <Link to="/practice">实践课堂</Link> },
  { key: '/profile', label: <Link to="/profile">个人中心</Link> },
];

function selectedKey(pathname: string): string {
  const top = '/' + (pathname.split('/')[1] || '');
  return navItems.find((i) => i.key === top)?.key ?? '/';
}

function Logo() {
  return (
    <div className="chrono-logo">
      <div className="chrono-logo-mark">历</div>
      <div>
        <div className="chrono-logo-cn">历史未来课堂</div>
        <div className="chrono-logo-en">FUTURE CLASSROOM</div>
      </div>
    </div>
  );
}

function UserSlot() {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  return (
    <Space size={12} align="center">
      <div className="chrono-search">
        <SearchOutlined className="chrono-search-icon" />
        <Input
          placeholder="搜索课程、知识点或历史人物..."
          variant="borderless"
          allowClear
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onPressEnter={() => {
            const kw = q.trim();
            nav(kw ? `/courses?q=${encodeURIComponent(kw)}` : '/courses');
          }}
        />
      </div>
      <Badge dot>
        <BellOutlined
          style={{ color: 'var(--text-cream)', fontSize: 18, cursor: 'pointer' }}
          onClick={() => nav('/profile?tab=2')}
        />
      </Badge>
      <Avatar
        icon={<UserOutlined />}
        style={{ background: 'var(--accent-gold)', cursor: 'pointer' }}
        onClick={() => nav('/profile')}
      />
    </Space>
  );
}

function MessageBinder() {
  const { message } = AntdApp.useApp();
  useEffect(() => { bindMessage(message); }, [message]);
  return null;
}

export default function App() {
  const location = useLocation();
  return (
    <AntdApp>
      <MessageBinder />
      <Layout style={{ minHeight: '100vh', background: 'var(--bg-page)' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 24,
            padding: '0 24px',
            background: 'var(--bg-navy)',
            lineHeight: 'normal',
            height: 64,
          }}
        >
          <Logo />
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey(location.pathname)]}
            items={navItems}
            className="chrono-nav"
            style={{ flex: '0 1 auto', minWidth: 0, background: 'transparent', borderBottom: 'none', fontSize: 14 }}
          />
          <div style={{ flex: 1 }} />
          <UserSlot />
        </Header>
        <Content style={{ padding: '24px', background: 'var(--bg-page)' }}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/courses/:courseId" element={<CourseDetailPage />} />
            <Route path="/courses/:courseId/lessons/:lessonId" element={<LessonPage />} />
            <Route path="/learning" element={<LearningPage />} />
            <Route path="/practice" element={<PracticePage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>2
        <Footer style={{ textAlign: 'center', color: 'var(--text-disabled)', fontSize: 12, background: 'var(--bg-page)' }}>
          历史未来课堂 · Chronovita · v0.1.0 · 看 练 问 创 · 让历史可推演
        </Footer>
      </Layout>
    </AntdApp>
  );
}
