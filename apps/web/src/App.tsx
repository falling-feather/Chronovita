import { Layout, Menu } from 'antd';
import { Link, Route, Routes, Navigate, useLocation } from 'react-router-dom';
import HomePage from './pages/HomePage';
import RecallPage from './pages/RecallPage';
import SandboxPage from './pages/SandboxPage';
import AgentPage from './pages/AgentPage';
import CanvasPage from './pages/CanvasPage';

const { Header, Content, Footer } = Layout;

const navItems = [
  { key: '/', label: <Link to="/">首页</Link> },
  { key: '/recall', label: <Link to="/recall">看 · 沉浸叙事</Link> },
  { key: '/sandbox', label: <Link to="/sandbox">练 · 沙盘推演</Link> },
  { key: '/agent', label: <Link to="/agent">问 · 双模智者</Link> },
  { key: '/canvas', label: <Link to="/canvas">创 · 知识谱系</Link> },
];

export default function App() {
  const location = useLocation();
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div className="chrono-title" style={{ color: '#F3EBDD', fontSize: 20, marginRight: 48 }}>
          史脉 · 未来课堂
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navItems}
          style={{ flex: 1, minWidth: 0, background: 'transparent' }}
        />
      </Header>
      <Content style={{ padding: '32px 48px' }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/recall" element={<RecallPage />} />
          <Route path="/sandbox" element={<SandboxPage />} />
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/canvas" element={<CanvasPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
      <Footer style={{ textAlign: 'center', background: 'transparent' }}>
        史脉 Chronovita · 看 练 问 创 · 让历史可推演
      </Footer>
    </Layout>
  );
}
