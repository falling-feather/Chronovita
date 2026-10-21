import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App as AntdApp, Alert, Avatar, Button, Input, Radio, Select, Spin } from 'antd';
import { DownloadOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '../auth/AuthContext';
import { authApi } from '../auth/client';
import { api, ApiError, type AccountProfile } from '../utils/api';
import { toast } from '../utils/toast';
import './ProfilePage.css';

type Section = 'basic' | 'reading' | 'security';
const tabs: { key: Section; label: string }[] = [
  { key: 'basic', label: '个人资料' }, { key: 'reading', label: '阅读偏好' },
  { key: 'security', label: '账号与数据' },
];
const message = (error: unknown) => error instanceof TypeError
  ? '网络连接失败，请检查本地课堂服务并重试。'
  : error instanceof ApiError && error.code === 'auth_rate_limited'
    ? '操作过于频繁，请稍后重试。'
    : error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : '请求失败，请稍后重试。';

export default function ProfilePage() {
  const auth = useAuth();
  const { modal } = AntdApp.useApp();
  const nav = useNavigate();
  const [active, setActive] = useState<Section>('basic');
  const [saved, setSaved] = useState<AccountProfile | null>(null);
  const [draft, setDraft] = useState<AccountProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [passwords, setPasswords] = useState({ current: '', next: '', repeat: '' });
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    let activeRequest = true;
    if (auth.mode !== 'accounts') { setLoading(false); return; }
    setLoading(true); setError('');
    api.profile().then((value) => {
      if (!activeRequest) return;
      setSaved(value); setDraft(value);
    }).catch((failure) => { if (activeRequest) setError(message(failure)); })
      .finally(() => { if (activeRequest) setLoading(false); });
    return () => { activeRequest = false; };
  }, [auth.mode, auth.principal?.user_id, retry]);

  const dirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const save = async () => {
    if (!draft || !saved || saving) return;
    setSaving(true); setError('');
    try {
      const updated = await api.saveProfile({
        display_name: draft.display_name, email: draft.email, grade: draft.grade,
        bio: draft.bio, avatar_data_url: draft.avatar_data_url,
        reading_size: draft.reading_size, expected_revision: saved.revision,
        expected_user_id: draft.user_id,
      });
      setSaved(updated); setDraft(updated); auth.applyProfile(updated);
      toast.success('资料已保存到当前账号');
    } catch (failure) { setError(message(failure)); }
    finally { setSaving(false); }
  };

  const chooseAvatar = async (file?: File) => {
    if (!file) return;
    if (file.size > 1024 * 1024 || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setError('请选择不超过 1 MB 的 PNG、JPEG 或 WebP 图片'); return;
    }
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('图片读取失败'));
        reader.readAsDataURL(file);
      });
      setDraft((current) => current ? { ...current, avatar_data_url: data } : current);
      setError('');
    } catch (failure) { setError(message(failure)); }
  };

  const logout = async () => {
    try { await auth.logout(); nav('/login', { replace: true }); }
    catch { setError('退出请求未完成，账号仍可能在线。请恢复网络后重试。'); }
  };

  const changePassword = async () => {
    if (passwords.next !== passwords.repeat) { setError('两次新密码不一致'); return; }
    setChanging(true); setError('');
    try {
      if (!draft) return;
      await api.changeOwnPassword(passwords.current, passwords.next, draft.user_id);
      setPasswords({ current: '', next: '', repeat: '' });
      auth.invalidate(); toast.success('密码已修改，所有会话已退出，请重新登录');
      nav('/login', { replace: true });
    } catch (failure) { setError(message(failure)); }
    finally { setChanging(false); }
  };

  const exportProfile = () => {
    if (!saved) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(saved, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url; link.download = 'Chronovita-个人资料.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  if (auth.mode !== 'accounts') return <Alert type="info" showIcon message="个人资料需要使用真实账号"
    description="本地兼容模式不冒充个人账号，也不会读取旧版共用的浏览器资料。" />;
  if (loading) return <div className="chrono-page-loading"><Spin /><span>正在读取个人资料…</span></div>;
  if (draft && draft.user_id !== auth.principal?.user_id) return <Alert type="warning" showIcon
    message="登录身份已变化，请重新载入。"
    action={<Button onClick={() => void auth.restore()}>重新载入</Button>} />;
  if (!draft) return <Alert type="error" showIcon message={error || '资料暂不可用'}
    action={<Button onClick={() => setRetry((value) => value + 1)}>重试</Button>} />;

  return <div className="chrono-profile-page">
    <aside className="chrono-card chrono-profile-nav">
      <Avatar size={80} src={draft.avatar_data_url || undefined} icon={<UserOutlined />} />
      <h1>{saved?.display_name}</h1><p>@{saved?.username}</p>
      <nav aria-label="个人中心功能">{tabs.map((tab) =>
        <button key={tab.key} aria-current={active === tab.key ? 'page' : undefined}
          onClick={() => { setActive(tab.key); setError(''); }}>{tab.label}</button>)}</nav>
      <Button aria-label="退出登录" icon={<LogoutOutlined aria-hidden />} onClick={() => {
        if (!dirty) { void logout(); return; }
        modal.confirm({ title: '有未保存资料，仍要退出吗？', onOk: logout, okText: '退出', cancelText: '继续编辑' });
      }}>退出登录</Button>
    </aside>
    <main className="chrono-card chrono-profile-main">
      <h2>{tabs.find((tab) => tab.key === active)?.label}</h2>
      {error ? <Alert type="error" showIcon message={error}
        action={<Button onClick={() => modal.confirm({ title: '重新载入会丢弃未保存修改，是否继续？',
          onOk: () => setRetry((value) => value + 1), okText: '重新载入', cancelText: '取消' })}>重新载入</Button>} /> : null}
      {active !== 'security' ? <form onSubmit={(event) => { event.preventDefault(); void save(); }}>
        {active === 'basic' ? <>
          <label htmlFor="profile-avatar">头像</label>
          <input id="profile-avatar" type="file" accept="image/png,image/jpeg,image/webp"
            onChange={(event) => { void chooseAvatar(event.target.files?.[0]); event.target.value = ''; }} />
          <small>图片仅用于个人头像，最大 1 MB；保存时去除元数据并缩小尺寸。</small>
          {draft.avatar_data_url ? <Button onClick={() => setDraft({ ...draft, avatar_data_url: '' })}>移除头像</Button> : null}
          <label htmlFor="profile-name">昵称</label>
          <Input id="profile-name" required maxLength={80} value={draft.display_name}
            onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} />
          <label htmlFor="profile-email">联系邮箱（可选）</label>
          <Input id="profile-email" type="email" maxLength={254} value={draft.email}
            onChange={(event) => setDraft({ ...draft, email: event.target.value })} />
          <small>仅保存联系方式，尚未验证，不用于密码找回或发送邮件。</small>
          <label htmlFor="profile-grade">年级</label>
          <Select id="profile-grade" aria-label="年级" value={draft.grade}
            options={['', '七年级', '八年级', '九年级'].map((value) => ({ value, label: value || '未设置' }))}
            onChange={(grade) => setDraft({ ...draft, grade })} />
          <label htmlFor="profile-bio">个性签名</label>
          <Input.TextArea id="profile-bio" value={draft.bio} maxLength={300} showCount rows={4}
            onChange={(event) => setDraft({ ...draft, bio: event.target.value })} />
        </> : <>
          <label>课文正文字号</label>
          <Radio.Group aria-label="课文正文字号" value={draft.reading_size}
            onChange={(event) => setDraft({ ...draft, reading_size: event.target.value })}>
            <Radio.Button value="standard">标准</Radio.Button><Radio.Button value="large">大字</Radio.Button>
          </Radio.Group>
          <p>保存后在课文阅读页生效，跟随当前账号；动画已遵循系统的“减少动态效果”设置。</p>
        </>}
        <div className="chrono-profile-actions">
          <Button htmlType="submit" type="primary" loading={saving} disabled={!dirty}>保存修改</Button>
          <Button disabled={!dirty || saving} onClick={() => { setDraft(saved); setRetry((value) => value + 1); }}>取消修改</Button>
          <span role="status">{dirty ? '有未保存修改' : '与账号资料一致'}</span>
        </div>
      </form> : <>
        <form onSubmit={(event) => { event.preventDefault(); void changePassword(); }}>
          <label htmlFor="profile-current-password">当前密码</label>
          <Input.Password id="profile-current-password" required autoComplete="current-password" value={passwords.current}
            onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} />
          <label htmlFor="profile-new-password">新密码</label>
          <Input.Password id="profile-new-password" required minLength={12} maxLength={256} autoComplete="new-password"
            value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} />
          <label htmlFor="profile-repeat-password">确认新密码</label>
          <Input.Password id="profile-repeat-password" required minLength={12} autoComplete="new-password"
            value={passwords.repeat} onChange={(event) => setPasswords({ ...passwords, repeat: event.target.value })} />
          <small>至少 12 个字符；修改后全部设备需重新登录。</small>
          <Button htmlType="submit" type="primary" loading={changing}>修改密码并退出</Button>
        </form>
        <section className="chrono-profile-data">
          <h3>资料与学习数据</h3>
          <p>个人资料保存在当前课堂服务；私人学习草稿保存在所用浏览器，只有明确提交后教师才能查看。</p>
          <Button icon={<DownloadOutlined />} onClick={exportProfile}>导出个人资料</Button>
          {auth.principal?.roles.includes('student') ? <Button onClick={() => nav('/learning?tab=submissions')}>查看成果与教师反馈</Button> : null}
          <Button danger onClick={() => modal.confirm({
            title: '退出所有设备？', content: '当前页面也会退出，学习数据和资料不会删除。',
            okText: '确认退出', cancelText: '取消', onOk: async () => {
              try { await authApi.revokeOwnSessions(); auth.invalidate(); nav('/login', { replace: true }); }
              catch (failure) { setError(message(failure)); throw failure; }
            },
          })}>退出所有设备</Button>
        </section>
      </>}
    </main>
  </div>;
}
