import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from '../utils/toast';
import { Button, Progress, Row, Col, Tag } from 'antd';
import { PlayCircleOutlined, CheckCircleFilled, LockFilled, RightOutlined } from '@ant-design/icons';

const chapters = [
  { num: '1.1', title: '上古传说 · 三皇五帝', state: 'done' as const },
  { num: '1.2', title: '黄河流域的早期文明', state: 'done' as const },
  { num: '1.3', title: '大禹治水的故事', state: 'active' as const },
  { num: '1.4', title: '夏朝的建立', state: 'lock' as const },
  { num: '1.5', title: '商周更替', state: 'lock' as const },
];

const keywords = [
  { word: '洪水', pinyin: 'hóng shuǐ', gloss: '上古时期席卷九州的水患' },
  { word: '肆虐', pinyin: 'sì nüè', gloss: '形容灾害无所约束地蔓延' },
  { word: '流离失所', pinyin: 'liú lí shī suǒ', gloss: '百姓被迫离开故土' },
  { word: '生灵涂炭', pinyin: 'shēng líng tú tàn', gloss: '形容百姓陷入极大的苦难' },
];

const related = [
  { tag: '人物', title: '大禹的传说与考古' },
  { tag: '地理', title: '九州山川考' },
  { tag: '制度', title: '从禅让到世袭' },
  { tag: '文物', title: '二里头遗址' },
  { tag: '典籍', title: '《尚书 · 禹贡》' },
];

const experts = ['李教授 · 历史系', '陈老师 · 考古所'];

