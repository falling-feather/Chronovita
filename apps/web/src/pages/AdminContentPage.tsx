import { useMemo, useState } from 'react';
import { Button, Input, Space, Tag } from 'antd';
import { EyeOutlined, FileTextOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api, type LessonContentPackage } from '../utils/api';
import { toast } from '../utils/toast';

const { TextArea } = Input;
const TOKEN_KEY = 'chrono.admin.token';

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parsePayload(raw: string): LessonContentPackage {
  const payload = JSON.parse(raw) as LessonContentPackage;
  if (!payload.lesson_id || !payload.title || !payload.unit || !payload.era) {
    throw new Error('lesson_id/title/unit/era required');
  }
  return payload;
}

export default function AdminContentPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || 'dev-admin-token');
  const [sealedBy, setSealedBy] = useState('admin');
  const [raw, setRaw] = useState('');
  const [preview, setPreview] = useState<LessonContentPackage | null>(null);
  const [sealedPath, setSealedPath] = useState('');
  const [busy, setBusy] = useState('');

  const currentPayload = useMemo(() => {
    try {
      return raw ? parsePayload(raw) : null;
    } catch {
      return null;
    }
  }, [raw]);

  const rememberToken = (value: string) => {
    setToken(value);
    localStorage.setItem(TOKEN_KEY, value);
  };

  const loadTemplate = async () => {
    setBusy('template');
    try {
      const item = await api.adminContentTemplate(token);
      setRaw(formatJson(item));
      setPreview(item);
      setSealedPath('');
      toast.success('模板已载入');
    } catch (err: any) {
      toast.error(err?.message || '模板载入失败');
    } finally {
      setBusy('');
    }
  };

  const previewContent = async () => {
    setBusy('preview');
    try {
      const payload = parsePayload(raw);
      const res = await api.adminContentPreview(token, payload);
      setPreview(res.item);
      setRaw(formatJson(res.item));
      setSealedPath('');
      toast.success('预览已更新');
    } catch (err: any) {
      toast.error(err?.message || '预览失败');
    } finally {
      setBusy('');
    }
  };

  const saveDraft = async () => {
    setBusy('save');
    try {
      const payload = parsePayload(raw);
      const res = await api.adminContentSaveDraft(token, payload);
      setPreview(res.item);
      setRaw(formatJson(res.item));
      setSealedPath('');
      toast.success('草稿已保存');
    } catch (err: any) {
      toast.error(err?.message || '草稿保存失败');
    } finally {
      setBusy('');
    }
  };

  const sealDraft = async () => {
    if (!currentPayload?.lesson_id) {
      toast.error('先保存一个有效草稿');
      return;
    }
    setBusy('seal');
    try {
      const res = await api.adminContentSeal(token, currentPayload.lesson_id, sealedBy || 'admin');
      setPreview(res.item);
      setRaw(formatJson(res.item));
      setSealedPath(res.record.path);
      toast.success('内容已封存');
    } catch (err: any) {
      toast.error(err?.message || '封存失败');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="chrono-page" style={{ maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-end', marginBottom: 18 }}>
        <div>
          <div className="chrono-course-eyeline">
            <span>Admin</span>
            <span>/api/v1/admin/content</span>
          </div>
          <h1 className="chrono-title" style={{ margin: 0 }}>内容封存工作台</h1>
        </div>
        <Space wrap>
          <Input.Password
            aria-label="Admin token"
            value={token}
            onChange={(e) => rememberToken(e.target.value)}
            style={{ width: 220 }}
          />
          <Input
            aria-label="Sealed by"
            value={sealedBy}
            onChange={(e) => setSealedBy(e.target.value)}
            style={{ width: 140 }}
          />
        </Space>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16, alignItems: 'start' }}>
        <section className="chrono-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            <div>
              <div className="chrono-title" style={{ fontSize: 16 }}>课程内容包</div>
              {currentPayload && <Tag color="blue">{currentPayload.lesson_id}</Tag>}
            </div>
            <Space wrap>
              <Button icon={<FileTextOutlined />} loading={busy === 'template'} onClick={loadTemplate}>模板</Button>
              <Button icon={<EyeOutlined />} loading={busy === 'preview'} onClick={previewContent}>预览</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={busy === 'save'} onClick={saveDraft}>保存草稿</Button>
              <Button danger icon={<LockOutlined />} loading={busy === 'seal'} onClick={sealDraft}>封存</Button>
            </Space>
          </div>
          <TextArea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            autoSize={{ minRows: 24, maxRows: 34 }}
            style={{ fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace', fontSize: 12, lineHeight: 1.65 }}
          />
        </section>

        <aside className="chrono-card" style={{ padding: 16 }}>
          <div className="chrono-title" style={{ fontSize: 16, marginBottom: 10 }}>规范化预览</div>
          {preview ? (
            <>
              <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
                <Tag color={preview.status === 'sealed' ? 'green' : 'gold'}>{preview.status}</Tag>
                <Tag>v{preview.version ?? 0}</Tag>
                {preview.sealed_by && <Tag>{preview.sealed_by}</Tag>}
              </Space>
              <div style={{ color: 'var(--text-dark)', lineHeight: 1.7, marginBottom: 12 }}>
                <strong>{preview.title}</strong>
                <div style={{ color: 'var(--text-mute)', fontSize: 12 }}>{preview.unit} · {preview.era}</div>
              </div>
              {sealedPath && (
                <div style={{ marginBottom: 12 }}>
                  <Tag color="green">{sealedPath}</Tag>
                  <div style={{ marginTop: 8 }}>
                    <Link to={`/courses/${preview.course_id || 'C-content-studio'}/lessons/${preview.lesson_id}?layer=watch`}>
                      打开课程页
                    </Link>
                  </div>
                </div>
              )}
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: 11, color: 'var(--text-mute)' }}>
                {formatJson({
                  lesson_id: preview.lesson_id,
                  title: preview.title,
                  body: preview.body?.length ?? 0,
                  keywords: preview.keywords?.length ?? 0,
                  people: preview.people?.length ?? 0,
                  map_points: preview.map_points?.length ?? 0,
                  source_refs: preview.source_refs?.length ?? 0,
                  facts: preview.facts?.length ?? 0,
                })}
              </pre>
            </>
          ) : (
            <div style={{ color: 'var(--text-mute)', fontSize: 13 }}>尚未生成预览</div>
          )}
        </aside>
      </div>
    </div>
  );
}
