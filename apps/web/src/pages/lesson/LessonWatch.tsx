import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert, Button } from 'antd';
import {
  BulbOutlined,
  EnvironmentOutlined,
  FileTextOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReadOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { Keyword, Lesson, LessonPresentationResponse } from '../../utils/api';
import { parseContentBlock, parseContentMarkup, type InlineMark } from '../../utils/contentMarkup';
import { emitLearningEvent } from '../../features/classroom/learningLedger';
import { normalizeReadingKeywords, splitReadingText } from './lessonReadingModel';

const READING_LENSES = [
  { index: '壹', title: '传说记忆', note: '先问故事由谁、在何时讲述' },
  { index: '贰', title: '传世文献', note: '辨认成书、编定与流传年代' },
  { index: '叁', title: '考古观察', note: '只从遗物与遗迹推出可支持的判断' },
  { index: '肆', title: '课堂解释', note: '把现代分析与古代材料分开' },
] as const;

const MARK_CLASS: Record<InlineMark, string> = {
  bold: 'is-bold',
  highlight: 'is-highlighted',
  keyword: 'is-keyword-mark',
  red: 'is-red',
  blue: 'is-blue',
  gold: 'is-gold',
  large: 'is-large',
  small: 'is-small',
};

function renderInteractiveMarkup(
  value: string,
  keywords: Keyword[],
  keywordNumbers: Map<string, number>,
  selectedWord: string,
  onKeywordSelect: (keyword: Keyword) => void,
): ReactNode[] {
  return parseContentMarkup(value).map((segment, segmentIndex) => (
    <span
      className={segment.marks.map((mark) => MARK_CLASS[mark]).join(' ')}
      key={`${segmentIndex}-${segment.text.slice(0, 18)}`}
    >
      {splitReadingText(segment.text, keywords).map((token, tokenIndex) => (
        token.keyword ? (
          <button
            className={`chrono-reading-keyword${selectedWord === token.keyword.word ? ' active' : ''}`}
            type="button"
            aria-pressed={selectedWord === token.keyword.word}
            aria-controls="chrono-knowledge-note"
            onClick={() => onKeywordSelect(token.keyword as Keyword)}
            key={`${token.keyword.word}-${tokenIndex}`}
          >
            <span>{token.text}</span>
            <sup>{keywordNumbers.get(token.keyword.word)}</sup>
          </button>
        ) : <span key={`${token.text}-${tokenIndex}`}>{token.text}</span>
      ))}
    </span>
  ));
}

function renderBodyBlock(
  paragraph: string,
  index: number,
  keywords: Keyword[],
  keywordNumbers: Map<string, number>,
  selectedWord: string,
  onKeywordSelect: (keyword: Keyword) => void,
) {
  const block = parseContentBlock(paragraph);
  const content = renderInteractiveMarkup(block.text, keywords, keywordNumbers, selectedWord, onKeywordSelect);
  if (block.level === 1) return <h2 key={index}>{content}</h2>;
  if (block.level === 2) return <h3 key={index}>{content}</h3>;
  if (block.level > 2) return <h4 key={index}>{content}</h4>;
  return <p key={index}>{content}</p>;
}

export function LessonWatchMedia({
  lesson,
  presentation = null,
}: {
  lesson: Lesson;
  presentation?: LessonPresentationResponse | null;
}) {
  const [transcript, setTranscript] = useState('');
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState('');

  useEffect(() => {
    setTranscript('');
    setTranscriptOpen(false);
    setTranscriptError('');
  }, [lesson.id, presentation?.presentation.checksum]);

  const toggleTranscript = async () => {
    if (!presentation || transcriptLoading) return;
    if (transcript) {
      setTranscriptOpen((current) => !current);
      return;
    }

    setTranscriptLoading(true);
    setTranscriptError('');
    try {
      const response = await fetch(presentation.asset_urls.transcript, { credentials: 'include' });
      if (!response.ok) throw new Error('文字稿暂时无法载入，请稍后重试。');
      setTranscript(await response.text());
      setTranscriptOpen(true);
    } catch (error) {
      setTranscriptError(error instanceof Error ? error.message : '文字稿暂时无法载入，请稍后重试。');
    } finally {
      setTranscriptLoading(false);
    }
  };

  if (!presentation) {
    return (
      <section className="chrono-observe-cinema is-empty">
        <Alert
          type="info"
          showIcon
          message="本课暂未配备导读短片"
          description="课文、关键词与后续课堂仍可正常学习。"
        />
      </section>
    );
  }

  return (
    <section className="chrono-observe-cinema" aria-labelledby={`cinema-${lesson.id}`}>
      <header>
        <div>
          <span>卷首导读 · {Math.round(presentation.presentation.video_duration_seconds)} 秒</span>
          <h2 id={`cinema-${lesson.id}`}>{presentation.presentation.title}</h2>
        </div>
        <p>先看时代留下的问题，再进入课文寻找证据。</p>
      </header>

      <div className="chrono-cinema-screen">
        <span className="chrono-cinema-seal" aria-hidden="true">观</span>
        <video
          controls
          preload="metadata"
          poster={presentation.asset_urls.poster}
          aria-label={presentation.presentation.title}
        >
          <source src={presentation.asset_urls.video} type="video/mp4" />
          当前浏览器无法播放本地课堂短片，请打开下方文字稿。
        </video>
      </div>

      <footer>
        <div>
          <PlayCircleOutlined />
          <span>本地课堂短片，可暂停、拖动或直接跳过</span>
        </div>
        <Button
          icon={<FileTextOutlined />}
          loading={transcriptLoading}
          onClick={() => void toggleTranscript()}
          aria-expanded={transcriptOpen}
          aria-controls={`transcript-${lesson.id}`}
        >
          {transcriptOpen ? '收起文字稿' : '阅读文字稿'}
        </Button>
      </footer>

      {transcriptError ? <Alert className="chrono-transcript-error" type="warning" showIcon message={transcriptError} /> : null}
      {transcriptOpen ? (
        <section className="chrono-cinema-transcript" id={`transcript-${lesson.id}`}>
          <header><ReadOutlined /><strong>无障碍文字稿</strong></header>
          <pre>{transcript}</pre>
          <p><PauseCircleOutlined /> {presentation.presentation.accessibility_note}</p>
        </section>
      ) : null}
    </section>
  );
}

export default function LessonWatch({ lesson }: { lesson: Lesson }) {
  const keywords = useMemo(() => normalizeReadingKeywords(lesson.keywords ?? []), [lesson.keywords]);
  const [selectedWord, setSelectedWord] = useState('');
  const selectedKeyword = keywords.find((keyword) => keyword.word === selectedWord) ?? null;
  const keywordNumbers = useMemo(
    () => new Map((lesson.keywords ?? []).map((keyword, index) => [keyword.word.trim(), index + 1])),
    [lesson.keywords],
  );
  const people: NonNullable<Lesson['people']> = lesson.people?.length
    ? lesson.people
    : lesson.figures.map((name) => ({ name }));

  useEffect(() => {
    setSelectedWord('');
  }, [lesson.id]);

  const selectKeyword = (keyword: Keyword) => {
    setSelectedWord(keyword.word);
    if (selectedWord === keyword.word) return;
    emitLearningEvent({
      course_id: lesson.course_id,
      lesson_id: lesson.id,
      kind: 'keyword_opened',
      title: `展开词条：${keyword.word}`,
      summary: keyword.gloss,
      metadata: { keyword: keyword.word },
    });
  };

  return (
    <div className="chrono-observe-reading-layout">
      <article className="chrono-lesson-reading chrono-reading-folio">
        <header>
          <div>
            <span>史卷正文 · 随读批注</span>
            <h2>{lesson.title}</h2>
            <p>点击朱砂色词语，右侧便签才会展开解释。</p>
          </div>
          <div className="chrono-reading-counts" aria-label="阅读提示">
            <span><strong>{lesson.body.length}</strong> 段正文</span>
            <span><strong>{keywords.length}</strong> 个词条</span>
          </div>
        </header>

        <ol className="chrono-reading-lenses" aria-label="四种阅读视角">
          {READING_LENSES.map((lens) => (
            <li key={lens.index}>
              <span>{lens.index}</span>
              <div><strong>{lens.title}</strong><small>{lens.note}</small></div>
            </li>
          ))}
        </ol>

        <div className="chrono-reading-body chrono-serif">
          {lesson.body.map((paragraph, index) => (
            renderBodyBlock(paragraph, index, keywords, keywordNumbers, selectedWord, selectKeyword)
          ))}
        </div>
      </article>

      <aside className="chrono-reading-sidebar" aria-label="关键词与知识点">
        <section className="chrono-knowledge-desk">
          <header>
            <span><BulbOutlined /></span>
            <div><strong>随读知识笺</strong><small>解释默认收起，等待你的选择</small></div>
          </header>

          <div
            className={`chrono-knowledge-note${selectedKeyword ? ' is-open' : ' is-idle'}`}
            id="chrono-knowledge-note"
            aria-live="polite"
            key={selectedKeyword?.word ?? 'knowledge-note-empty'}
          >
            {selectedKeyword ? (
              <>
                <button
                  className="chrono-knowledge-note-close"
                  type="button"
                  aria-label="收起知识笺"
                  onClick={() => setSelectedWord('')}
                >×</button>
                <span>词条 {String(keywordNumbers.get(selectedKeyword.word) ?? 0).padStart(2, '0')}</span>
                <h3>{selectedKeyword.word}</h3>
                {selectedKeyword.pinyin ? <small>{selectedKeyword.pinyin}</small> : null}
                <p>{selectedKeyword.gloss}</p>
              </>
            ) : (
              <>
                <span>未展开</span>
                <h3>在正文中寻找朱砂批注</h3>
                <p>词语本身先作为线索出现；只有点击后，解释才会像夹入史书的便签一样展开。</p>
              </>
            )}
          </div>

          <div className="chrono-keyword-index" aria-label="本课关键词">
            {lesson.keywords.map((keyword, index) => (
              <button
                type="button"
                className={selectedWord === keyword.word ? 'active' : ''}
                aria-pressed={selectedWord === keyword.word}
                onClick={() => selectKeyword(keyword)}
                key={keyword.word}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>{keyword.word}
              </button>
            ))}
          </div>
        </section>

        {(lesson.map_points?.length ?? 0) > 0 ? (
          <section className="chrono-reading-index-card">
            <header><EnvironmentOutlined /><strong>踏勘坐标</strong></header>
            <ol>
              {(lesson.map_points ?? []).map((point, index) => (
                <li key={`${point.label}-${point.region}`}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div><strong>{point.label}</strong>{point.region ? <small>{point.region}</small> : null}<p>{point.note}</p></div>
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {people.length > 0 ? (
          <section className="chrono-reading-index-card is-people">
            <header><TeamOutlined /><strong>人物与群体</strong></header>
            <div>
              {people.map((person) => (
                <article key={person.name}>
                  <strong>{person.name}</strong>
                  {person.role ? <small>{person.role}</small> : null}
                  <p>{person.summary || person.persona}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </aside>
    </div>
  );
}
