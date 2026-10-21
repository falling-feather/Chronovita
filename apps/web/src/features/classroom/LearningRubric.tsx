import { Select, Space, Tag } from 'antd';
import type { LearningRubric, RubricLevel } from '../../utils/api';

export const EMPTY_RUBRIC: LearningRubric = { facts: 'not_assessed', evidence: 'not_assessed', explanation: 'not_assessed' };
const LABELS: Record<RubricLevel, string> = { not_assessed: '暂未评价', needs_revision: '需要修改', developing: '逐步形成', supported: '有依据支持' };
const DIMENSIONS = [['facts', '史实与历史边界'], ['evidence', '材料与出处'], ['explanation', '判断与理由']] as const;

export function RubricEditor({ value, onChange, disabled }: { value: LearningRubric; onChange: (value: LearningRubric) => void; disabled?: boolean }) {
  return <Space wrap aria-label="三项人工评价" style={{ display: 'flex', margin: '16px 0' }}>
    {DIMENSIONS.map(([key, title]) => <label key={key}>{title}<Select aria-label={title} value={value[key]} disabled={disabled} style={{ display: 'block', width: 160 }}
      options={Object.entries(LABELS).map(([level, label]) => ({ value: level, label }))}
      onChange={(level: RubricLevel) => onChange({ ...value, [key]: level })} /></label>)}
    <small>教师人工判断，不是自动测验分数。</small>
  </Space>;
}

export function RubricSummary({ rubric }: { rubric: LearningRubric }) {
  return <Space wrap>{DIMENSIONS.map(([key, title]) => <Tag key={key}>{title}：{LABELS[rubric[key]]}</Tag>)}</Space>;
}
