import { useState } from 'react';
import { Button, Space } from 'antd';
import { SoundOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { toast } from '../../utils/toast';

export default function LessonWatch({ lesson }: { lesson: Lesson }) {
  const [expert, setExpert] = useState<'A' | 'B'>('A');
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 280px', gap: 20 }}>
      <div>
        {/* 视频占位 */}
        <div className="chrono-card-dark" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
          <div style={{ position: 'relative', aspectRatio: '16/9', background: '#000',
                        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: 'var(--text-cream)', textAlign: 'center' }}>
              <div style={{ fontSize: 36, color: 'var(--accent-gold)' }}>▶</div>
              <div style={{ fontSize: 13, marginTop: 8 }}>AI 视频生成中</div>
              <div style={{ fontSize: 11, color: 'var(--text-cream-mute)' }}>当前为占位 · 真实视频将在后续版本接入</div>
            </div>
          </div>
        </div>

        <div className="chrono-card">
          <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="chrono-title" style={{ fontSize: 18 }}>{lesson.num} {lesson.title}</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>时长 {lesson.duration}</div>
            </div>
            <Space>
              <Button size="small" type={expert === 'A' ? 'primary' : 'default'} onClick={() => setExpert('A')}>李教授解读</Button>
              <Button size="small" type={expert === 'B' ? 'primary' : 'default'} onClick={() => setExpert('B')}>陈老师解读</Button>
            </Space>
          </div>
          <div style={{ background: 'var(--bg-warm-soft)', padding: 14, borderRadius: 6, fontSize: 13,
                        color: 'var(--text-dark)', marginBottom: 16, lineHeight: 1.7 }}>
            <SoundOutlined style={{ color: 'var(--accent-gold)', marginRight: 8 }} />
            {lesson.abstract}
          </div>
          <div className="chrono-serif" style={{ fontSize: 15, color: 'var(--text-dark)', lineHeight: 2 }}>
            {lesson.body.map((p, i) => (
              <p key={i} style={{ marginBottom: 14, textIndent: '2em' }}>{p}</p>
            ))}
          </div>
        </div>
      </div>

      {/* 右侧关键词 + 人物 */}
      <div>
        <div className="chrono-card" style={{ marginBottom: 16 }}>
          <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>关键词汇</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {lesson.keywords.map((k) => (
              <div className="chrono-keyword" key={k.word}>
                <div className="pinyin">{k.pinyin}</div>
                <div className="word">{k.word}</div>
                <div className="gloss">{k.gloss}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="chrono-card">
          <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>本节人物</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {lesson.figures.map((f) => (
              <span key={f} className="chrono-chip"
                    onClick={() => toast.info(`「${f}」人物档案将在后续版本接入`)}>{f}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
