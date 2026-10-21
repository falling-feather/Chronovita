import { describe, expect, it } from 'vitest';
import packageInfo from '../package.json';
import { APP_VERSION, APP_VERSION_LABEL } from './version';

describe('frontend version fact source', () => {
  it('renders the package version instead of a page-level hardcoded label', () => {
    expect(APP_VERSION).toBe(packageInfo.version);
    expect(APP_VERSION_LABEL).toBe(`V${packageInfo.version}`);
  });
});
