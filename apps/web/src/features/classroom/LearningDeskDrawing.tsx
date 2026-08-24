import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Segmented, Slider } from 'antd';
import {
  ClearOutlined,
  DeleteOutlined,
  EditOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import type { LearningDeskPoint, LearningDeskStroke } from './learningLedger';

const COLORS = ['#24302f', '#8f2f2f', '#3f7968', '#b27a2f'] as const;

function newStrokeId(): string {
  return `stroke:${Date.now().toString(36)}:${Math.random().toString(36).slice(2)}`;
}

function drawStroke(
  context: CanvasRenderingContext2D,
  stroke: LearningDeskStroke,
  width: number,
  height: number,
) {
  if (stroke.points.length === 0) return;
  context.save();
  context.globalCompositeOperation = stroke.mode === 'erase' ? 'destination-out' : 'source-over';
  context.strokeStyle = stroke.color;
  context.lineWidth = stroke.width;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  const first = stroke.points[0];
  context.moveTo(first.x * width, first.y * height);
  for (const point of stroke.points.slice(1)) {
    context.lineTo(point.x * width, point.y * height);
  }
  if (stroke.points.length === 1) {
    context.lineTo(first.x * width + 0.01, first.y * height + 0.01);
  }
  context.stroke();
  context.restore();
}

export default function LearningDeskDrawing({
  strokes,
  onChange,
}: {
  strokes: LearningDeskStroke[];
  onChange: (strokes: LearningDeskStroke[]) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<LearningDeskStroke | null>(null);
  const [mode, setMode] = useState<'ink' | 'erase'>('ink');
  const [color, setColor] = useState<(typeof COLORS)[number]>('#24302f');
  const [width, setWidth] = useState(4);
  const [drawing, setDrawing] = useState(false);

  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    if (!canvas || !stage) return;
    const rect = stage.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    const pixelWidth = Math.max(1, Math.round(rect.width * scale));
    const pixelHeight = Math.max(1, Math.round(rect.height * scale));
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
    }
    const context = canvas.getContext('2d');
    if (!context) return;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);
    strokes.forEach((stroke) => drawStroke(context, stroke, rect.width, rect.height));
    if (activeRef.current) drawStroke(context, activeRef.current, rect.width, rect.height);
  }, [strokes]);

  useEffect(() => {
    paint();
    const stage = stageRef.current;
    if (!stage) return undefined;
    const observer = new ResizeObserver(paint);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [paint]);

  const pointForEvent = (event: React.PointerEvent<HTMLCanvasElement>): LearningDeskPoint => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(rect.width, 1))),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(rect.height, 1))),
    };
  };

  const start = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    event.currentTarget.setPointerCapture(event.pointerId);
    activeRef.current = {
      stroke_id: newStrokeId(),
      color,
      width: mode === 'erase' ? Math.max(width * 3, 12) : width,
      mode,
      points: [pointForEvent(event)],
    };
    setDrawing(true);
    paint();
  };

  const move = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const stroke = activeRef.current;
    if (!stroke) return;
    const next = pointForEvent(event);
    const previous = stroke.points.at(-1);
    if (previous && Math.hypot(next.x - previous.x, next.y - previous.y) < 0.0015) return;
    stroke.points.push(next);
    paint();
  };

  const finish = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const stroke = activeRef.current;
    if (!stroke) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    activeRef.current = null;
    setDrawing(false);
    onChange([...strokes, stroke]);
  };

  return (
    <section className="chrono-desk-drawing" aria-label="手写与绘图">
      <header className="chrono-desk-drawing-toolbar">
        <Segmented
          aria-label="画笔模式"
          value={mode}
          onChange={(value) => setMode(value as 'ink' | 'erase')}
          options={[
            { label: <span><EditOutlined /> 落笔</span>, value: 'ink' },
            { label: <span><ClearOutlined /> 擦除</span>, value: 'erase' },
          ]}
        />
        <div className="chrono-desk-ink-colors" aria-label="墨色">
          {COLORS.map((item) => (
            <button
              type="button"
              key={item}
              style={{ '--ink-color': item } as React.CSSProperties}
              className={color === item ? 'active' : ''}
              aria-label={`选择墨色 ${item}`}
              aria-pressed={color === item}
              onClick={() => { setColor(item); setMode('ink'); }}
            />
          ))}
        </div>
        <label className="chrono-desk-stroke-width">
          <span>笔锋</span>
          <Slider min={2} max={14} value={width} onChange={setWidth} />
        </label>
        <Button
          icon={<UndoOutlined />}
          disabled={strokes.length === 0 || drawing}
          onClick={() => onChange(strokes.slice(0, -1))}
        >撤回</Button>
        <Button
          icon={<DeleteOutlined />}
          disabled={strokes.length === 0 || drawing}
          onClick={() => onChange([])}
        >清空</Button>
      </header>
      <div ref={stageRef} className="chrono-desk-drawing-stage">
        <canvas
          ref={canvasRef}
          aria-label="可以使用鼠标、触控笔或手指书写的画布"
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={finish}
          onPointerCancel={finish}
        />
        {strokes.length === 0 && !drawing ? (
          <div className="chrono-desk-drawing-empty" aria-hidden="true">
            <span>在纸上落笔</span>
            <p>支持鼠标、触控笔与触屏；笔迹仅保存为本课的归一化线条。</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
