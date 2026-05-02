import { Empty, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function SandboxPage() {
  return (
    <div>
      <Title level={3} className="chrono-title">练 · 沙盘推演</Title>
      <Paragraph>基于有向无环图与状态压缩动态规划构建因果推演引擎，允许学生输入变量改变历史走向。</Paragraph>
      <Empty description="待 v1.2.0 接入「大禹治水」首发剧本" />
    </div>
  );
}
