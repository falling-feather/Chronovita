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
  type AssetGitPublicationRecord,
  type ContentAssetArchiveManifest,
  type ContentAssetArchivePublishRequest,
  type ContentAssetKind,
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

const ASSET_META: Record<
  ContentAssetKind,
  { label: string; versionLabel: string; empty: string }
> = {
  person: {
    label: '人物档案',
    versionLabel: '人物封存版本',
    empty: '人物档案封存后，可在这里生成归档并提交审核。',
  },
  keyword: {
    label: '关键词档案',
    versionLabel: '关键词封存版本',
    empty: '关键词档案封存后，可在这里生成归档并提交审核。',
  },
  scenario: {
    label: '关卡规则',
    versionLabel: '关卡封存版本',
    empty: '关卡规则封存后，可在这里生成归档并提交审核。',
  },
};

const PUBLICATION_STATUS_META: Record<
  PublicationStatus,
  { label: string; color: string; percent: number }
> = {
  requested: { label: '任务已接收', color: 'default', percent: 8 },
  preparing: { label: '正在核对归档', color: 'processing', percent: 22 },
  pushing: { label: '正在传送内容', color: 'processing', percent: 48 },
  commit_created: { label: '内容版本已生成', color: 'cyan', percent: 68 },
  ref_updated: { label: '审核版本已就绪', color: 'cyan', percent: 84 },
  pr_open: { label: '审核页面已建立', color: 'blue', percent: 94 },
  succeeded: { label: '已提交内容审核', color: 'green', percent: 100 },
  failed_retryable: { label: '暂时失败，可重试', color: 'orange', percent: 100 },
  failed_terminal: { label: '提交被阻止', color: 'red', percent: 100 },
};

export interface AssetPublicationVersion {
  version: number;
  checksum: string;
  title?: string;
  sealedAt?: string | null;
  sealedBy?: string | null;
}

interface AssetPublicationPanelProps {
  token: string;
  assetKind: ContentAssetKind;
  assetId: string;
  assetTitle: string;
  versions: AssetPublicationVersion[];
}

type Activity = '' | 'preview' | 'download' | 'publish' | 'refresh' | 'retry';

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
  return cleaned || '内容资产';
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

function publicationErrorLabel(code?: string | null): string {
  const labels: Record<string, string> = {
    content_asset_archive_changed: '封存内容在预览后发生变化，请重新生成归档预览。',
    github_authentication_failed: '提交凭据已失效，请联系项目管理员。',
    github_permission_denied: '当前提交服务没有写入内容审核库的权限。',
    github_repository_not_found: '内容审核库暂不可用，请联系项目管理员。',
    github_repository_id_mismatch: '内容审核库身份校验失败，已停止提交。',
    github_repository_name_mismatch: '内容审核库名称校验失败，已停止提交。',
    github_repository_not_private: '目标内容库不再是私有库，已停止提交。',
    github_ref_conflict: '审核库刚刚出现了新版本，请重新尝试。',
    github_rate_limited: '提交服务当前繁忙，请稍后重试。',
    github_timeout: '连接内容审核库超时，请稍后重试。',
    github_upstream_unavailable: '内容审核库暂时不可用，请稍后重试。',
  };
  return code ? labels[code] || '提交未完成，请联系项目管理员。' : '提交未完成。';
}

function requestErrorLabel(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'content_publication_disabled') {
      return '内容归档提交尚未由项目管理员启用，本地预览和下载仍可使用。';
    }
    if (error.code === 'content_publication_configuration_invalid') {
      return '内容归档提交配置尚未完成，请联系项目管理员。';
    }
  }
  return error instanceof Error ? error.message : '操作未完成';
}

function replacePublication(
  items: AssetGitPublicationRecord[],
  next: AssetGitPublicationRecord,
): AssetGitPublicationRecord[] {
  return [next, ...items.filter(
    (item) => item.intent.publication_id !== next.intent.publication_id,
  )].sort((left, right) => (
    new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  ));
}

function publicationStatusMeta(record: AssetGitPublicationRecord) {
  const meta = PUBLICATION_STATUS_META[record.status];
  if (
    record.status === 'succeeded'
    && record.intent.request.mode === 'direct_commit'
  ) {
    return { ...meta, label: '已直接保存到内容历史库' };
  }
  return meta;
}

function publicationResultUrl(record: AssetGitPublicationRecord): string | undefined {
  if (record.pull_request_url) return record.pull_request_url;
  if (record.status !== 'succeeded' || !record.commit_sha) return undefined;
  const { owner, repository } = record.intent.binding;
  return `https://github.com/${owner}/${repository}/commit/${record.commit_sha}`;
}

