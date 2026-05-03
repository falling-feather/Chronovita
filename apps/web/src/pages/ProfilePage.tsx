import { useEffect, useState } from 'react';
import { toast } from '../utils/toast';
import { Avatar, Button, Input, Row, Col } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { loadJSON, saveJSON, removeKey } from '../utils/storage';

const menu = [
  { icon: '👤', label: '基本资料' },
  { icon: '🎨', label: '学习偏好' },
  { icon: '🔔', label: '通知与提醒' },
  { icon: '🔒', label: '隐私与数据' },
  { icon: '🛡', label: '账号安全' },
  { icon: '🚪', label: '退出登录', dim: true },
];

const grades = ['七年级', '八年级', '九年级'];

interface Profile {
  nickname: string;
  email: string;
  gradeIdx: number;
  bio: string;
}

const DEFAULT: Profile = { nickname: '未命名学徒', email: '', gradeIdx: 0, bio: '' };

export default function ProfilePage() {
  const [active, setActive] = useState(0);
  const [profile, setProfile] = useState<Profile>(DEFAULT);
  const [draft, setDraft] = useState<Profile>(DEFAULT);

  useEffect(() => {
    const loaded = loadJSON<Profile>('profile', DEFAULT);
    setProfile(loaded); setDraft(loaded);
  }, []);

  const dirty = JSON.stringify(profile) !== JSON.stringify(draft);

  const onSave = () => {
    saveJSON('profile', draft);
    setProfile(draft);
    toast.success('已保存');
  };

  const onCancel = () => {
    setDraft(profile);
  };

  const onLogout = () => {
    removeKey('profile');
    setProfile(DEFAULT); setDraft(DEFAULT);
    toast.warning('已清除本地资料（v0.1.0 暂未接入鉴权）');
  };

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <Row gutter={16}>
        <Col flex="280px">
          <div className="chrono-card" style={{ padding: 0 }}>
            <div style={{ padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <Avatar size={80} icon={<UserOutlined />} style={{ background: 'var(--accent-gold)' }} />
              <div className="chrono-title" style={{ fontSize: 16 }}>{profile.nickname || '未命名学徒'}</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 11 }}>本地存储 · 后端鉴权将在 v0.1.x 后续小版本接入</div>
              <Button shape="round"
                      onClick={() => toast.info('头像上传将在 v0.1.x 接入对象存储后开放')}
                      style={{ borderColor: 'var(--accent-gold)', color: 'var(--accent-gold)' }}>
                编辑头像
              </Button>
            </div>
            <div style={{ height: 1, background: 'var(--border-soft)' }} />
            <div style={{ padding: '12px 0' }}>
              {menu.map((m, i) => {
                const isActive = i === active;
                return (
                  <div key={m.label}
                       onClick={() => {
                         if (m.dim) { onLogout(); return; }
                         setActive(i);
                       }}
                       style={{
                         display: 'flex', alignItems: 'center', gap: 10,
                         padding: '10px 20px',
                         background: isActive ? 'var(--bg-tint)' : 'transparent',
                         color: isActive ? 'var(--accent-gold)' : (m.dim ? 'var(--text-disabled)' : 'var(--text-dark)'),
                         fontWeight: isActive ? 600 : 400,
                         cursor: 'pointer',
                         fontSize: 13,
                       }}>
                    <span>{m.icon}</span><span>{m.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Col>

        <Col flex="auto">
          <div className="chrono-card" style={{ padding: 32 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 24 }}>
              <h2 className="chrono-title" style={{ fontSize: 22, margin: 0 }}>{menu[active].label}</h2>
              <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>{active === 0 ? '本地保存' : '该子模块将在后续版本逐步开放'}</span>
            </div>

            {active === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>昵称</div>
                  <Input style={{ maxWidth: 480, background: 'var(--bg-warm-soft)' }}
                         value={draft.nickname}
                         onChange={(e) => setDraft({ ...draft, nickname: e.target.value })} />
                </div>

                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>邮箱</div>
                  <Input style={{ maxWidth: 480, background: 'var(--bg-warm-soft)' }}
                         placeholder="未绑定"
                         value={draft.email}
                         onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
                </div>

                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>年级 / 学段</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {grades.map((g, i) => (
                      <span key={g}
                            onClick={() => setDraft({ ...draft, gradeIdx: i })}
                            className={`chrono-chip${i === draft.gradeIdx ? ' active' : ''}`}>
                        {g}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>个性签名</div>
                  <Input.TextArea
                    rows={3}
                    style={{ maxWidth: 720, background: 'var(--bg-warm-soft)' }}
                    placeholder="以史为镜，可以知兴替……"
                    value={draft.bio}
                    onChange={(e) => setDraft({ ...draft, bio: e.target.value })}
                  />
                </div>

                <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                  <Button type="primary" disabled={!dirty} onClick={onSave}>保存修改</Button>
                  <Button disabled={!dirty} onClick={onCancel}>取消</Button>
                </div>
              </div>
            ) : (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-mute)' }}>
                <div style={{ fontSize: 14, marginBottom: 6 }}>「{menu[active].label}」即将开放</div>
                <div style={{ fontSize: 12, color: 'var(--text-disabled)' }}>当前版本仅开通基本资料；其余子模块按 Roadmap 推进。</div>
              </div>
            )}
          </div>
        </Col>
      </Row>
    </div>
  );
}
