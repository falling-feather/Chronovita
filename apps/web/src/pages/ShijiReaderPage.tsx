import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Drawer, Select, Space, Spin, Typography } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { READER_QUOTE_MESSAGE, readerQuoteRequest, type ReaderQuote } from '../../../readerContracts';
import { useAuth } from '../auth/AuthContext';
import { api } from '../utils/api';
import {
  TEMPORARY_NOTEBOOK_EVENT, TEMPORARY_NOTEBOOK_MAX_LENGTH,
  readTemporaryNotebook, writeTemporaryNotebook,
} from '../features/classroom/temporaryNotebook';
import { appendLearningEvent } from '../features/classroom/learningLedger';
import { toast } from '../utils/toast';
import './ShijiReaderPage.css';

type Destination = { value: string; label: string; courseId: string; lessonId: string };

export default function ShijiReaderPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const iframe = useRef<HTMLIFrameElement>(null);
  const generation = useRef(0);
  const saving = useRef(false);
  const [quote, setQuote] = useState<ReaderQuote | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [target, setTarget] = useState<string>();
  const [savedQuoteId, setSavedQuoteId] = useState('');
  const source = useMemo(() => {
    const passage = params.get('passage');
    const sentence = params.get('sentence');
    const checksum = params.get('checksum');
    const query = new URLSearchParams();
    if (sentence) query.set('sentence', sentence);
    if (checksum) query.set('checksum', checksum);
    const target = passage ? `#/reader/${encodeURIComponent(passage)}${query.size ? `?${query}` : ''}` : '';
    return `${import.meta.env.BASE_URL}shiji-reader/index.html${target}`;
  }, [params]);

  useEffect(() => {
    const onMessage = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== iframe.current?.contentWindow
        || event.data?.type !== READER_QUOTE_MESSAGE) return;
      const request = readerQuoteRequest(event.data.request);
      if (!request) return;
      const id = ++generation.current;
      setOpen(true); setLoading(true); setError(''); setQuote(null); setSavedQuoteId('');
      try {
        const resolved = await api.readerQuote(request);
        if (generation.current !== id) return;
        setQuote(resolved);
        const choices = await api.readerDestinations();
        if (generation.current !== id) return;
        setDestinations(choices);
        const origin = `${params.get('course') || ''}/${params.get('lesson') || ''}`;
        if (choices.some((choice) => choice.value === origin)) setTarget(origin);
      } catch (failure) {
        if (generation.current === id) setError(failure instanceof Error ? failure.message : '摘录暂不可用');
      } finally {
        if (generation.current === id) setLoading(false);
      }
    };
    window.addEventListener('message', onMessage);
    return () => { generation.current += 1; window.removeEventListener('message', onMessage); };
  }, [auth.principal?.user_id, params]);

  const saveQuote = async (goToDesk: boolean) => {
    const destination = destinations.find((item) => item.value === target);
    if (!quote || !destination || !auth.principal || saving.current) return;
    if (savedQuoteId === `${quote.quote_id}/${destination.value}`) {
      if (goToDesk) navigate(`/courses/${destination.courseId}/lessons/${destination.lessonId}?layer=create`);
      return;
    }
    saving.current = true;
    const identity = { ownerId: auth.principal.user_id, courseId: destination.courseId, lessonId: destination.lessonId };
    const url = `/shiji?passage=${encodeURIComponent(quote.passage_id)}&sentence=${encodeURIComponent(quote.sentence_ids[0])}&checksum=${quote.chapter_checksum}`;
    const citation = `> ${quote.quote_text.split('\n').join('\n> ')}\n\n出处：《${quote.book_title}》卷${quote.volume_no}·${quote.volume_title}／${quote.passage_title}\n[${quote.text_variant === 'traditional' ? '繁体转写' : '简体转写'} · 返回原文](${url})\n${quote.review_notice}\n`;
    try {
      const existing = readTemporaryNotebook(window.localStorage, identity)?.body || '';
      const body = `${existing}${existing ? '\n\n' : ''}${citation}`;
      if (body.length > TEMPORARY_NOTEBOOK_MAX_LENGTH) {
        setError('临时笔记空间不足，请先将已有内容保存到书案，再摘录。'); return;
      }
      const saved = writeTemporaryNotebook(window.localStorage, identity, body);
      if (!saved.persisted) { setError('浏览器未能保存摘录，原文仍保留在窗口中。'); return; }
      window.dispatchEvent(new CustomEvent(TEMPORARY_NOTEBOOK_EVENT));
      setSavedQuoteId(`${quote.quote_id}/${destination.value}`);
      await appendLearningEvent(identity, {
        course_id: destination.courseId, lesson_id: destination.lessonId, kind: 'temporary_note_saved',
        title: '保存史料摘录', summary: `《史记》卷${quote.volume_no}·${quote.passage_title}`,
        metadata: { book_id: quote.book_id, passage_id: quote.passage_id, chapter_checksum: quote.chapter_checksum,
          quote_checksum: quote.checksum, sentence_ids: quote.sentence_ids.join(','), text_variant: quote.text_variant },
      });
      toast.success('摘录已保存在本机临时笔记，未上传教师');
      setOpen(false);
      if (goToDesk) navigate(`/courses/${destination.courseId}/lessons/${destination.lessonId}?layer=create`);
    } catch {
      setError('摘录已写入临时笔记，但过程记录未能保存；请检查浏览器存储。');
    } finally {
      saving.current = false;
    }
  };

  return (
    <main className="chrono-shiji-reader-embed" aria-label="《史记》完整文献阅读器">
      <iframe ref={iframe} title="《史记》完整文献阅读器" src={source} allow="fullscreen" />
      <Drawer title="保存史料摘录" open={open} width="min(520px, 96vw)"
        onClose={() => { generation.current += 1; setOpen(false); }}>
        {loading ? <Spin /> : null}
        {error ? <Alert type="warning" showIcon message={error} /> : null}
        {quote ? <>
          <Typography.Title level={4}>《史记》卷{quote.volume_no} · {quote.volume_title}</Typography.Title>
          <blockquote style={{ margin: '20px 0', lineHeight: 1.9 }}>{quote.quote_text}</blockquote>
          <Typography.Paragraph type="secondary">{quote.review_notice}</Typography.Paragraph>
          <Select style={{ width: '100%' }} aria-label="保存到哪一课的书案" placeholder="选择学习书案" showSearch
            optionFilterProp="label" options={destinations} value={target} onChange={setTarget} />
          <Space style={{ marginTop: 20 }} wrap>
            <Button disabled={!target || loading} onClick={() => void saveQuote(false)}>保存到临时笔记</Button>
            <Button type="primary" disabled={!target || loading} onClick={() => void saveQuote(true)}>保存并打开书案</Button>
          </Space>
        </> : null}
      </Drawer>
    </main>
  );
}
