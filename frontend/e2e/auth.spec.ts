import { expect, test } from '@playwright/test';

import { login } from './helpers';

test('unauthenticated /campaigns redirects to /login', async ({ page }) => {
  await page.goto('/campaigns');
  await expect(page).toHaveURL(/\/login$/);
});

test('wrong password shows an error', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Login').fill(process.env.APP_LOGIN!);
  await page.getByLabel('Password').fill('definitely-wrong-password');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('alert')).toHaveText('Invalid login or password');
  await expect(page).toHaveURL(/\/login$/);
});

test('login lands on campaigns and survives reload', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('heading', { name: 'Campaigns' })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/campaigns$/);
  await expect(page.getByRole('heading', { name: 'Campaigns' })).toBeVisible();
});

test('logged in user opening /login is redirected to /campaigns', async ({
  page,
}) => {
  await login(page);
  await page.goto('/login');
  await expect(page).toHaveURL(/\/campaigns$/);
});

test('log out returns to /login and protects /campaigns', async ({ page }) => {
  await login(page);
  await page.getByRole('link', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/campaigns');
  await expect(page).toHaveURL(/\/login$/);
});

test('expired access token is silently refreshed', async ({
  page,
  context,
}) => {
  await login(page);
  await context.clearCookies({ name: 'access_token' });
  expect((await context.cookies()).some((c) => c.name === 'access_token')).toBe(
    false,
  );
  await page.reload();
  await expect(page).toHaveURL(/\/campaigns$/);
  await expect(page.getByRole('heading', { name: 'Campaigns' })).toBeVisible();
  await expect
    .poll(async () =>
      (await context.cookies()).some((c) => c.name === 'access_token'),
    )
    .toBe(true);
});
