import { expect, request, type FullConfig } from '@playwright/test';

type Role = 'student' | 'teacher' | 'reviewer';

const PROJECT_SUFFIXES = ['laptop', 'fullhd'] as const;

function accounts(): Array<{ username: string; displayName: string; role: Role }> {
  const records: Array<{ username: string; displayName: string; role: Role }> = [];
  for (const suffix of PROJECT_SUFFIXES) {
    records.push(
      { username: `student.l101.${suffix}`, displayName: `L101 ${suffix} 学生`, role: 'student' },
      { username: `student.l103.${suffix}`, displayName: `L103 ${suffix} 学生`, role: 'student' },
      { username: `student.guard.${suffix}`, displayName: `${suffix} 权限学生`, role: 'student' },
      { username: `teacher.e2e.${suffix}`, displayName: `${suffix} 教师`, role: 'teacher' },
      { username: `reviewer.e2e.${suffix}`, displayName: `${suffix} 审校者`, role: 'reviewer' },
    );
  }
  return records;
}

export default async function globalSetup(config: FullConfig) {
  const baseURL = String(config.projects[0]?.use.baseURL || '').replace(/\/$/, '');
  if (!baseURL) throw new Error('CHRONO_E2E_BASE_URL is required.');

  const adminUsername = process.env.CHRONO_E2E_ADMIN_USERNAME || 'classroom.admin';
  const adminPassword = process.env.CHRONO_E2E_ADMIN_PASSWORD;
  const userPassword = process.env.CHRONO_E2E_USER_PASSWORD;
  if (!adminPassword || !userPassword) {
    throw new Error('E2E account passwords must be provided through process-only environment variables.');
  }

  const api = await request.newContext({
    baseURL,
    extraHTTPHeaders: { Origin: baseURL },
  });
  try {
    const health = await api.get('/healthz');
    expect(health.ok()).toBeTruthy();
    expect(await health.json()).toMatchObject({ status: 'alive' });

    const authConfig = await api.get('/api/v1/auth/config');
    expect(authConfig.ok()).toBeTruthy();
    expect(await authConfig.json()).toEqual({
      mode: 'accounts',
      browser_transport: 'http-only-cookie',
    });

    const login = await api.post('/api/v1/auth/login', {
      data: { username: adminUsername, password: adminPassword },
    });
    const loginText = await login.text();
    expect(login.ok(), loginText).toBeTruthy();
    const loginBody = JSON.parse(loginText);
    expect(loginBody).not.toHaveProperty('access_token');
    expect(loginBody).toMatchObject({
      transport: 'cookie',
      principal: { roles: ['admin'] },
    });

    for (const account of accounts()) {
      const created = await api.post('/api/v1/auth/users', {
        data: {
          username: account.username,
          password: userPassword,
          display_name: account.displayName,
          roles: [account.role],
        },
      });
      expect(
        [201, 409],
        `${account.username}: ${created.status()} ${await created.text()}`,
      ).toContain(created.status());
    }
  } finally {
    await api.dispose();
  }
}