export default function CoursesPage() {
  const [currentIdx, setCurrentIdx] = useState(2);
  const current = chapters[currentIdx];
  const [params] = useSearchParams();
  const q = params.get('q')?.trim() || '';

  const onChapterClick = (i: number) => {
    if (chapters[i].state === 'lock') {
      toast.warning(`${chapters[i].title} · 待解锁`);
      return;
    }
    setCurrentIdx(i);
  };

  return (
    <div style={{ maxWidth: 1536, margin: '0 auto' }}>
      {q && (
        <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--bg-tint)', border: '1px solid var(--border-soft)', borderRadius: 6, fontSize: 13 }}>
          搜索关键词：<b style={{ color: 'var(--accent-gold)' }}>{q}</b> · 当前展示「华夏文明的起源」示例课程；课程检索接口将在 v0.2.x 接入。
        </div>
      )}
      <div className="chrono-courses-grid">
        {/* 左 */}
        <div className="chrono-courses-side">
          <div className="chrono-card" style={{ marginBottom: 16, padding: 0, overflow: 'hidden' }}>
            <div style={{ height: 90, background: 'var(--accent-bronze)' }} />
            <div style={{ padding: 12 }}>
              <div className="chrono-title" style={{ fontSize: 14 }}>华夏文明的起源</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 11, margin: '6px 0' }}>七年级 · 历史上册</div>
              <Progress percent={42} strokeColor="var(--accent-gold)" showInfo={false} />
              <div style={{ fontSize: 11, color: 'var(--text-mute)', marginTop: 4 }}>学习进度 42%</div>
            </div>
          </div>
          <div className="chrono-card">
            <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>章节目录</div>
            {chapters.map((c, i) => {
              const icon =
                c.state === 'done' ? <CheckCircleFilled style={{ color: 'var(--accent-gold)' }} /> :
                i === currentIdx ? <PlayCircleOutlined style={{ color: 'var(--accent-gold)' }} /> :
                c.state === 'lock' ? <LockFilled style={{ color: 'var(--text-disabled)' }} /> :
                <PlayCircleOutlined style={{ color: 'var(--text-mute)' }} />;
              const active = i === currentIdx;
              return (
                <div
                  key={c.num}
                  onClick={() => onChapterClick(i)}
                  style={{
                    display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 6, alignItems: 'center',
                    background: active ? 'var(--bg-tint)' : 'transparent',
                    cursor: c.state === 'lock' ? 'not-allowed' : 'pointer',
                  }}
                >
                  {icon}
                  <span style={{ fontSize: 12, color: 'var(--text-mute)' }}>{c.num}</span>
                  <span style={{ fontSize: 13, color: c.state === 'lock' ? 'var(--text-disabled)' : 'var(--text-dark)' }}>{c.title}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 中 */}
        <div className="chrono-courses-main">
          <div className="chrono-card-dark" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ position: 'relative', aspectRatio: '16/9', background: '#000' }}>
              <Tag color="gold" style={{ position: 'absolute', top: 12, left: 12, zIndex: 2 }}>AI 生成 · 良渚文化</Tag>
              <iframe
                title="良渚文化主题短片「玉」的一天"
                src="https://player.bilibili.com/player.html?bvid=BV1jCpwz3Eir&page=1&high_quality=1&danmaku=0&autoplay=0"
                allowFullScreen
                scrolling="no"
                frameBorder="0"
                style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}
              />
            </div>
          </div>

          <div className="chrono-card" style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="chrono-title" style={{ fontSize: 18 }}>{current.num} {current.title}</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>03:42 · 已观看 0 次 · v0.1.0 占位</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button onClick={() => toast.info('专家解读切换功能将在 v0.5.x · 问层接入')}>切换专家解读</Button>
              <Button type="primary" onClick={() => toast.info('知识点卡片生成功能将在 v0.6.x · 创层接入')}>生成知识点卡片</Button>
            </div>
          </div>

          <Row gutter={8} style={{ marginTop: 12 }}>
            {chapters.map((c, i) => (
              <Col span={Math.floor(24 / chapters.length)} key={c.num}>
                <div
                  className="chrono-card"
                  onClick={() => onChapterClick(i)}
                  style={{
                    padding: 0, overflow: 'hidden',
                    cursor: c.state === 'lock' ? 'not-allowed' : 'pointer',
                    borderColor: i === currentIdx ? 'var(--accent-gold)' : 'var(--border-soft)',
                    boxShadow: i === currentIdx ? '0 0 0 2px var(--accent-gold)' : 'none',
                  }}
                >
                  <div style={{ height: 80, background: i === currentIdx ? 'var(--accent-bronze)' : 'var(--bg-warm)', position: 'relative' }}>
                    <span style={{
                      position: 'absolute', bottom: 4, right: 6, fontSize: 10,
                      color: '#fff', background: 'rgba(0,0,0,.55)', padding: '1px 6px', borderRadius: 3,
                    }}>0{i + 1}:00</span>
                  </div>
                  <div style={{ padding: '8px 10px' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-mute)' }}>第{i + 1}章</div>
                    <div style={{ fontSize: 12, marginTop: 2, color: c.state === 'lock' ? 'var(--text-disabled)' : 'var(--text-dark)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.title}</div>
                  </div>
                </div>
              </Col>
            ))}
          </Row>
        </div>

        {/* 右 */}
        <div className="chrono-courses-side">
          <div className="chrono-card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span className="chrono-title" style={{ fontSize: 14 }}>关键词汇</span>
              <a style={{ color: 'var(--accent-gold)', fontSize: 12 }} onClick={() => toast.info('词汇推荐将在 v0.3.x · 看层接入')}>换一批</a>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {keywords.map((k) => (
                <div className="chrono-keyword" key={k.word}>
                  <div className="pinyin">{k.pinyin}</div>
                  <div className="word">{k.word}</div>
                  <div className="gloss">{k.gloss}</div>
                </div>
              ))}
            </div>
            <Button type="primary" block style={{ marginTop: 14 }}
                    onClick={() => toast.info('知识点卡片生成功能将在 v0.6.x · 创层接入')}>
              生成知识点卡片 <RightOutlined />
            </Button>
          </div>

          <div className="chrono-card">
            <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>专家解读</div>
            {experts.map((e) => (
              <div key={e}
                   style={{ display: 'flex', gap: 10, padding: '8px 0', alignItems: 'center' }}>
                <div style={{ width: 36, height: 36, borderRadius: 18, background: 'var(--accent-bronze)' }} />
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-dark)' }}>{e.split(' · ')[0]}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-mute)' }}>{e.split(' · ')[1]}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 相关推荐 */}
      <div style={{ marginTop: 32 }}>
        <h3 className="chrono-title" style={{ fontSize: 18, marginBottom: 12 }}>相关推荐</h3>
        <Row gutter={12}>
          {related.map((r) => (
            <Col span={Math.floor(24 / related.length)} key={r.title}>
              <div className="chrono-card"
                   onClick={() => toast.info('该课程将在 v0.7.x · 内容填充阶段开放')}
                   style={{ padding: 0, overflow: 'hidden', cursor: 'pointer' }}>
                <div style={{ height: 90, background: 'var(--bg-warm)' }} />
                <div style={{ padding: 12 }}>
                  <Tag color="gold">{r.tag}</Tag>
                  <div style={{ fontSize: 12, color: 'var(--text-dark)', marginTop: 6 }}>{r.title}</div>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  );
}
