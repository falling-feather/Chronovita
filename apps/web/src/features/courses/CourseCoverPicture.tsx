import type { CSSProperties } from 'react';
import {
  COURSE_COVER_META,
  courseCoverUrl,
  isCourseCoverId,
  type CourseCoverWidth,
} from './courseCoverAssets';

interface CourseCoverPictureProps {
  courseId: string;
  width?: CourseCoverWidth;
  eager?: boolean;
  className?: string;
  fallbackColor?: string;
}

export default function CourseCoverPicture({
  courseId,
  width = 720,
  eager = false,
  className = '',
  fallbackColor = '#5d665f',
}: CourseCoverPictureProps) {
  if (!isCourseCoverId(courseId)) {
    return (
      <span
        className={`chrono-course-cover-fallback ${className}`.trim()}
        style={{ backgroundColor: fallbackColor }}
        aria-hidden="true"
      />
    );
  }

  const height = Math.round((width * 9) / 16);
  const style = { '--course-cover-focus': COURSE_COVER_META[courseId].focus } as CSSProperties;

  return (
    <picture className={`chrono-course-cover-picture ${className}`.trim()} style={style} aria-hidden="true">
      <source srcSet={courseCoverUrl(courseId, width, 'avif')} type="image/avif" />
      <source srcSet={courseCoverUrl(courseId, width, 'webp')} type="image/webp" />
      <img
        src={courseCoverUrl(courseId, width, 'webp')}
        alt=""
        width={width}
        height={height}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
      />
    </picture>
  );
}
