import type { CSSProperties } from 'react';
import {
  COURSE_COVER_META,
  courseCoverUrl,
  resolveCourseCoverId,
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
  const coverId = resolveCourseCoverId(courseId);
  if (!coverId) {
    return (
      <span
        className={`chrono-course-cover-fallback ${className}`.trim()}
        style={{ backgroundColor: fallbackColor }}
        aria-hidden="true"
      />
    );
  }

  const height = Math.round((width * 9) / 16);
  const style = { '--course-cover-focus': COURSE_COVER_META[coverId].focus } as CSSProperties;

  return (
    <picture className={`chrono-course-cover-picture ${className}`.trim()} style={style} aria-hidden="true">
      <source srcSet={courseCoverUrl(coverId, width, 'avif')} type="image/avif" />
      <source srcSet={courseCoverUrl(coverId, width, 'webp')} type="image/webp" />
      <img
        src={courseCoverUrl(coverId, width, 'webp')}
        alt=""
        width={width}
        height={height}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
      />
    </picture>
  );
}
