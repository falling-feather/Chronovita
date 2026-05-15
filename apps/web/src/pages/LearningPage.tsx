import { useEffect, useMemo, useState } from 'react';
import { Avatar, Button, Progress, Row, Col, Tag, Empty } from 'antd';
import { UserOutlined, PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, type ProgressItem } from '../utils/api';

const tabs = ['进行中', '我的收藏', '学习记录', '我的笔记'];
const LAYER_LABEL: Record<string, string> = {
  watch: '看', practice: '练', ask: '问', create: '创',
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diff = (now - d.getTime()) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
    return d.toLocaleDateString('zh-CN');
  } catch { return iso; }
}

function progressPct(item: ProgressItem): number {
  const arr = [item.layers.watch, item.layers.practice, item.layers.ask, item.layers.create];
  return Math.round(arr.filter(Boolean).length * 25);
}

export default function LearningPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState(0);
  const [items, setItems] = useState<ProgressItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.progressList()
      .then((r) => setItems(r.items || []))
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => {
    const total = items.length;
    const done = items.filter((i) => progressPct(i) === 100).length;
    const inProgress = total - done;
    return [
      { v: String(inProgress), l: '进行中' },
      { v: String(done), l: '已完成' },
      { v: '0', l: '收藏' },
      { v: '—', l: '本周时长' },
    ];
  }, [items]);

  const continueItem = items[0];
  const showItems = items.slice(0, 6);

  return (
    <div style={{ maxWidth: 1392, margin: '0 auto' }}>
      <div className="chrono-card-warm" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Avatar size={56} icon={<UserOutlined />} style={{ background: 'var(--accent-gold)' }} />
          <div>
            <div className="chrono-title" style={{ fontSize: 22 }}>你好，未命名学徒</div>
            <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>
              {continueItem
                ? `上次学到：${continueItem.title ?? continueItem.lesson_id} · ${LAYER_LABEL[continueItem.last_layer] ?? continueItem.last_layer} 层`
                : '尚未开始任何课程，去课程中心挑一节吧'}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 32 }}>
          {stats.map((s) => (
            <div key={s.l} style={{ textAlign: 'center' }}>
              <div className="chrono-title" style={{ fontSize: 26, color: 'var(--accent-gold)' }}>{s.v}</div>
              <div style={{ fontSize: 11, color: 'var(--text-mute)' }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--border-soft)', marginBottom: 20 }}>
        {tabs.map((t, i) => (
          <div key={t}
               onClick={() => setTab(i)}
               style={{
                 padding: '10px 0',
                 borderBottom: i === tab ? '2px solid var(--accent-gold)' : '2px solid transparent',
                 color: i === tab ? 'var(--accent-gold)' : 'var(--text-mute)',
                 fontWeight: i === tab ? 600 : 400,
                 cursor: 'pointer',
                 fontSize: 14,
               }}>{t}</div>
        ))}
      </div>

      {tab === 0 && (
        <>
          {loading ? (
            <div className="chrono-empty">加载中…</div>
          ) : showItems.length === 0 ? (
            <Empty description={<span style={{ color: 'var(--text-mute)' }}>还没有学习记录，去开启第一节课吧</span>}>
              <Button type="primary" onClick={() => nav('/courses')}>去课程中心</Button>
            </Empty>
          ) : (
            <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
              {showItems.map((it) => {
                const pct = progressPct(it);
                return (
                  <Col span={12} key={it.lesson_id}>
                    <div className="chrono-card" style={{ padding: 0, overflow: 'hidden' }}>
                      <div style={{ display: 'flex' }}>
                        <div style={{ width: 160, background: 'var(--accent-bronze)' }} />
                        <div style={{ padding: 20, flex: 1 }}>
                          <div className="chrono-title" style={{ fontSize: 16 }}>
                            {it.title ?? it.lesson_id}
                          </div>
                          <div style={{ color: 'var(--text-mute)', fontSize: 12, margin: '6px 0 12px', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                            <span>上次：{LAYER_LABEL[it.last_layer] ?? it.last_layer} 层</span>
                            <span>·</span>
                            <span>{formatTime(it.updated_at)}</span>
                            <Tag color={pct === 100 ? 'gold' : 'default'} style={{ marginLeft: 4 }}>
                              {(['watch', 'practice', 'ask', 'create'] as const).map(
                                (k) => (it.layers[k] ? LAYER_LABEL[k] : '·')
                              ).join('')}
                            </Tag>
                          </div>
                          <Progress percent={pct} strokeColor="var(--accent-gold)" showInfo={false} />
                          <div style={{ fontSize: 11, color: 'var(--text-mute)', margin: '4px 0 14px' }}>
                            已完成 {pct}%（按四层任意进入计）
                          </div>
                          <Button type="primary" onClick={() => {
                            if (it.course_id) {
                              nav(`/courses/${it.course_id}/lessons/${it.lesson_id}?layer=${it.last_layer}`);
                            } else {
                              nav('/courses');
                            }
                          }}>
                            继续学习
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Col>
                );
              })}
              <Col span={12}>
                <div className="chrono-empty"
                     onClick={() => nav('/courses')}
                     style={{
                       display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                       minHeight: 200, border: '1px dashed var(--border-soft)', cursor: 'pointer',
                     }}>
                  <PlusOutlined style={{ fontSize: 28, color: 'var(--text-disabled)', marginBottom: 8 }} />
                  <div style={{ color: 'var(--text-mute)' }}>添加新课程</div>
                </div>
              </Col>
            </Row>
          )}
        </>
      )}

      {tab !== 0 && (
        <div className="chrono-empty">
          <div style={{ color: 'var(--text-disabled)', marginBottom: 4 }}>该子页将在 v0.9.x 接入</div>
          <div style={{ fontSize: 12 }}>详见 docs/Planning.md M6「我的学习面板深化」</div>
        </div>
      )}
    </div>
  );
}
