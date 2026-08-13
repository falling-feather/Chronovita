import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Checkbox,
  Empty,
  Input,
  Progress,
  Segmented,
  Select,
  Space,
  Tag,
  Tooltip,
} from 'antd';
import {
  CloudDownloadOutlined,
  CloudUploadOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {
  ApiError,
  api,
  type ArchiveFileKind,
  type CourseArchiveManifest,
  type CourseArchivePublishRequest,
  type CourseReleaseManifest,
  type GitPublicationRecord,
  type PublicationMode,
  type PublicationStatus,
} from '../../utils/api';
import { toast } from '../../utils/toast';

const { TextArea } = Input;
const CONTENT_HISTORY_BINDING = 'content-history-primary';
const IN_PROGRESS_STATUSES = new Set<PublicationStatus>([
  'requested',
  'preparing',
  'pushing',
  'commit_created',
  'ref_updated',
  'pr_open',
]);

const PUBLICATION_STATUS_META: Record<
  PublicationStatus,
  { label: string; color: string; percent: number }
> = {
  requested: { label: '任务已接收', color: 'default', percent: 8 },
  preparing: { label: '正在核对课程包', color: 'processing', percent: 22 },
  pushing: { label: '正在传送文件', color: 'processing', percent: 48 },
  commit_created: { label: '文件版本已生成', color: 'cyan', percent: 68 },
  ref_updated: { label: '审核版本已就绪', color: 'cyan', percent: 84 },
  pr_open: { label: '审核页面已建立', color: 'blue', percent: 94 },
  succeeded: { label: '已提交内容审核', color: 'green', percent: 100 },
  failed_retryable: { label: '暂时失败，可重试', color: 'orange', percent: 100 },
  failed_terminal: { label: '提交被阻止', color: 'red', percent: 100 },
};

const ARCHIVE_FILE_LABELS: Record<ArchiveFileKind, string> = {
  'release-manifest': '课程版本清单',
  'sealed-lesson': '课程原稿',
  'course-package': '课程运行包',
  'scenario-template': '情境关卡',
  'format-layer': '格式层',
  'teacher-markdown': '教师稿',
  'preview-html': '离线预览',
};

interface ArchivePublicationPanelProps {
  token: string;
  canPublish: boolean;
  courseId: string;
  releases: CourseReleaseManifest[];
  currentRelease: CourseReleaseManifest | null;
}

type Activity =
  | ''
  | 'preview'
  | 'download'
  | 'publish'
  | 'refresh'
  | 'retry';

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function safeFileBase(value: string): string {
  const cleaned = value
    .normalize('NFKC')
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-')
    .replace(/[. ]+$/g, '')
    .trim();
  return cleaned || '课程内容';
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function operationLabel(operation: CourseReleaseManifest['operation']): string {
  if (operation === 'rollback') return '回滚版本';
  if (operation === 'bootstrap') return '历史导入';
  return '正式发布';
}

function publicationErrorLabel(code?: string | null): string {
  const labels: Record<string, string> = {
    content_publication_archive_changed: '课程文件在预览后发生变化，请重新预览。',
    github_authentication_failed: '服务器发布凭据已失效，请联系项目管理员。',
    github_permission_denied: '服务器没有写入内容审核库的权限。',
    github_repository_not_found: '内容审核库不可用，请联系项目管理员。',
    github_repository_id_mismatch: '内容审核库身份校验失败，已停止提交。',
    github_repository_name_mismatch: '内容审核库名称校验失败，已停止提交。',
    github_repository_not_private: '目标仓库不再是私有仓库，已停止提交。',
    github_ref_conflict: '审核库刚刚有新版本，请重新尝试。',
    github_rate_limited: '提交服务当前繁忙，请稍后重试。',
    github_timeout: '连接内容审核库超时，请稍后重试。',
    github_upstream_unavailable: '内容审核库暂时不可用，请稍后重试。',
  };
  return code ? labels[code] || `提交未完成（${code}）` : '提交未完成。';
}

function publicationStatusMeta(record: GitPublicationRecord) {
  const meta = PUBLICATION_STATUS_META[record.status];
  if (
    record.status === 'succeeded'
    && record.intent.request.mode === 'direct_commit'
  ) {
    return { ...meta, label: '已保存到课程历史库' };
  }
  return meta;
}

function publicationResultUrl(record: GitPublicationRecord): string | undefined {
  if (record.pull_request_url) return record.pull_request_url;
  if (record.status !== 'succeeded' || !record.commit_sha) return undefined;
  const { owner, repository } = record.intent.binding;
  return `https://github.com/${owner}/${repository}/commit/${record.commit_sha}`;
}

function requestErrorLabel(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'content_publication_disabled') {
      return '课程历史发布尚未由项目管理员启用，本地预览和下载仍可使用。';
    }
    if (error.code === 'content_publication_configuration_invalid') {
      return '课程历史发布配置尚未完成，请联系项目管理员。';
    }
  }
  return error instanceof Error ? error.message : '操作未完成';
}

