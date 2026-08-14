import { Alert, Tag } from 'antd';
import {
  BookOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import type { RagAnswer, RagCitation } from '../../utils/api';

const SOURCE_LABEL: Record<RagAnswer['answer_source'], string> = {
  model: '模型据证据组织',
  extractive: '本地抽取式回答',
  insufficient_evidence: '依据不足',
};

const UNCERTAINTY_LABEL: Record<RagAnswer['uncertainty'], string> = {
  low: '较低', medium: '中等', high: '较高',
};

const CERTAINTY_LABEL: Record<RagCitation['certainty'], string> = {
  consensus: '通行认识',
  interpretation: '教学解释',
  legend: '传说叙事',
  disputed: '存在争议',
};

export default function RagAnswerCard({
  answer,
  compact = false,
}: {
  answer: RagAnswer;
  compact?: boolean;
}) {
  const insufficient = answer.answer_source === 'insufficient_evidence';
  return (
    <article className={`chrono-rag-answer${compact ? ' compact' : ''}`} aria-label="课程证据回答">
      <header>
        <div>
          {insufficient ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
          <strong>{SOURCE_LABEL[answer.answer_source]}</strong>
        </div>
        <Tag color={answer.uncertainty === 'high' ? 'orange' : answer.uncertainty === 'low' ? 'green' : 'gold'}>
          不确定性 {UNCERTAINTY_LABEL[answer.uncertainty]}
        </Tag>
      </header>

      <p className="chrono-rag-body">{answer.body}</p>

      {answer.role_disclaimer ? (
        <Alert
          className="chrono-rag-disclaimer"
          type="info"
          showIcon
          message={answer.role_disclaimer}
        />
      ) : null}

      {answer.citations.length > 0 ? (
        <section className="chrono-rag-citations" aria-label="引用片段">
          <h3><FileSearchOutlined /> 引用片段</h3>
          {answer.citations.slice(0, compact ? 2 : undefined).map((citation, index) => (
            <blockquote key={citation.citation_id}>
              <div>
                <span>[{index + 1}] {citation.source_title}</span>
                <Tag>{CERTAINTY_LABEL[citation.certainty]}</Tag>
              </div>
              <p>{citation.excerpt}</p>
              {citation.locator ? <cite>{citation.locator}</cite> : null}
            </blockquote>
          ))}
        </section>
      ) : null}

      <footer>
        <span><BookOutlined /> 发布 #{answer.release_no}</span>
        <span>证据库 v{answer.evidence_version}</span>
        <code title={answer.evidence_checksum}>校验 {answer.evidence_checksum.slice(0, 10)}</code>
      </footer>
    </article>
  );
}
