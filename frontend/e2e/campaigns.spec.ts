import { expect, test, type Page } from '@playwright/test';

import { login } from './helpers';

const closers: [
  string,
  (page: import('@playwright/test').Page) => Promise<void>,
][] = [
  ['x button', (p) => p.getByRole('button', { name: 'Close' }).click()],
  ['Cancel', (p) => p.getByRole('button', { name: 'Cancel' }).click()],
  ['Escape', (p) => p.keyboard.press('Escape')],
  ['overlay click', (p) => p.mouse.click(5, 5)],
];

for (const [name, close] of closers) {
  test(`new campaign dialog closes via ${name}`, async ({ page }) => {
    await login(page);
    await page.getByRole('button', { name: 'New campaign' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await close(page);
    await expect(page.getByRole('dialog')).toBeHidden();
  });
}

const FAKE_CAMPAIGN = {
  id: '00000000-0000-0000-0000-000000000001',
  kt_id: 999999,
  name: 'test_iudkin_fake_e2e',
  url: 'https://fake.example/abc',
  geo: ['MX', 'AU'],
  offer_id: 18813,
  created_at: '2026-11-19T12:00:00Z',
};

async function openDialog(page: Page) {
  await login(page);
  await page.getByRole('button', { name: 'New campaign' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
}

async function fillGeo(page: Page, text: string) {
  const geo = page.getByLabel('Geo');
  await geo.fill(text);
  await geo.press('Enter');
}

async function pickOffer(page: Page) {
  await page.getByLabel('Offer', { exact: true }).fill('flex');
  await page.getByRole('option', { name: /#18813/ }).click();
}

async function fillAll(page: Page) {
  await page.getByLabel('Name').fill('fake_e2e');
  await fillGeo(page, 'mx');
  await fillGeo(page, 'au');
  await pickOffer(page);
}

// never let a test create a real campaign in Keitaro
async function stubCreate(
  page: Page,
  status: number,
  body: unknown,
  onBody?: (data: unknown) => void,
) {
  let created = false;
  await page.route('**/api/campaigns', async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      onBody?.(request.postDataJSON());
      created = true;
      await route.fulfill({ status, json: body });
    } else if (created && status === 201) {
      await route.fulfill({ json: [FAKE_CAMPAIGN] });
    } else {
      await route.continue();
    }
  });
}

test('list shows a campaign row with geo, no Keitaro link', async ({
  page,
}) => {
  await page.route('**/api/campaigns', (route) =>
    route.fulfill({ json: [FAKE_CAMPAIGN] }),
  );
  await login(page);
  const row = page.getByRole('row', { name: /test_iudkin_fake_e2e/ });
  await expect(row).toBeVisible();
  await expect(row.getByRole('link')).toHaveCount(1);
  await expect(row.getByRole('link')).toHaveText('Edit offers');
  await expect(row).not.toContainText('fake.example');
  await expect(row).toContainText('MX');
});

test('geo chips: add, paste, backspace, reject', async ({ page }) => {
  await openDialog(page);
  const chips = page.getByRole('dialog').getByRole('button', {
    name: /^Remove /,
  });
  await fillGeo(page, 'mx');
  await expect(chips).toHaveText(['×']);
  await expect(page.getByRole('button', { name: 'Remove MX' })).toBeVisible();

  const geo = page.getByLabel('Geo');
  await geo.focus();
  await page.evaluate(() => {
    const input = document.getElementById('geo')!;
    const data = new DataTransfer();
    data.setData('text/plain', 'au, RO,au');
    input.dispatchEvent(
      new ClipboardEvent('paste', {
        clipboardData: data,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  await expect(chips).toHaveCount(3);
  await expect(page.getByRole('button', { name: 'Remove RO' })).toBeVisible();

  await geo.press('Backspace');
  await expect(page.getByRole('button', { name: 'Remove RO' })).toBeHidden();
  await expect(chips).toHaveCount(2);

  await fillGeo(page, 'MEX');
  await expect(page.getByText('Use 2-letter codes')).toBeVisible();
  await expect(chips).toHaveCount(2);
});

test('offer search finds the real offer; unknown shows No offers', async ({
  page,
}) => {
  await openDialog(page);
  const offer = page.getByLabel('Offer', { exact: true });
  await offer.fill('flex');
  const option = page.getByRole('option', { name: /^#18813 / });
  await expect(option).toBeVisible();
  await option.click();
  await expect(page.getByRole('dialog')).toContainText('#18813');

  await offer.fill('zzz');
  await expect(page.getByText('No offers')).toBeVisible();
});

test('Create is disabled until name, geo and offer are set', async ({
  page,
}) => {
  await openDialog(page);
  const create = page.getByRole('button', { name: 'Create', exact: true });
  await expect(create).toBeDisabled();
  await page.getByLabel('Name').fill('fake_e2e');
  await expect(create).toBeDisabled();
  await fillGeo(page, 'mx');
  await expect(create).toBeDisabled();
  await pickOffer(page);
  await expect(create).toBeEnabled();
});

test('create happy path (stubbed): body, closes, new row', async ({ page }) => {
  let body: unknown;
  await stubCreate(page, 201, FAKE_CAMPAIGN, (data) => (body = data));
  await openDialog(page);
  await fillAll(page);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  expect(body).toEqual({
    name: 'fake_e2e',
    geo: ['MX', 'AU'],
    offer_id: 18813,
  });
  await expect(
    page.getByRole('row', { name: /test_iudkin_fake_e2e/ }),
  ).toBeVisible();
});

test('create error (stubbed 502) keeps dialog open with the detail', async ({
  page,
}) => {
  const detail = 'Keitaro error: 422 bad stream';
  await stubCreate(page, 502, { detail });
  await openDialog(page);
  await fillAll(page);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveText(detail);
  await expect(page.getByRole('dialog')).toBeVisible();
});
