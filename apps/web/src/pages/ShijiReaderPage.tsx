import { useMemo } from 'react';
import './ShijiReaderPage.css';

/**
 * The complete historical reader is the migrated Vue reader from 史海.
 * It runs inside the current React shell so Chronovita keeps its own account
 * header while the reader retains its catalog, document pane, settings,
 * scan page, encyclopedia and floating assistant interactions.
 */
export default function ShijiReaderPage() {
  const source = useMemo(() => `${import.meta.env.BASE_URL}shiji-reader/index.html`, []);
  return (
    <main className="chrono-shiji-reader-embed" aria-label="《史记》完整文献阅读器">
      <iframe title="《史记》完整文献阅读器" src={source} allow="fullscreen" />
    </main>
  );
}
