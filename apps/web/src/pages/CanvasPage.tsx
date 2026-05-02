import { Empty, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function CanvasPage() {
  return (
    <div>
      <Title level={3} className="chrono-title">创 · 知识谱系</Title>
      <Paragraph>低代码拖拽画布，将交互过程中的素材转化为个人知识谱系图与课程总结。</Paragraph>
      <Empty description="待 v1.4.0 迁移既有节点渲染引擎" />
    </div>
  );
}
