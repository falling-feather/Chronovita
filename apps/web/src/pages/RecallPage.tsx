import { Empty, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function RecallPage() {
  return (
    <div>
      <Title level={3} className="chrono-title">看 · 沉浸叙事</Title>
      <Paragraph>历史文本解析 → 关键帧生成 → 动态镜头插帧 → 声线克隆，输出符合教学大纲的高质量微视频。</Paragraph>
      <Empty description="待 v1.1.0 接入 Prompt 链与 ControlNet 工作流" />
    </div>
  );
}
