import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Spin, Tag } from 'antd';
import {
  FileSearchOutlined,
  LeftOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  getShijiChapter,
  getShijiNavigation,
  type ShijiChapterPayload,
  type ShijiNavigation,
  type ShijiSentence,
  type ShijiVolumeSummary,
} from '../features/shiji/shijiReaderApi';
import './ShijiReaderPage.css';

function sentenceText(sentence: ShijiSentence, traditional: boolean) {
  return (traditional ? sentence.traditional : sentence.simplified) || sentence.simplified || sentence.traditional || '';
}

function chapterSentences(payload: ShijiChapterPayload | undefined): ShijiSentence[] {
  return Array.isArray(payload?.sentences) ? payload.sentences : [];
}

export default function ShijiReaderPage() {
  const [navigation, setNavigation] = useState<ShijiNavigation | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState('');
  const [chapter, setChapter] = useState<ShijiChapterPayload | null>(null);
  const [volume, setVolume] = useState<ShijiVolumeSummary | null>(null);
  const [query, setQuery] = useState('');
  const [traditional, setTraditional] = useState(false);
  const [showTranslation, setShowTranslation] = useState(true);
  const [showOcr, setShowOcr] = useState(false);
  const [loading, setLoading] = useState(true);
  const [chapterLoading, setChapterLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    getShijiNavigation().then((value) => {
      if (!active) return;
      setNavigation(value);
      const first = value.volumes[0]?.chapters[0];
      if (first) setSelectedChapterId(first.id);
    }).catch((caught) => {
      if (active) setError(caught instanceof Error ? caught.message : '《史记》目录载入失败');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selectedChapterId) return;
    let active = true;
    setChapterLoading(true);
    setError('');
    getShijiChapter(selectedChapterId).then((value) => {
      if (!active) return;
      setChapter(value.payload.chapter ?? null);
      setVolume(navigation?.volumes.find((item) => item.volume_no === value.volume.volume_no) ?? null);
    }).catch((caught) => {
      if (active) setError(caught instanceof Error ? caught.message : '篇章载入失败');
    }).finally(() => {
      if (active) setChapterLoading(false);
    });
    return () => { active = false; };
  }, [navigation, selectedChapterId]);

  const visibleVolumes = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return navigation?.volumes ?? [];
    return (navigation?.volumes ?? []).map((item) => ({
      ...item,
      chapters: item.chapters.filter((entry) => `${item.title}${entry.title}${entry.preview ?? ''}`.toLocaleLowerCase().includes(needle)),
    })).filter((item) => item.title.toLocaleLowerCase().includes(needle) || item.chapters.length > 0);
  }, [navigation, query]);

  const sentences = chapterSentences(chapter ?? undefined);
  const selectedIndex = useMemo(() => {
    const all = navigation?.volumes.flatMap((item) => item.chapters) ?? [];
    return all.findIndex((item) => item.id === selectedChapterId);
  }, [navigation, selectedChapterId]);
  const allChapters = navigation?.volumes.flatMap((item) => item.chapters) ?? [];
  const jumpChapter = (offset: number) => {
    const next = allChapters[selectedIndex + offset];
    if (next) setSelectedChapterId(next.id);
  };

  return (
    <main className="shiji-reader-page">
      <header className="shiji-reader-hero">
        <div className="shiji-reader-kicker">DOCUMENTARY READING · OCR TEXT</div>
        <div className="shiji-reader-hero-row">
          <div>
            <h1><span>史</span>记文献阅读器</h1>
            <p>从真实 OCR 文本出发，逐句对照简繁原文、译读和来源页引用。</p>
          </div>
          <div className="shiji-reader-ledger">
            <strong>{navigation?.total_volumes ?? '—'}</strong>
            <span>卷运行时资料</span>
            <small>{navigation?.manifest_sha256 ? `资料校验 ${navigation.manifest_sha256.slice(0, 12)}…` : '正在读取资料包'}</small>
          </div>
        </div>
      </header>

      {error ? <Alert type="warning" showIcon message={error} /> : null}
      {loading ? <div className="shiji-reader-loading"><Spin /><span>正在打开《史记》目录…</span></div> : null}

      {!loading && navigation ? (
        <section className="shiji-reader-shell">
          <aside className="shiji-reader-catalog">
            <div className="shiji-reader-catalog-head">
              <div><span className="eyebrow">130 VOLUMES</span><h2>卷章目录</h2></div>
              <Tag color="gold">只读</Tag>
            </div>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索卷名或篇章"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="shiji-reader-volume-list">
              {visibleVolumes.map((item) => (
                <details key={item.volume_id} open={item.volume_no === volume?.volume_no || Boolean(query)}>
                  <summary><span>卷 {item.volume_no}</span><strong>{traditional ? item.title_traditional ?? item.title : item.title}</strong><small>{item.category}</small></summary>
                  <div className="shiji-reader-chapter-list">
                    {item.chapters.map((entry) => (
                      <button
                        className={entry.id === selectedChapterId ? 'active' : ''}
                        key={entry.id}
                        type="button"
                        onClick={() => setSelectedChapterId(entry.id)}
                      >
                        <span>{entry.title}</span>
                        <small>{entry.preview || '进入篇章'}</small>
                      </button>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </aside>

          <article className="shiji-reader-content">
            {chapterLoading ? <div className="shiji-reader-loading"><Spin /><span>正在载入正文与 OCR 层…</span></div> : null}
            {!chapterLoading && chapter ? (
              <>
                <header className="shiji-reader-chapter-head">
                  <div>
                    <span className="eyebrow">卷 {volume?.volume_no ?? '—'} · {volume?.category ?? '史记'}</span>
                    <h2>{traditional ? chapter.chapter_id : volume?.chapters.find((item) => item.id === selectedChapterId)?.title ?? chapter.chapter_id}</h2>
                    <p>正文、注释和 OCR 识别结果均来自迁移的史海运行时资料；当前页面不提供在线编辑。</p>
                  </div>
                  <div className="shiji-reader-actions">
                    <Button size="small" onClick={() => jumpChapter(-1)} disabled={selectedIndex <= 0}><LeftOutlined /> 上一篇</Button>
                    <Button size="small" onClick={() => jumpChapter(1)} disabled={selectedIndex < 0 || selectedIndex >= allChapters.length - 1}>下一篇 <RightOutlined /></Button>
                  </div>
                </header>
                <div className="shiji-reader-controls" role="toolbar" aria-label="阅读设置">
                  <Button size="small" type={traditional ? 'primary' : 'default'} onClick={() => setTraditional((value) => !value)}>繁 / 简</Button>
                  <Button size="small" type={showTranslation ? 'primary' : 'default'} onClick={() => setShowTranslation((value) => !value)}>译读</Button>
                  <Button size="small" type={showOcr ? 'primary' : 'default'} onClick={() => setShowOcr((value) => !value)}>OCR 原文</Button>
                  <span><FileSearchOutlined /> {sentences.length} 个识别段</span>
                </div>
                <div className="shiji-reader-paper">
                  {sentences.map((sentence, index) => (
                    <section className="shiji-reader-sentence" key={sentence.sentence_id || `${index}`}>
                      <div className="shiji-reader-sentence-index">{String(index + 1).padStart(3, '0')}</div>
                      <div>
                        <p className="shiji-reader-original">{sentenceText(sentence, traditional)}</p>
                        {showTranslation && sentence.translation ? <p className="shiji-reader-translation">{sentence.translation}</p> : null}
                        {showOcr && sentence.raw_ocr ? <pre className="shiji-reader-ocr">{sentence.raw_ocr}</pre> : null}
                        {sentence.source_span_ids?.length ? <small className="shiji-reader-source">来源页：{sentence.source_span_ids.join(' · ')}</small> : null}
                      </div>
                    </section>
                  ))}
                  {!sentences.length ? <Empty description="当前篇章暂无可显示正文" /> : null}
                </div>
              </>
            ) : null}
          </article>
        </section>
      ) : null}
    </main>
  );
}
