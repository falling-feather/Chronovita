import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { setRecallToSandbox } from '../bridge';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

interface PromptStep {
  role: string;
  template: string;
  rendered: string | null;
}

interface PromptChainResult {
  chain_id: string;
  steps: PromptStep[];
  final_prompt: string;
  negative_prompt: string;
}

interface ControlSignal {
  kind: string;
  weight: number;
  source_uri: string | null;
  note: string;
}

interface Shot {
  index: number;
  duration_sec: number;
  summary: string;
  prompt: PromptChainResult;
  control_signals: ControlSignal[];
  voiceover: string;
}

interface Storyboard {
  storyboard_id: string;
  chapter_id: string;
  title: string;
  style: string;
  shots: Shot[];
  created_at: string;
}

interface RenderJob {
  job_id: string;
  storyboard_id: string;
  status: string;
  stage: string;
  progress: number;
  video_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

const STAGE_LABEL: Record<string, string> = {
  queued: '排队中',
  prompt_chain: 'Prompt 链',
  storyboard: '分镜编排',
  controlnet: 'ControlNet 约束',
  diffusion: '扩散绘制',
  animation: '动效插帧',
  tts: '声线合成',
  compose: '拼接合成',
  done: '已完成',
  failed: '失败',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
};

export default function RecallPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [jobs, setJobs] = useState<RenderJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refreshJobs = async () => {
    try {
      const res = await fetch('/api/v1/recall/jobs');
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data);
    } catch {
      // 忽略轮询错误
    }
  };

  useEffect(() => {
    refreshJobs();
    const t = setInterval(refreshJobs, 2000);
    return () => clearInterval(t);
  }, []);

  const onGenerate = async (values: {
    chapter_id: string;
    title: string;
    history_context: string;
    keywords: string;
    style: string;
    target_shot_count: number;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const body = {
        chapter_id: values.chapter_id,
        title: values.title,
        history_context: values.history_context,
        keywords: values.keywords
          .split(/[,，、\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        style: values.style,
        target_shot_count: values.target_shot_count,
      };
      const res = await fetch('/api/v1/recall/storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`生成分镜失败：${res.status}`);
      const data: Storyboard = await res.json();
      setStoryboard(data);
      message.success(`已生成 ${data.shots.length} 个分镜`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setLoading(false);
    }
  };

  const onSubmitRender = async () => {
    if (!storyboard) return;
    try {
      const res = await fetch(
        `/api/v1/recall/render?storyboard_id=${encodeURIComponent(storyboard.storyboard_id)}`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error(`提交任务失败：${res.status}`);
      const job: RenderJob = await res.json();
      message.success(`已提交渲染任务 ${job.job_id}`);
      refreshJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '提交失败');
    }
  };

  return (
    <div>
      <Title level={3} className="chrono-title">看 · 沉浸叙事</Title>
      <Paragraph>
        基于 Prompt 链与 ControlNet 工作流，将历史文本转化为符合史实形制的高质量微视频。当前为 v1.1.0
        编排骨架，渲染阶段为占位推进。
      </Paragraph>

      <Row gutter={24}>
        <Col xs={24} lg={10}>
          <Card title="新建分镜">
            <Form
              form={form}
              layout="vertical"
              onFinish={onGenerate}
              initialValues={{
                chapter_id: 'xia-001',
                title: '大禹治水',
                history_context:
                  '约公元前 2070 年，禹承父业，划九州、定贡赋，疏导河川以解水患。',
                keywords: '黄河, 堤坝, 九州, 民众',
                style: '工笔淡彩',
                target_shot_count: 4,
              }}
            >
              <Form.Item label="章节编号" name="chapter_id" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item label="叙事标题" name="title" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item label="历史背景" name="history_context" rules={[{ required: true }]}>
                <TextArea rows={4} />
              </Form.Item>
              <Form.Item label="关键词（逗号或顿号分隔）" name="keywords">
                <Input />
              </Form.Item>
              <Form.Item label="美术风格" name="style">
                <Select
                  options={[
                    { value: '工笔淡彩', label: '工笔淡彩' },
                    { value: '写意水墨', label: '写意水墨' },
                    { value: '青绿山水', label: '青绿山水' },
                    { value: '帛画绢本', label: '帛画绢本' },
                  ]}
                />
              </Form.Item>
              <Form.Item label="分镜数量" name="target_shot_count">
                <InputNumber min={1} max={12} style={{ width: '100%' }} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                生成分镜
              </Button>
            </Form>
            {error && <Alert style={{ marginTop: 12 }} type="error" message={error} />}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title={storyboard ? `分镜：${storyboard.title}` : '分镜预览'}
            extra={
              storyboard && (
                <Space>
                  <Tag color="gold">{storyboard.style}</Tag>
                  <Button type="primary" onClick={onSubmitRender}>
                    提交渲染
                  </Button>
                  <Button
                    onClick={() => {
                      const values = form.getFieldsValue();
                      const keywords = String(values.keywords ?? '')
                        .split(/[,，、\s]+/)
                        .map((s: string) => s.trim())
                        .filter(Boolean);
                      setRecallToSandbox({
                        chapter_id: values.chapter_id,
                        title: values.title,
                        keywords,
                        history_context: values.history_context,
                      });
                      message.success('已携带分镜素材跳往「练 · 沙盘推演」');
                      navigate('/sandbox');
                    }}
                  >
                    送入练模块 →
                  </Button>
                </Space>
              )
            }

          >
            {!storyboard && <Paragraph type="secondary">请先在左侧生成分镜。</Paragraph>}
            {loading && <Spin />}
            {storyboard && (
              <List
                itemLayout="vertical"
                dataSource={storyboard.shots}
                renderItem={(shot) => (
                  <List.Item key={shot.index}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space>
                        <Tag color="volcano">第 {shot.index + 1} 镜</Tag>
                        <Text strong>{shot.summary}</Text>
                        <Text type="secondary">{shot.duration_sec.toFixed(1)} 秒</Text>
                      </Space>
                      <Text code style={{ whiteSpace: 'pre-wrap' }}>
                        {shot.prompt.final_prompt}
                      </Text>
                      <Space wrap>
                        {shot.control_signals.map((c, i) => (
                          <Tag key={i} color="geekblue">
                            {c.kind} · {c.weight.toFixed(2)}
                          </Tag>
                        ))}
                      </Space>
                      <Text type="secondary">旁白：{shot.voiceover}</Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>

          <Divider />

          <Card title="渲染任务">
            {jobs.length === 0 && <Paragraph type="secondary">暂无任务。</Paragraph>}
            <List
              dataSource={jobs}
              renderItem={(job) => (
                <List.Item key={job.job_id}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Space>
                      <Text code>{job.job_id}</Text>
                      <Tag color={STATUS_COLOR[job.status] ?? 'default'}>{job.status}</Tag>
                      <Tag>{STAGE_LABEL[job.stage] ?? job.stage}</Tag>
                    </Space>
                    <Progress percent={Math.round(job.progress * 100)} size="small" />
                    {job.video_url && (
                      <Text type="success">输出：{job.video_url}</Text>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
