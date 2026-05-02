import { Card, Col, Row, Steps, Typography } from 'antd';
import { Link } from 'react-router-dom';

const { Title, Paragraph } = Typography;

const modules = [
  { path: '/recall', name: '看 · 沉浸叙事', desc: '历史文本化作高保真微视频，身临其境溯源华夏。' },
  { path: '/sandbox', name: '练 · 沙盘推演', desc: '干预历史变量，于平行时空验证因果必然与偶然。' },
  { path: '/agent', name: '问 · 双模智者', desc: '历史人物同伴与考古专家无缝切换，跨时空对话。' },
  { path: '/canvas', name: '创 · 知识谱系', desc: '低代码画布编织个人知识脉络，从被动观看到主动创造。' },
  { path: '/classroom', name: '课 · 老师预设', desc: '老师预调初始变量、必经节点与合格终局，生成任务 ID 分享学生。' },
];

export default function HomePage() {
  return (
    <div>
      <Title level={2} className="chrono-title">让史册化作可推演的时空</Title>
      <Paragraph style={{ fontSize: 16, maxWidth: 720 }}>
        史脉以生成式人工智能驱动的「看 · 练 · 问 · 创」四段式实践教学，
        将固化的历史叙事重构为可干预、可量化、可创造的沙盘课堂。
      </Paragraph>
      <div className="chrono-divider" />
      <Row gutter={[24, 24]}>
        {modules.map((m) => (
          <Col key={m.path} xs={24} sm={12} lg={6}>
            <Link to={m.path}>
              <Card hoverable title={<span className="chrono-title">{m.name}</span>}>
                {m.desc}
              </Card>
            </Link>
          </Col>
        ))}
      </Row>

      <div className="chrono-divider" />
      <Card title={<span className="chrono-title">v1.5.0 · 全链路引导</span>} style={{ background: '#FBF6EC' }}>
        <Paragraph>
          四模块已贯通会话桥，按下列次序游历可一键串联整段课堂：
        </Paragraph>
        <Steps
          direction="horizontal"
          size="small"
          current={-1}
          items={[
            { title: '看', description: '生成分镜后点「送入练模块」' },
            { title: '练', description: '推演至终局后点「送入问模块」' },
            { title: '问', description: '获得双派论述后点「沉淀为创模块谱系」' },
            { title: '创', description: '自动生成论辩谱系节点与引证' },
          ]}
        />
      </Card>
    </div>
  );
}

