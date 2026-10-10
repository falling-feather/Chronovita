import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Spin, Tag } from 'antd';
import { api, type Lesson } from '../utils/api';
import CourseCoverPicture from '../features/courses/CourseCoverPicture';
import { FLAGSHIP_LESSON_IDS, lessonInteractionReady } from '../features/classroom/classroomModel';

export default function PracticePage() {
  const nav = useNavigate();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    Promise.all(Array.from(FLAGSHIP_LESSON_IDS, (id) => api.lesson('C-prequin-state', id)))
      .then((items) => { if (active) setLessons(items); })
      .catch((failure) => { if (active) setError(failure instanceof Error ? failure.message : '课堂载入失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  return (
    <div className="chrono-practice-index">
      <header><p>HISTORY · DECISION LAB</p><h1>把判断放进历史情景</h1>
        <span>先读材料，再权衡选择；用依据解释结果，而不是寻找万能答案。</span></header>
      {error ? <Alert type="warning" showIcon message={error} action={<Button onClick={() => setRetry((n) => n + 1)}>重试</Button>} /> : null}
      {loading ? <div className="chrono-page-loading"><Spin /></div> : (
        <section className="chrono-practice-lessons">
          {lessons.map((lesson) => {
            const ready = lessonInteractionReady(lesson);
            const path = `/courses/${lesson.course_id}/lessons/${lesson.id}`;
            return (
              <article key={lesson.id}>
                <div className="chrono-practice-cover"><CourseCoverPicture courseId={lesson.course_id} /></div>
                <div className="chrono-practice-copy">
                  <Tag color={ready ? 'green' : 'default'}>{ready ? '互动已开放' : '互动适配中'}</Tag>
                  <h2>{lesson.title}</h2><p>{lesson.abstract}</p>
                  <footer>
                    <Button type="primary" disabled={!ready} onClick={() => nav(`${path}?layer=practice`)}>进入抉择</Button>
                    <Button disabled={!ready} onClick={() => nav(`${path}?layer=ask`)}>召见人物</Button>
                    <Button onClick={() => nav(`${path}?layer=watch`)}>阅读课文</Button>
                    <Button onClick={() => nav(`${path}?layer=create`)}>打开书案</Button>
                  </footer>
                </div>
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
