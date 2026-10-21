export const IS_STATIC_PREVIEW = import.meta.env.MODE === 'pages'
  || import.meta.env.VITE_STATIC_PREVIEW === 'true';

/**
 * Resolve files from Vite's public directory under both `/` and a GitHub Pages
 * repository sub-path. External/data/blob URLs pass through unchanged.
 */
export function publicAssetUrl(path: string): string {
  if (!path || /^(?:[a-z]+:|\/\/)/i.test(path)) return path;
  const clean = path.replace(/^\.?\/+/, '');
  return `${import.meta.env.BASE_URL}${clean}`;
}

export function publicAssetSrcSet(srcSet: string): string {
  return srcSet
    .split(',')
    .map((candidate) => {
      const [url, ...descriptor] = candidate.trim().split(/\s+/);
      return [publicAssetUrl(url), ...descriptor].join(' ');
    })
    .join(', ');
}
