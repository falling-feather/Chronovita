import { useState } from 'react';
import { Button, Space, Tag } from 'antd';
import { LinkOutlined, PlayCircleOutlined, SoundOutlined } from '@ant-design/icons';
import type { Lesson } from '../../utils/api';
import { parseContentBlock, renderContentMarkup } from '../../utils/contentMarkup';
import { toast } from '../../utils/toast';
import { BILIBILI_PLACEHOLDER, uiAssets } from '../p0Route';

function renderBodyBlock(paragraph: string, index: number) {
  const block = parseContentBlock(paragraph);
  if (block.level > 0) {
    const headingStyle = {
      margin: block.level === 1 ? '20px 0 10px' : '18px 0 8px',
      color: 'var(--text-dark)',
      lineHeight: 1.45,
      fontSize: block.level === 1 ? 22 : block.level === 2 ? 19 : 17,
    };
    const content = renderContentMarkup(block.text);
    if (block.level === 1) return <h2 key={index} style={headingStyle}>{content}</h2>;
    if (block.level === 2) return <h3 key={index} style={headingStyle}>{content}</h3>;
    return <h4 key={index} style={headingStyle}>{content}</h4>;
  }
  return <p key={index} style={{ marginBottom: 14, textIndent: '2em' }}>{renderContentMarkup(paragraph)}</p>;
}

