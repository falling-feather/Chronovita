import { useEffect, useId, useState } from 'react';
import {
  DownOutlined,
  FileTextOutlined,
  UpOutlined,
} from '@ant-design/icons';
import type { RagAnswer, RagCitation } from '../../utils/api';
import {
  answerBoundaryNote,
  evidenceDisclosureLabel,
  studentAnswerOrigin,
} from './askPresentation';

const CERTAINTY_LABEL: Record<RagCitation['certainty'], string> = {
  consensus: '通行认识',
  interpretation: '教学解释',
  legend: '传说叙事',
  disputed: '仍有争议',
};

export default function RagAnswerCard({
  answer,
  compact = false,
  speakerName = '课程学者',
  speakerRole = '依据本课材料作答',
  defaultCitationsOpen = false,
}: {
  answer: RagAnswer;
  compact?: boolean;
  speakerName?: string;
  speakerRole?: string;
  defaultCitationsOpen?: boolean;
}) {
  const citationRegionId = useId();
  const [citationsOpen, setCitationsOpen] = useState(defaultCitationsOpen);
  const insufficient = answer.answer_source === 'insufficient_evidence';
  const citations = compact ? answer.citations.slice(0, 2) : answer.citations;

  useEffect(() => {
    setCitationsOpen(defaultCitationsOpen);
  }, [answer.evidence_checksum, answer.body, defaultCitationsOpen]);

  if (compact) {
    return (
      <article className={`chrono-ask-answer compact${insufficient ? ' is-insufficient' : ''}`} aria-label="课程材料回答">
        <header className="chrono-ask-answer-speaker">
          <span aria-hidden="true">{insufficient ? '？' : '史'}</span>
          <div>
            <strong>{speakerName}</strong>
            <small>{studentAnswerOrigin(answer)}</small>
          </div>
        </header>
        <p className="chrono-ask-answer-body">{answer.body}</p>
        {answer.role_disclaimer ? <p className="chrono-ask-role-note">{answer.role_disclaimer}</p> : null}
        <footer><FileTextOutlined /> {answer.citations.length} 条本课材料</footer>
      </article>
    );
  }

  return (
    <article className={`chrono-ask-answer${insufficient ? ' is-insufficient' : ''}`} aria-label={`${speakerName}的课程材料回答`}>
      <header className="chrono-ask-answer-speaker">
        <span aria-hidden="true">{insufficient ? '？' : '史'}</span>
        <div>
          <strong>{speakerName}</strong>
          <small>{speakerRole} · {studentAnswerOrigin(answer)}</small>
        </div>
      </header>

      <p className="chrono-ask-answer-body">{answer.body}</p>

      <p className={`chrono-ask-boundary${insufficient ? ' is-insufficient' : ''}`}>
        {answerBoundaryNote(answer)}
      </p>

      {answer.role_disclaimer ? (
        <p className="chrono-ask-role-note">{answer.role_disclaimer}</p>
      ) : null}

      <button
        type="button"
        className="chrono-ask-citation-toggle"
        aria-expanded={citationsOpen}
        aria-controls={citationRegionId}
        disabled={citations.length === 0}
        onClick={() => setCitationsOpen((open) => !open)}
      >
        <span><FileTextOutlined /> {evidenceDisclosureLabel(citations.length)}</span>
        {citations.length > 0 ? (citationsOpen ? <UpOutlined /> : <DownOutlined />) : null}
      </button>

      {citationsOpen && citations.length > 0 ? (
        <section id={citationRegionId} className="chrono-ask-citations" aria-label="本次回答采用的材料">
          {citations.map((citation, index) => (
            <blockquote key={citation.citation_id}>
              <header>
                <span>{index + 1}</span>
                <div>
                  <strong>{citation.source_title}</strong>
                  <small>{CERTAINTY_LABEL[citation.certainty]}{citation.locator ? ` · ${citation.locator}` : ''}</small>
                </div>
              </header>
              <p>{citation.excerpt}</p>
            </blockquote>
          ))}
        </section>
      ) : null}
    </article>
  );
}
