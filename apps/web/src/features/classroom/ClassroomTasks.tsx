import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Empty, Input, Select, Space, Tag } from 'antd';
import { useAuth } from '../../auth/AuthContext';
import { api, type ClassroomTask, type ClassroomTaskListItem } from '../../utils/api';
import { createClientFeedbackId } from './learningSubmission';

const taskError = (failure: unknown) => failure instanceof Error ? failure.message : '课堂任务暂不可用';

export function TeacherClassroomTasks() {
  const auth = useAuth();
  const [items, setItems] = useState<ClassroomTaskListItem[]>([]);
  const [destinations, setDestinations] = useState<Array<{ value: string; label: string; courseId: string; lessonId: string }>>([]);
  const [destination, setDestination] = useState('');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [editing, setEditing] = useState<ClassroomTask | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const clientId = useRef(createClientFeedbackId());
  useEffect(() => {
    let current = true;
    void Promise.all([api.readerDestinations(), api.classroomReviewTasks()]).then(([choices, response]) => {
      if (current) { setDestinations(choices); setItems(response.items); }
    }).catch((failure) => { if (current) setError(taskError(failure)); });
    return () => { current = false; };
  }, []);

  const publish = async (close?: ClassroomTask) => {
    if (saving) return;
    const selected = destinations.find((item) => item.value === destination);
    if (!close && (!selected || !title.trim() || !prompt.trim())) return;
    setSaving(true); setError('');
    try {
      const previous = close || editing;
      const response = await api.classroomSaveTask({
        client_task_id: previous?.client_task_id || clientId.current,
        course_id: close?.course_id || selected!.courseId, lesson_id: close?.lesson_id || selected!.lessonId,
        title: close?.title || title.trim(), prompt: close?.prompt || prompt.trim(), status: close ? 'closed' : 'open',
        expected_checksum: previous?.checksum,
      });
      setItems((current) => [{ task: response.task, text_current: true }, ...current.filter((item) => item.task.task_id !== response.task.task_id)]);
      if (!close) { setTitle(''); setPrompt(''); setEditing(null); clientId.current = createClientFeedbackId(); }
    } catch (failure) { setError(taskError(failure)); }
    finally { setSaving(false); }
  };
  return <section className="chrono-review-feedback-composer" aria-label="课堂任务管理">
    <h2>课堂任务</h2><p>学生在书案中明确选择任务并上传；不会读取未提交的私人草稿。</p>
    {error ? <Alert type="warning" message={error} showIcon /> : null}
    <Select aria-label="任务课时" placeholder="选择课时" style={{ width: '100%' }} options={destinations}
      showSearch optionFilterProp="label" value={destination || undefined} onChange={setDestination} disabled={saving} />
    <Input aria-label="课堂任务标题" placeholder="任务标题" value={title} maxLength={160} onChange={(event) => setTitle(event.target.value)} disabled={saving} />
    <Input.TextArea aria-label="课堂任务要求" placeholder="写清需要学生作出的判断、引用的材料和解释的理由" value={prompt} maxLength={4000} rows={3} onChange={(event) => setPrompt(event.target.value)} disabled={saving} />
    <Space><Button type="primary" loading={saving} disabled={!destination || !title.trim() || !prompt.trim()} onClick={() => void publish()}>{editing ? '发布修订任务' : '发布课堂任务'}</Button>
      {editing ? <Button onClick={() => { setEditing(null); setTitle(''); setPrompt(''); }}>取消编辑</Button> : null}</Space>
    {items.length ? items.map(({ task, text_current }) => <article key={task.task_id} style={{ borderTop: '1px solid #ddd', padding: '16px 0' }}>
      <strong>{task.title}</strong> <Tag>{task.lesson_id} · 第{task.revision}版</Tag><Tag>{task.status === 'open' ? '开放' : '已关闭'}</Tag>
      {!text_current ? <Tag color="orange">对应课文已更新</Tag> : null}
      <p style={{ whiteSpace: 'pre-wrap' }}>{task.prompt}</p><small>{task.teacher_display_name}</small>
      {task.teacher_id === auth.principal?.user_id ? <Space style={{ marginLeft: 16 }}>
        <Button size="small" disabled={saving} onClick={() => { setEditing(task); setDestination(`${task.course_id}/${task.lesson_id}`); setTitle(task.title); setPrompt(task.prompt); }}>编辑任务</Button>
        {task.status === 'open' ? <Button size="small" disabled={saving} onClick={() => void publish(task)}>关闭任务</Button> : null}
      </Space> : null}
    </article>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未发布任务" />}
  </section>;
}

export function StudentClassroomTasks({ courseId, lessonId, selected, onSelect, locked = false }: {
  courseId: string; lessonId: string; selected: ClassroomTask | null; onSelect: (task: ClassroomTask | null) => void; locked?: boolean;
}) {
  const [items, setItems] = useState<ClassroomTaskListItem[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setItems([]); setError(''); onSelect(null);
    void api.classroomTasks(courseId, lessonId).then((response) => { if (current) setItems(response.items); })
      .catch(() => { if (current) setError('课堂任务暂不可读取；私人笔记仍可编辑保存，稍后再刷新任务。'); });
    return () => { current = false; };
  }, [courseId, lessonId]);
  const available = items.filter(({ task, text_current }) => task.status === 'open' && text_current);
  return <section className="chrono-desk-task" aria-label="本课课堂任务">
    {error ? <Alert type="info" message={error} /> : null}
    <Select aria-label="选择提交的课堂任务" style={{ width: '100%' }} value={selected?.task_id || ''} disabled={locked}
      options={[{ value: '', label: '自主学习成果（不绑定教师任务）' }, ...available.map(({ task }) => ({ value: task.task_id, label: task.title })),
        ...(selected && !available.some(({ task }) => task.task_id === selected.task_id) ? [{value: selected.task_id, label: selected.title}] : [])]}
      onChange={(id) => onSelect(available.find(({ task }) => task.task_id === id)?.task || null)} />
    {selected ? <p style={{ whiteSpace: 'pre-wrap' }}><strong>{selected.teacher_display_name} · 第{selected.revision}版任务：</strong>{selected.prompt}</p> : null}
    {items.some((item) => !item.text_current) ? <small>旧课文任务已隐藏，等待教师修订。</small> : null}
  </section>;
}