export default function LessonWatch({ lesson }: { lesson: Lesson }) {
  const [expert, setExpert] = useState<'A' | 'B'>('A');
  const people = (lesson.people?.length
    ? lesson.people
    : lesson.figures.map((name) => ({ name }))) as NonNullable<Lesson['people']>;
  const mapPoints = lesson.map_points ?? [];
  const sourceRefs = lesson.source_refs ?? [];
  const factItems = lesson.facts ?? [];
  const qaItems = lesson.qa_points ?? [];
  const goalItems = lesson.level_goals ?? [];
  const hasAiSeeds = factItems.length > 0 || qaItems.length > 0 || goalItems.length > 0 || lesson.saga_material?.objective || lesson.sandbox_material?.objective;
  return (
    <div className="chrono-lesson-grid">
      <div>
        <div className="chrono-card-dark" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
          <div
            className="chrono-video-shell"
            style={{ backgroundImage: `linear-gradient(135deg, rgba(7,27,47,.58), rgba(46,111,113,.36)), url(${uiAssets.liangzhuCover})` }}
          >
            <iframe
              title={BILIBILI_PLACEHOLDER.title}
              src={BILIBILI_PLACEHOLDER.embedUrl}
              allow="fullscreen; autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
            <div className="chrono-video-badge">
              <Tag color="gold" icon={<PlayCircleOutlined />}>视频占位</Tag>
              <span>{BILIBILI_PLACEHOLDER.title}</span>
              <Button
                size="small"
                type="link"
                icon={<LinkOutlined />}
                href={BILIBILI_PLACEHOLDER.url}
                target="_blank"
                rel="noreferrer"
              >
                原链接
              </Button>
            </div>
          </div>
        </div>

        <div className="chrono-card">
          <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="chrono-title" style={{ fontSize: 18 }}>{lesson.num} {lesson.title}</div>
              <div style={{ color: 'var(--text-mute)', fontSize: 12, marginTop: 4 }}>
                时长 {lesson.duration}
                {lesson.unit && ` · ${lesson.unit}`}
                {lesson.era && ` · ${lesson.era}`}
              </div>
            </div>
            <Space>
              <Button size="small" type={expert === 'A' ? 'primary' : 'default'} onClick={() => setExpert('A')}>李教授解读</Button>
              <Button size="small" type={expert === 'B' ? 'primary' : 'default'} onClick={() => setExpert('B')}>陈老师解读</Button>
            </Space>
          </div>
          <div style={{ background: 'var(--bg-warm-soft)', border: '1px solid var(--border-soft)', padding: 14, borderRadius: 6, fontSize: 13,
                        color: 'var(--text-dark)', marginBottom: 16, lineHeight: 1.7 }}>
            <SoundOutlined style={{ color: 'var(--accent-gold)', marginRight: 8 }} />
            {lesson.abstract}
            {lesson.content_status === 'sealed' && (
              <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Tag color="green">封存 v{lesson.content_version ?? 1}</Tag>
                {lesson.sealed_by && <Tag>封存人 {lesson.sealed_by}</Tag>}
              </div>
            )}
          </div>
          <div className="chrono-serif" style={{ fontSize: 15, color: 'var(--text-dark)', lineHeight: 2 }}>
            {lesson.body.map(renderBodyBlock)}
          </div>
        </div>
      </div>

      {/* 右侧关键词 + 人物 */}
      <aside>
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

        <div className="chrono-card" style={{ marginBottom: 16 }}>
          <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>本节人物</div>
          {people.length === 0 ? (
            <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>暂无人物卡</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {people.map((p) => (
                <div key={p.name} style={{ border: '1px solid var(--border-soft)', borderRadius: 6, padding: 10, background: 'var(--bg-warm-soft)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <strong>{p.name}</strong>
                    {p.role && <Tag color="blue">{p.role}</Tag>}
                  </div>
                  {p.summary ? (
                    <div style={{ color: 'var(--text-mute)', fontSize: 12, lineHeight: 1.7, marginTop: 6 }}>{p.summary}</div>
                  ) : (
                    <span className="chrono-chip" onClick={() => toast.info(`「${p.name}」人物档案将在后续版本接入`)}>{p.name}</span>
                  )}
                  {p.persona && <div style={{ color: 'var(--text-dark)', fontSize: 12, lineHeight: 1.7, marginTop: 6 }}>同窗设定：{p.persona}</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        {mapPoints.length > 0 && (
          <div className="chrono-card" style={{ marginBottom: 16 }}>
            <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>地图点</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {mapPoints.map((point) => (
                <div key={`${point.label}-${point.region}`} style={{ fontSize: 12, lineHeight: 1.7 }}>
                  <strong>{point.label}</strong>
                  {point.region && <span style={{ color: 'var(--text-mute)' }}> · {point.region}</span>}
                  {point.note && <div style={{ color: 'var(--text-mute)' }}>{point.note}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {sourceRefs.length > 0 && (
          <div className="chrono-card" style={{ marginBottom: 16 }}>
            <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>参考资料</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sourceRefs.map((ref) => (
                <div key={`${ref.title}-${ref.source}`} style={{ fontSize: 12, lineHeight: 1.7 }}>
                  <strong>{ref.title}</strong>
                  {ref.source && <div style={{ color: 'var(--text-mute)' }}>{ref.source}</div>}
                  {ref.citation_note && <div style={{ color: 'var(--text-mute)' }}>{ref.citation_note}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {hasAiSeeds && (
          <div className="chrono-card">
            <div className="chrono-title" style={{ fontSize: 14, marginBottom: 12 }}>AI 预留素材</div>
            <Space size={[6, 6]} wrap>
              {factItems.slice(0, 4).map((item) => <Tag key={item} color="gold">史实</Tag>)}
              {qaItems.slice(0, 3).map((item) => <Tag key={item} color="purple">问答</Tag>)}
              {goalItems.slice(0, 3).map((item) => <Tag key={item} color="green">关卡</Tag>)}
              {lesson.saga_material?.objective && <Tag color="blue">saga</Tag>}
              {lesson.sandbox_material?.objective && <Tag color="cyan">sandbox</Tag>}
            </Space>
            {factItems[0] && <div style={{ color: 'var(--text-mute)', fontSize: 12, lineHeight: 1.7, marginTop: 10 }}>{factItems[0]}</div>}
          </div>
        )}
      </aside>
    </div>
  );
}