export default function AssetPublicationPanel({
  token,
  assetKind,
  assetId,
  assetTitle,
  versions,
}: AssetPublicationPanelProps) {
  const meta = ASSET_META[assetKind];
  const displayTitle = assetTitle.trim() || meta.label;
  const [selectedVersion, setSelectedVersion] = useState<number>();
  const [archive, setArchive] = useState<ContentAssetArchiveManifest | null>(null);
  const [publications, setPublications] = useState<AssetGitPublicationRecord[]>([]);
  const [selectedPublicationId, setSelectedPublicationId] = useState<string>();
  const [changeSummary, setChangeSummary] = useState('');
  const [mode, setMode] = useState<PublicationMode>('pull_request');
  const [directCommitConfirmed, setDirectCommitConfirmed] = useState(false);
  const [activity, setActivity] = useState<Activity>('');
  const [operationError, setOperationError] = useState('');
  const publicationSequenceRef = useRef(0);
  const previewSequenceRef = useRef(0);
  const operationSequenceRef = useRef(0);

  const orderedVersions = useMemo(
    () => versions
      .filter((item) => item.version > 0 && /^[0-9a-f]{64}$/.test(item.checksum))
      .slice()
      .sort((left, right) => (
        right.version - left.version || right.checksum.localeCompare(left.checksum)
      )),
    [versions],
  );
  const selected = useMemo(
    () => orderedVersions.find((item) => item.version === selectedVersion) ?? null,
    [orderedVersions, selectedVersion],
  );
  const versionPublications = useMemo(
    () => publications.filter(
      (item) => (
        item.intent.request.asset_kind === assetKind
        && item.intent.request.asset_id === assetId
        && item.intent.request.version === selectedVersion
        && item.intent.request.expected_source_checksum === selected?.checksum
      ),
    ),
    [assetId, assetKind, publications, selected?.checksum, selectedVersion],
  );
  const activePublication = useMemo(
    () => versionPublications.find(
      (item) => item.intent.publication_id === selectedPublicationId,
    ) ?? versionPublications[0] ?? null,
    [selectedPublicationId, versionPublications],
  );
  const archiveMatchesSelection = Boolean(
    archive
    && selected
    && archive.asset_kind === assetKind
    && archive.asset_id === assetId
    && archive.version === selected.version
    && archive.source_checksum === selected.checksum,
  );
  const activePublicationMatchesSelection = Boolean(
    activePublication
    && selected
    && activePublication.intent.request.asset_kind === assetKind
    && activePublication.intent.request.asset_id === assetId
    && activePublication.intent.request.version === selected.version
    && activePublication.intent.request.expected_source_checksum === selected.checksum,
  );
  const hasInProgressPublication = useMemo(
    () => publications.some((item) => (
      item.intent.request.asset_kind === assetKind
      && item.intent.request.asset_id === assetId
      && IN_PROGRESS_STATUSES.has(item.status)
    )),
    [assetId, assetKind, publications],
  );

  useEffect(() => {
    setSelectedVersion((current) => (
      current && orderedVersions.some((item) => item.version === current)
        ? current
        : orderedVersions[0]?.version
    ));
  }, [orderedVersions]);

  useEffect(() => {
    previewSequenceRef.current += 1;
    operationSequenceRef.current += 1;
    setArchive(null);
    setChangeSummary('');
    setDirectCommitConfirmed(false);
    setOperationError('');
    setActivity('');
  }, [assetId, assetKind, selected?.checksum, selectedVersion, token]);

  useEffect(() => {
    publicationSequenceRef.current += 1;
    setPublications([]);
    setSelectedPublicationId(undefined);
  }, [assetId, assetKind, token]);

  useEffect(() => {
    setSelectedPublicationId((current) => (
      current
      && versionPublications.some((item) => item.intent.publication_id === current)
        ? current
        : versionPublications[0]?.intent.publication_id
    ));
  }, [versionPublications]);

  const refreshPublications = useCallback(async (silent = false) => {
    const sequence = ++publicationSequenceRef.current;
    if (!token || !assetId) {
      setPublications([]);
      return;
    }
    if (!silent) setActivity('refresh');
    try {
      const response = await api.adminContentAssetPublications(token, {
        asset_kind: assetKind,
        asset_id: assetId,
      });
      if (publicationSequenceRef.current !== sequence) return;
      setPublications(response.items.filter((item) => (
        item.intent.request.asset_kind === assetKind
        && item.intent.request.asset_id === assetId
      )));
    } catch (error) {
      if (!silent && publicationSequenceRef.current === sequence) {
        toast.error(requestErrorLabel(error));
      }
    } finally {
      if (!silent && publicationSequenceRef.current === sequence) setActivity('');
    }
  }, [assetId, assetKind, token]);

  useEffect(() => {
    void refreshPublications(true);
  }, [refreshPublications]);

  useEffect(() => {
    if (!hasInProgressPublication) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      await refreshPublications(true);
      if (!cancelled) {
        timer = window.setTimeout(() => {
          void poll();
        }, 2500);
      }
    };
    timer = window.setTimeout(() => {
      void poll();
    }, 2500);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [hasInProgressPublication, refreshPublications]);

  const previewArchive = async () => {
    if (!selected) return;
    const sequence = ++previewSequenceRef.current;
    setActivity('preview');
    setOperationError('');
    try {
      const response = await api.adminContentAssetArchivePreview(
        token,
        assetKind,
        assetId,
        selected.version,
        selected.checksum,
      );
      if (previewSequenceRef.current !== sequence) return;
      setArchive(response.archive);
      setChangeSummary((current) => (
        current.trim()
          ? current
          : `归档“${response.archive.title}”第 ${response.archive.version} 版${meta.label}。`
      ));
      toast.success('归档预览已生成');
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
    if (!archive || !archiveMatchesSelection) return;
    const sequence = ++operationSequenceRef.current;
    setActivity('download');
    setOperationError('');
    try {
      const blob = await api.adminContentAssetArchiveFile(
        token,
        archive.asset_kind,
        archive.asset_id,
        archive.version,
        archive.source_checksum,
      );
      if (operationSequenceRef.current !== sequence) return;
      downloadBlob(
        `${safeFileBase(archive.title)}-${meta.label}-v${String(archive.version).padStart(3, '0')}-归档.zip`,
        blob,
      );
      toast.success('完整归档已下载');
    } catch (error) {
      if (operationSequenceRef.current !== sequence) return;
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      if (operationSequenceRef.current === sequence) setActivity('');
    }
  };

  const createPublication = async () => {
    if (!archive || !archiveMatchesSelection) return;
    if (mode === 'direct_commit' && !directCommitConfirmed) {
      toast.warning('管理员直接归档前需要再次确认');
      return;
    }
    const request: ContentAssetArchivePublishRequest = {
      schema_version: 'content-asset-archive-publish-request/v1',
      binding_id: CONTENT_HISTORY_BINDING,
      asset_kind: archive.asset_kind,
      asset_id: archive.asset_id,
      version: archive.version,
      expected_source_checksum: archive.source_checksum,
      archive_id: archive.archive_id,
      expected_archive_checksum: archive.archive_checksum,
      mode,
      client_request_id: `teacher-${archive.archive_checksum.slice(0, 48)}`,
      change_summary: changeSummary.trim(),
      direct_commit_confirmed: mode === 'direct_commit',
    };
    const sequence = ++operationSequenceRef.current;
    setActivity('publish');
    setOperationError('');
    try {
      const response = await api.adminCreateContentAssetPublication(token, request);
      if (operationSequenceRef.current !== sequence) return;
      setPublications((current) => replacePublication(current, response.publication));
      setSelectedPublicationId(response.publication.intent.publication_id);
      if (response.publication.status === 'succeeded') {
        toast.success(
          response.reused
            ? '已找到同一封存版本的提交记录'
            : mode === 'direct_commit'
              ? '内容已直接保存到历史库'
              : '内容已提交审核',
        );
      } else if (response.publication.status === 'failed_retryable') {
        toast.warning(publicationErrorLabel(response.publication.last_error_code));
      } else if (response.publication.status === 'failed_terminal') {
        toast.error(publicationErrorLabel(response.publication.last_error_code));
      }
    } catch (error) {
      if (operationSequenceRef.current !== sequence) return;
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      if (operationSequenceRef.current !== sequence) return;
      if (mode === 'direct_commit') setDirectCommitConfirmed(false);
      setActivity('');
    }
  };

  const retryPublication = async () => {
    if (!activePublication || !activePublicationMatchesSelection) return;
    const sequence = ++operationSequenceRef.current;
    setActivity('retry');
    setOperationError('');
    try {
      const response = await api.adminRetryContentAssetPublication(
        token,
        activePublication.intent.publication_id,
        activePublication.revision,
      );
      if (operationSequenceRef.current !== sequence) return;
      setPublications((current) => replacePublication(current, response.publication));
      setSelectedPublicationId(response.publication.intent.publication_id);
      if (response.publication.status === 'succeeded') {
        toast.success(
          response.publication.intent.request.mode === 'direct_commit'
            ? '内容已直接保存到历史库'
            : '内容已重新提交审核',
        );
      } else {
        toast.warning(publicationErrorLabel(response.publication.last_error_code));
      }
    } catch (error) {
      if (operationSequenceRef.current !== sequence) return;
      const message = requestErrorLabel(error);
      setOperationError(message);
      toast.error(message);
    } finally {
      if (operationSequenceRef.current !== sequence) return;
      setActivity('');
    }
  };

  if (!orderedVersions.length) {
    return (
      <section
        className="chrono-archive-publisher"
        data-testid={`asset-publication-panel-${assetKind}`}
      >
        <div className="chrono-archive-heading">
          <div>
            <div className="chrono-course-eyeline">内容历史留存</div>
            <h3>{displayTitle}归档</h3>
          </div>
        </div>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={meta.empty} />
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
    ? `${safeFileBase(archive.title)}-${meta.label}-v${String(archive.version).padStart(3, '0')}-归档.zip`
    : '';

  return (
    <section
      className="chrono-archive-publisher"
      data-testid={`asset-publication-panel-${assetKind}`}
    >
      <div className="chrono-archive-heading">
        <div>
          <div className="chrono-course-eyeline">内容历史留存</div>
          <h3>{displayTitle}归档</h3>
        </div>
        <Tooltip title="刷新提交状态">
          <Button
            aria-label={`刷新${meta.label}提交状态`}
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
          <span className="chrono-field-label">{meta.versionLabel}</span>
          <Select
            aria-label={`选择${meta.versionLabel}`}
            value={selectedVersion}
            disabled={busy}
            onChange={setSelectedVersion}
            options={orderedVersions.map((item) => ({
              value: item.version,
              label: `第 ${item.version} 版${item.sealedAt ? ` · ${new Date(item.sealedAt).toLocaleString()}` : ''}`,
            }))}
            style={{ width: '100%' }}
          />
        </label>
        <Space size={8} wrap className="chrono-archive-actions">
          <Button
            icon={<SafetyCertificateOutlined />}
            loading={activity === 'preview'}
            disabled={busy || !selected || !token}
            onClick={previewArchive}
          >
            生成归档预览
          </Button>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={activity === 'download'}
            disabled={busy || !archiveMatchesSelection}
            onClick={downloadArchive}
          >
            下载完整归档
          </Button>
        </Space>
      </div>

      {archive && (
        <div className="chrono-archive-preview" data-testid="asset-archive-preview">
          <div className="chrono-archive-summary">
            <div className="chrono-archive-filename">
              <FolderOpenOutlined />
              <span>{downloadName}</span>
            </div>
            <Space size={[6, 6]} wrap>
              <Tag>第 {archive.version} 版</Tag>
              <Tag>{formatBytes(archive.total_size_bytes)}</Tag>
              <Tooltip title={archive.archive_checksum}>
                <Tag color="blue">校验码 {archive.archive_checksum.slice(0, 12)}</Tag>
              </Tooltip>
            </Space>
          </div>
          <details className="chrono-archive-files">
            <summary>查看归档内容</summary>
            <div>
              {archive.files.map((file) => (
                <div className="chrono-archive-file-row" key={file.path}>
                  <span>{meta.label}封存件</span>
                  <code>第 {archive.version} 版可复核内容</code>
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
            aria-label={`${meta.label}更新说明`}
            value={changeSummary}
            disabled={busy}
            maxLength={2000}
            autoSize={{ minRows: 2, maxRows: 4 }}
            placeholder={`简要说明本次补充或修订的${meta.label}内容`}
            onChange={(event) => setChangeSummary(event.target.value)}
          />
        </label>

        <details className="chrono-archive-advanced">
          <summary>管理员高级选项</summary>
          <div>
            <Segmented
              aria-label={`${meta.label}提交方式`}
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
                我确认跳过人工审核并直接写入内容历史库
              </Checkbox>
            )}
          </div>
        </details>

        <Button
          type="primary"
          icon={<CloudUploadOutlined />}
          loading={activity === 'publish'}
          disabled={
            busy
            || !archiveMatchesSelection
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

      {versionPublications.length > 0 && (
        <div className="chrono-publication-state" data-testid="asset-publication-state">
          <div className="chrono-publication-state-header">
            <div>
              <span className="chrono-field-label">提交记录</span>
              {versionPublications.length > 1 && (
                <Select
                  aria-label={`选择${meta.label}提交记录`}
                  value={activePublication?.intent.publication_id}
                  onChange={setSelectedPublicationId}
                  options={versionPublications.map((item) => ({
                    value: item.intent.publication_id,
                    label: `${new Date(item.updated_at).toLocaleString()} · ${publicationStatusMeta(item).label}`,
                  }))}
                  style={{ width: 'min(100%, 360px)' }}
                />
              )}
            </div>
            {statusMeta && (
              <span role="status" aria-live="polite" aria-atomic="true">
                <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
              </span>
            )}
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
                    disabled={busy || !activePublicationMatchesSelection}
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
                      : '打开内容审核页面'}
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
