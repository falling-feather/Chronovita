import { useEffect, useState } from 'react';
import { Alert, Button, Collapse, Tag } from 'antd';
import {
  BookOutlined,
  EnvironmentOutlined,
  FileTextOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { Lesson, LessonPresentationResponse } from '../../utils/api';
import { parseContentBlock, renderContentMarkup } from '../../utils/contentMarkup';

function renderBodyBlock(paragraph: string, index: number) {
  const block = parseContentBlock(paragraph);
  const content = renderContentMarkup(block.text);
  if (block.level === 1) return <h2 key={index}>{content}</h2>;
  if (block.level === 2) return <h3 key={index}>{content}</h3>;
  if (block.level > 2) return <h4 key={index}>{content}</h4>;
  return <p key={index}>{renderContentMarkup(paragraph)}</p>;
}

export default function LessonWatch({
  lesson,
  presentation = null,
}: {
  lesson: Lesson;
  presentation?: LessonPresentationResponse | null;
}) {
  const [transcript, setTranscript] = useState('');
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const people: NonNullable<Lesson['people']> = lesson.people?.length
    ? lesson.people
    : lesson.figures.map((name) => ({ name }));

  useEffect(() => {
    setTranscript('');
  }, [lesson.id]);

  const loadTranscript = async () => {
    if (!presentation || transcript || transcriptLoading) return;
    setTranscriptLoading(true);
    try {
      const response = await fetch(presentation.asset_urls.transcript, { credentials: 'include' });
      if (!response.ok) throw new Error('文字稿载入失败');
      setTranscript(await response.text());
    } catch (error) {
      setTranscript(error instanceof Error ? error.message : '文字稿载入失败');
    } finally {
      setTranscriptLoading(false);
    }
  };

  return (
    <div className="chrono-observe-layout">
      <section className="chrono-observe-main">
        {presentation ? (
          <div className="chrono-local-video">
            <video
              controls
              preload="metadata"
              poster={presentation.asset_urls.poster}
              aria-label={presentation.presentation.title}
            >
              <source src={presentation.asset_urls.video} type="video/mp4" />
              当前浏览器无法播放本地课堂短片，请查看文字稿。
            </video>
            <div className="chrono-video-meta">
              <div>
                <Tag icon={<PlayCircleOutlined />} color="gold">课堂短片</Tag>
                <strong>{presentation.presentation.title}</strong>
                <span>{Math.round(presentation.presentation.video_duration_seconds)} 秒 · 可随时跳过</span>
              </div>
              <Button icon={<FileTextOutlined />} loading={transcriptLoading} onClick={() => void loadTranscript()}>
                {transcript ? '收起 / 展开文字稿' : '读取文字稿'}
              </Button>
            </div>
            {transcript ? (
              <Collapse
                className="chrono-transcript"
                defaultActiveKey={['transcript']}
                items={[{
                  key: 'transcript',
                  label: '可访问文字稿',
                  children: <pre>{transcript}</pre>,
                }]}
              />
            ) : null}
            <p className="chrono-accessibility-note">
              <PauseCircleOutlined /> {presentation.presentation.accessibility_note}
            </p>
          </div>
        ) : (
          <Alert
            type="info"
            showIcon
            message="本课暂无发布短片"
            description="你仍可阅读正式课文与资料卡，不影响后续兼容学习流程。"
          />
        )}

        <article className="chrono-lesson-reading">
          <header>
            <div>
              <span>叙事性正文</span>
              <h2>{lesson.title}</h2>
            </div>
            <div>
              {lesson.content_status === 'sealed' ? <Tag color="green">正式封存 v{lesson.content_version ?? 1}</Tag> : null}
              {lesson.release_no ? <Tag>发布 #{lesson.release_no}</Tag> : null}
            </div>
          </header>
          <div className="chrono-evidence-layers">
            {['传说叙事', '传世文献', '考古判断', '教学解释'].map((label, index) => (
              <span key={label}><i>{index + 1}</i>{label}</span>
            ))}
          </div>
          <div className="chrono-reading-body chrono-serif">
            {lesson.body.map(renderBodyBlock)}
          </div>
        </article>
      </section>

      <aside className="chrono-observe-aside">
        <section>
          <h3><EnvironmentOutlined /> 踏勘点</h3>
          {(lesson.map_points ?? []).map((point, index) => (
            <article key={`${point.label}-${point.region}`}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div><strong>{point.label}</strong><small>{point.region}</small><p>{point.note}</p></div>
            </article>
          ))}
        </section>
        <section>
          <h3><TeamOutlined /> 人物与群体</h3>
          {people.map((person) => (
            <article className="chrono-observe-person" key={person.name}>
              <div><strong>{person.name}</strong><small>{person.role}</small></div>
              <p>{person.summary || person.persona}</p>
            </article>
          ))}
        </section>
        <section>
          <h3><BookOutlined /> 可复核来源</h3>
          {(lesson.source_refs ?? []).slice(0, 6).map((source) => (
            <article className="chrono-observe-source" key={`${source.title}-${source.source}`}>
              <strong>{source.title}</strong>
              <span>{source.source}</span>
              <p>{source.citation_note}</p>
            </article>
          ))}
          {(lesson.source_refs?.length ?? 0) > 6 ? <Tag>另有 {(lesson.source_refs?.length ?? 0) - 6} 项来源收入课程</Tag> : null}
        </section>
        {presentation ? (
          <div className="chrono-observe-integrity">
            <SafetyCertificateOutlined />
            <span>展示资源与当前发布 checksum 精确绑定</span>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
