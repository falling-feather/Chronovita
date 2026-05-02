import { Empty, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function AgentPage() {
  return (
    <div>
      <Title level={3} className="chrono-title">问 · 双模智者</Title>
      <Paragraph>同时代历史人物同伴与考古专家无缝切换；以检索增强生成与三层防幻觉机制守护史实严谨。</Paragraph>
      <Empty description="待 v1.3.0 接入双 Persona 与语音通道" />
    </div>
  );
}