function replacePublication(
  items: GitPublicationRecord[],
  next: GitPublicationRecord,
): GitPublicationRecord[] {
  return [next, ...items.filter(
    (item) => item.intent.publication_id !== next.intent.publication_id,
  )].sort((left, right) => (
    new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  ));
}

export default function ArchivePublicationPanel({
  token,
  canPublish,
  courseId,
  releases,
  currentRelease,
}: ArchivePublicationPanelProps) {
  const [selectedReleaseId, setSelectedReleaseId] = useState<string>();
  const [archive, setArchive] = useState<CourseArchiveManifest | null>(null);
  const [publications, setPublications] = useState<GitPublicationRecord[]>([]);
  const [selectedPublicationId, setSelectedPublicationId] = useState<string>();
  const [changeSummary, setChangeSummary] = useState('');
  const [mode, setMode] = useState<PublicationMode>('pull_request');
  const [directCommitConfirmed, setDirectCommitConfirmed] = useState(false);
  const [activity, setActivity] = useState<Activity>('');
  const [operationError, setOperationError] = useState('');
  const publicationSequenceRef = useRef(0);
  const previewSequenceRef = useRef(0);

  const orderedReleases = useMemo(
    () => releases.slice().sort((left, right) => right.release_no - left.release_no),
    [releases],
  );
  const selectedRelease = useMemo(
    () => orderedReleases.find((item) => item.release_id === selectedReleaseId) ?? null,
    [orderedReleases, selectedReleaseId],
  );
  const releasePublications = useMemo(
    () => publications.filter(
      (item) => item.intent.request.release_id === selectedReleaseId,
    ),
    [publications, selectedReleaseId],
  );
  const activePublication = useMemo(
    () => releasePublications.find(
      (item) => item.intent.publication_id === selectedPublicationId,
    ) ?? releasePublications[0] ?? null,
    [releasePublications, selectedPublicationId],
  );

  useEffect(() => {
    setSelectedReleaseId((current) => {
      if (current && orderedReleases.some((item) => item.release_id === current)) {
        return current;
      }
      return currentRelease?.release_id ?? orderedReleases[0]?.release_id;
    });
  }, [currentRelease?.release_id, orderedReleases]);

  useEffect(() => {
    previewSequenceRef.current += 1;
    setArchive(null);
    setChangeSummary('');
    setDirectCommitConfirmed(false);
    setOperationError('');
    setActivity((current) => (
      current === 'preview' || current === 'download' ? '' : current
    ));
  }, [courseId, selectedReleaseId, token]);

  useEffect(() => {
    setSelectedPublicationId((current) => {
      if (
        current
        && releasePublications.some(
          (item) => item.intent.publication_id === current,
        )
      ) {
        return current;
      }
      return releasePublications[0]?.intent.publication_id;
    });
  }, [releasePublications]);

  const refreshPublications = useCallback(async (silent = false) => {
    const sequence = ++publicationSequenceRef.current;
    if (!token || !courseId) {
      setPublications([]);
      return;
    }
    if (!silent) setActivity('refresh');
    try {
      const response = await api.adminContentPublications(token, {
        course_id: courseId,
      });
      if (publicationSequenceRef.current !== sequence) return;
      setPublications(response.items);
    } catch (error) {
      if (!silent && publicationSequenceRef.current === sequence) {
        toast.error(requestErrorLabel(error));
      }
    } finally {
      if (!silent && publicationSequenceRef.current === sequence) setActivity('');
    }
  }, [courseId, token]);

  useEffect(() => {
    void refreshPublications(true);
  }, [refreshPublications]);

  useEffect(() => {
    if (!publications.some((item) => IN_PROGRESS_STATUSES.has(item.status))) return;
    const timer = window.setTimeout(() => {
      void refreshPublications(true);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [publications, refreshPublications]);

  const previewArchive = async () => {
    if (!selectedRelease) return;
    const sequence = ++previewSequenceRef.current;
    setActivity('preview');
    setOperationError('');
    try {
      const response = await api.adminContentArchivePreview(
        token,
        selectedRelease.course_id,
        selectedRelease.release_id,
      );
      if (previewSequenceRef.current !== sequence) return;
      setArchive(response.archive);
      setChangeSummary((current) => (
        current.trim()
          ? current
          : `归档“${response.archive.course_title}”第 ${response.archive.release_no} 版课程内容。`
      ));
      toast.success('课程文件包预览已生成');
    } catch (error) {
      if (previewSequenceRef.current !== sequence) return;
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      if (previewSequenceRef.current === sequence) setActivity('');
    }
  };

  const downloadArchive = async () => {
    if (!archive || archive.release_id !== selectedReleaseId) return;
    setActivity('download');
    setOperationError('');
    try {
      const blob = await api.adminContentArchiveFile(
        token,
        archive.course_id,
        archive.release_id,
      );
      downloadBlob(
        `${safeFileBase(archive.course_title)}-第${archive.release_no}版-课程归档.zip`,
        blob,
      );
      toast.success('完整课程文件包已下载');
    } catch (error) {
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      setActivity('');
    }
  };

  const createPublication = async () => {
    if (!archive) return;
    if (mode === 'direct_commit' && !directCommitConfirmed) {
      toast.warning('管理员直接归档前需要再次确认');
      return;
    }
    const request: CourseArchivePublishRequest = {
      schema_version: 'course-archive-publish-request/v1',
      binding_id: CONTENT_HISTORY_BINDING,
      course_id: archive.course_id,
      release_id: archive.release_id,
      expected_release_checksum: archive.release_checksum,
      archive_id: archive.archive_id,
      expected_archive_checksum: archive.archive_checksum,
      mode,
      client_request_id: `teacher-${archive.archive_checksum.slice(0, 48)}`,
      change_summary: changeSummary.trim(),
      direct_commit_confirmed: mode === 'direct_commit',
    };
    setActivity('publish');
    setOperationError('');
    try {
      const response = await api.adminCreateContentPublication(token, request);
      setPublications((current) => replacePublication(
        current,
        response.publication,
      ));
      setSelectedPublicationId(response.publication.intent.publication_id);
      if (response.publication.status === 'succeeded') {
        toast.success(
          response.reused
            ? '已找到同一课程包的提交记录'
            : mode === 'direct_commit'
              ? '课程内容已保存到历史库'
              : '课程内容已提交审核',
        );
      } else if (response.publication.status === 'failed_retryable') {
        toast.warning(publicationErrorLabel(response.publication.last_error_code));
      } else if (response.publication.status === 'failed_terminal') {
        toast.error(publicationErrorLabel(response.publication.last_error_code));
      }
    } catch (error) {
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      if (mode === 'direct_commit') setDirectCommitConfirmed(false);
      setActivity('');
    }
  };

  const retryPublication = async () => {
    if (!activePublication) return;
    setActivity('retry');
    setOperationError('');
    try {
      const response = await api.adminRetryContentPublication(
        token,
        activePublication.intent.publication_id,
        activePublication.revision,
      );
      setPublications((current) => replacePublication(
        current,
        response.publication,
      ));
      setSelectedPublicationId(response.publication.intent.publication_id);
      if (response.publication.status === 'succeeded') {
        toast.success(
          response.publication.intent.request.mode === 'direct_commit'
            ? '课程内容已保存到历史库'
            : '课程内容已重新提交审核',
        );
      } else {
        toast.warning(publicationErrorLabel(response.publication.last_error_code));
      }
    } catch (error) {
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      setActivity('');
    }
  };

  if (!orderedReleases.length) {
    return (
      <section className="chrono-archive-publisher" data-testid="archive-publication-panel">
        <div className="chrono-archive-heading">
          <div>
            <div className="chrono-course-eyeline">课程历史留档</div>
            <h3>课程文件包</h3>
          </div>
        </div>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="课程正式发布后可生成历史文件包"
        />
      </section>
    );
  }

  const statusMeta = activePublication
    ? publicationStatusMeta(activePublication)
    : null;
  const resultUrl = activePublication
    ? publicationResultUrl(activePublication)
    : undefined;
  const busy = activity !== '';
  const downloadName = archive
    ? `${safeFileBase(archive.course_title)}-第${archive.release_no}版-课程归档.zip`
    : '';

  return (
    <section className="chrono-archive-publisher" data-testid="archive-publication-panel">
      <div className="chrono-archive-heading">
        <div>
          <div className="chrono-course-eyeline">课程历史留档</div>
          <h3>课程文件包</h3>
        </div>
        <Tooltip title="刷新提交状态">
          <Button
            aria-label="刷新课程历史提交状态"
            type="text"
            icon={<ReloadOutlined />}
            loading={activity === 'refresh'}
            disabled={busy}
            onClick={() => void refreshPublications(false)}
          />
        </Tooltip>
      </div>

      <div className="chrono-archive-controls">
        <label>
          <span className="chrono-field-label">已发布课程版本</span>
          <Select
            aria-label="选择课程归档版本"
            value={selectedReleaseId}
            disabled={busy}
            onChange={setSelectedReleaseId}
            options={orderedReleases.map((item) => ({
              value: item.release_id,
              label: `第 ${item.release_no} 版 · ${operationLabel(item.operation)} · ${item.items.length} 节`,
            }))}
            style={{ width: '100%' }}
          />
        </label>
        <Space size={8} wrap className="chrono-archive-actions">
          <Button
            icon={<SafetyCertificateOutlined />}
            loading={activity === 'preview'}
            disabled={busy || !selectedRelease || !token}
            onClick={previewArchive}
          >
            预览文件包
          </Button>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={activity === 'download'}
            disabled={busy || !archive || archive.release_id !== selectedReleaseId}
            onClick={downloadArchive}
          >
            下载完整包
          </Button>
        </Space>
      </div>

      {archive && (
        <div className="chrono-archive-preview" data-testid="archive-preview">
          <div className="chrono-archive-summary">
            <div className="chrono-archive-filename">
              <FolderOpenOutlined />
              <span>{downloadName}</span>
            </div>
            <Space size={[6, 6]} wrap>
              <Tag>{archive.file_count} 个文件</Tag>
              <Tag>{formatBytes(archive.total_size_bytes)}</Tag>
              <Tooltip title={archive.archive_checksum}>
                <Tag color="blue">校验码 {archive.archive_checksum.slice(0, 12)}</Tag>
              </Tooltip>
            </Space>
          </div>
          <details className="chrono-archive-files">
            <summary>查看文件清单</summary>
            <div>
              {archive.files.map((file) => (
                <div className="chrono-archive-file-row" key={file.path}>
                  <span>{ARCHIVE_FILE_LABELS[file.kind]}</span>
                  <code title={file.path}>{file.path}</code>
                  <span>{formatBytes(file.size_bytes)}</span>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      <div className="chrono-archive-submit">
        <label>
          <span className="chrono-field-label">本次更新说明</span>
          <TextArea
            aria-label="课程历史更新说明"
            value={changeSummary}
            disabled={busy}
            maxLength={2000}
            autoSize={{ minRows: 2, maxRows: 4 }}
            placeholder="简要说明本次补充或修订的内容"
            onChange={(event) => setChangeSummary(event.target.value)}
          />
        </label>

        <details className="chrono-archive-advanced">
          <summary>管理员高级选项</summary>
          <div>
            <Segmented
              aria-label="课程历史提交方式"
              value={mode}
              disabled={busy}
              options={[
                { label: '提交审核', value: 'pull_request' },
                { label: '管理员直接归档', value: 'direct_commit' },
              ]}
              onChange={(value) => {
                setMode(value as PublicationMode);
                setDirectCommitConfirmed(false);
              }}
            />
            {mode === 'direct_commit' && (
              <Checkbox
                checked={directCommitConfirmed}
                disabled={busy}
                onChange={(event) => setDirectCommitConfirmed(event.target.checked)}
              >
                我确认跳过人工审核并直接写入历史库
              </Checkbox>
            )}
          </div>
        </details>

        <Button
          type="primary"
          icon={<CloudUploadOutlined />}
          loading={activity === 'publish'}
          disabled={
            !canPublish
            || busy
            || !archive
            || archive.release_id !== selectedReleaseId
            || (mode === 'direct_commit' && !directCommitConfirmed)
          }
          onClick={createPublication}
        >
          {mode === 'pull_request' ? '提交内容审核' : '直接归档'}
        </Button>
      </div>

      {operationError && (
        <div className="chrono-archive-notice" role="status">
          {operationError}
        </div>
      )}

      {releasePublications.length > 0 && (
        <div className="chrono-publication-state" data-testid="publication-state">
          <div className="chrono-publication-state-header">
            <div>
              <span className="chrono-field-label">提交记录</span>
              {releasePublications.length > 1 && (
                <Select
                  aria-label="选择课程历史提交记录"
                  value={activePublication?.intent.publication_id}
                  onChange={setSelectedPublicationId}
                  options={releasePublications.map((item) => ({
                    value: item.intent.publication_id,
                    label: `${new Date(item.updated_at).toLocaleString()} · ${publicationStatusMeta(item).label}`,
                  }))}
                  style={{ width: 'min(100%, 360px)' }}
                />
              )}
            </div>
            {statusMeta && <Tag color={statusMeta.color}>{statusMeta.label}</Tag>}
          </div>

          {activePublication && statusMeta && (
            <>
              <Progress
                percent={statusMeta.percent}
                status={
                  activePublication.status === 'failed_terminal'
                    || activePublication.status === 'failed_retryable'
                    ? 'exception'
                    : activePublication.status === 'succeeded'
                      ? 'success'
                      : 'active'
                }
                showInfo={false}
                size="small"
              />
              <div className="chrono-publication-meta">
                <span>更新于 {new Date(activePublication.updated_at).toLocaleString()}</span>
                <span>第 {activePublication.attempt} 次处理</span>
                <span>任务 {activePublication.intent.publication_id.slice(-8)}</span>
              </div>

              {activePublication.last_error_code && (
                <div className="chrono-publication-error">
                  {publicationErrorLabel(activePublication.last_error_code)}
                </div>
              )}

              <Space size={8} wrap>
                {activePublication.status === 'failed_retryable' && (
                  <Button
                    icon={<ReloadOutlined />}
                    loading={activity === 'retry'}
                    disabled={!canPublish || busy}
                    onClick={retryPublication}
                  >
                    重新尝试
                  </Button>
                )}
                {resultUrl && (
                  <Button
                    type="primary"
                    icon={<FolderOpenOutlined />}
                    href={resultUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {activePublication.intent.request.mode === 'direct_commit'
                      ? '打开历史记录'
                      : '打开内容审核页'}
                  </Button>
                )}
              </Space>
            </>
          )}
        </div>
      )}
    </section>
  );
}
