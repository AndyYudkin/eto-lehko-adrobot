import { expect, type Page } from '@playwright/test';

export async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Login').fill(process.env.APP_LOGIN!);
  await page.getByLabel('Password').fill(process.env.APP_PASSWORD!);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/campaigns$/);
}
