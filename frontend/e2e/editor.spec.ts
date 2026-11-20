import { expect, test, type Page } from '@playwright/test';

import { login } from './helpers';

const CAMPAIGN_ID = '00000000-0000-0000-0000-000000000001';

const FAKE_CAMPAIGN = {
  id: CAMPAIGN_ID,
  kt_id: 999999,
  name: 'test_iudkin_fake_e2e',
  url: 'https://fake.example/abc',
  geo: ['MX', 'AU'],
  offer_id: 18813,
  created_at: '2026-11-19T12:00:00Z',
  synced_at: new Date(Date.now() - 2 * 60000).toISOString(),
  offers_count: 3,
};

function offer(
  offer_id: number,
  name: string,
  share: number,
  extra: Record<string, unknown> = {},
) {
  return {
    offer_id,
    name,
    share,
    pinned: false,
    active: true,
    ...extra,
  };
}

function fakeStreams(pushBlockReason: string | null, dirty = true) {
  return [
    {
      id: '00000000-0000-0000-0000-0000000000a2',
      kt_id: 1328759,
      name: 'Everyone else',
      position: 2,
      type: 'regular',
      schema: 'landings_offers',
      has_offers: true,
      filters: [],
      action_payload: null,
      dirty,
      push_block_reason: pushBlockReason,
      offers: [
        offer(11112, 'Oxys [BEAUTY-CL-BE_0155]', 34),
        offer(10009, 'Miaflow [BEAUTY-RO-BE_0009]', 33, { pinned: true }),
        offer(11111, 'FitoMishki [Weight Loss-CO-DT_0309]', 33),
        offer(10008, 'Miaflow [BEAUTY-RO-BE_0008]', 0, { active: false }),
      ],
    },
    {
      id: '00000000-0000-0000-0000-0000000000a1',
      kt_id: 1328758,
      name: 'Geo → Google',
      position: 1,
      type: 'regular',
      schema: 'redirect',
      has_offers: false,
      filters: [{ name: 'country', mode: 'accept', payload: ['MX', 'AU'] }],
      action_payload: 'google.com',
      dirty: false,
      push_block_reason: null,
      offers: [],
    },
  ];
}

async function stubApi(
  page: Page,
  pushBlockReason: string | null = null,
  dirty = true,
) {
  await page.route('**/api/campaigns', (route) =>
    route.fulfill({ json: [FAKE_CAMPAIGN] }),
  );
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/streams`, (route) =>
    route.fulfill({
      json: {
        campaign: FAKE_CAMPAIGN,
        streams: fakeStreams(pushBlockReason, dirty),
      },
    }),
  );
}

test('Edit offers opens the editor with the streams from the API', async ({
  page,
}) => {
  await stubApi(page);
  await login(page);
  await page
    .getByRole('row', { name: /test_iudkin_fake_e2e/ })
    .getByRole('link', { name: 'Edit offers' })
    .click();
  await expect(page).toHaveURL(`/campaigns/${CAMPAIGN_ID}`);
  await expect(
    page.getByRole('heading', { level: 1, name: FAKE_CAMPAIGN.name }),
  ).toBeVisible();
  await expect(page.getByText('Synced from Keitaro 2 min ago')).toBeVisible();

  await expect(page.getByRole('row', { name: /Oxys/ })).toContainText('34%');
  const removed = page.getByRole('row', { name: /REMOVED/ });
  await expect(
    removed.getByRole('button', { name: 'Bring back' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Push to KT' })).toBeEnabled();
  const geo = page.getByRole('region', { name: /Geo → Google/ });
  await expect(geo).toContainText('MX');
  await expect(geo).toContainText('google.com');

  // offer streams first, the read-only redirect stream at the bottom
  const regions = page.getByRole('region');
  await expect(regions.last()).toContainText('Geo → Google');
  await expect(regions.first()).toContainText('unsaved changes');
  // a dirty draft swaps Fetch for Push / Cancel
  await expect(page.getByRole('button', { name: 'Fetch from KT' })).toHaveCount(
    0,
  );

  await page.getByRole('link', { name: 'Campaigns' }).click();
  await expect(page).toHaveURL(/\/campaigns$/);
});

test('Push to KT is disabled with a hint when shares do not add up', async ({
  page,
}) => {
  await stubApi(page, 'sum_not_100');
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  const push = page.getByRole('button', { name: 'Push to KT' });
  await expect(push).toBeDisabled();
  await expect(push).toHaveAttribute('title', 'Shares must add up to 100%');
  // once in the header next to Push, once in the stream that needs fixing
  await expect(page.getByText('Shares must add up to 100%')).toHaveCount(2);
});

test('unknown campaign shows Campaign not found', async ({ page }) => {
  await page.route('**/api/campaigns/*/streams', (route) =>
    route.fulfill({ status: 404, json: { detail: 'Campaign not found' } }),
  );
  await login(page);
  await page.goto('/campaigns/11111111-1111-1111-1111-111111111111');
  await expect(page.getByText('Campaign not found')).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Back to campaigns' }),
  ).toBeVisible();
});

test('real backend: test_iudkin_test1 shows its streams', async ({ page }) => {
  await login(page);
  const row = page.getByRole('row', { name: /test_iudkin_test1/ });
  test.skip(
    (await row.count()) === 0,
    'campaign test_iudkin_test1 is not in GET /api/campaigns',
  );
  await row.getByRole('link', { name: 'Edit offers' }).click();
  await expect(
    page.getByRole('heading', { level: 1, name: 'test_iudkin_test1' }),
  ).toBeVisible();
  await expect(page.getByRole('row', { name: /18813/ })).toContainText('100%');
  await expect(
    page.getByRole('region', { name: /Geo → Google/ }),
  ).toBeVisible();
});

test('stubbed: Push to KT pushes the campaign and brings Fetch back', async ({
  page,
}) => {
  await stubApi(page);
  let pushed = 0;
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/push`, (route) => {
    pushed += 1;
    expect(route.request().method()).toBe('POST');
    const [offers, redirect] = fakeStreams(null, false);
    const clean = {
      ...offers,
      offers: [offer(11112, 'Oxys [BEAUTY-CL-BE_0155]', 100)],
    };
    return route.fulfill({
      json: { campaign: FAKE_CAMPAIGN, streams: [clean, redirect] },
    });
  });
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await page.getByRole('button', { name: 'Push to KT' }).click();
  await expect(page.getByText('unsaved changes')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Push to KT' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Cancel' })).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Fetch from KT' }),
  ).toBeVisible();
  await expect(page.getByRole('row', { name: /Oxys/ })).toContainText('100%');
  expect(pushed).toBe(1);
});

test('stubbed: Cancel drops the campaign draft', async ({ page }) => {
  await stubApi(page);
  let cancelled = 0;
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/cancel`, (route) => {
    cancelled += 1;
    return route.fulfill({
      json: { campaign: FAKE_CAMPAIGN, streams: fakeStreams(null, false) },
    });
  });
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('unsaved changes')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Fetch from KT' }),
  ).toBeVisible();
  expect(cancelled).toBe(1);
});

test('stubbed: a failed Push shows the server detail', async ({ page }) => {
  await stubApi(page);
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/push`, (route) =>
    route.fulfill({ status: 502, json: { detail: 'Keitaro error: 500 boom' } }),
  );
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await page.getByRole('button', { name: 'Push to KT' }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Keitaro error: 500 boom' }),
  ).toBeVisible();
  // the draft is still there to push again
  await expect(page.getByText('unsaved changes')).toBeVisible();
});

test('stubbed: Fetch from KT on a clean campaign reloads it', async ({
  page,
}) => {
  await stubApi(page, null, false);
  let fetched = 0;
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/fetch`, (route) => {
    fetched += 1;
    return route.fulfill({
      json: { campaign: FAKE_CAMPAIGN, streams: fakeStreams(null, false) },
    });
  });
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await expect(page.getByRole('button', { name: 'Push to KT' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Fetch from KT' }).click();
  await expect.poll(() => fetched).toBe(1);
});

test('stubbed: Fetch on a campaign deleted in Keitaro shows a message', async ({
  page,
}) => {
  await stubApi(page, null, false);
  await page.route(`**/api/campaigns/${CAMPAIGN_ID}/fetch`, (route) =>
    route.fulfill({
      status: 410,
      json: { detail: 'Campaign was deleted in Keitaro' },
    }),
  );
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await page.getByRole('button', { name: 'Fetch from KT' }).click();
  await expect(page.getByText('Campaign was deleted in Keitaro')).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Back to campaigns' }),
  ).toBeVisible();
});

test.describe('real backend: test_iudkin_test1 editor actions', () => {
  test.describe.configure({ mode: 'serial' });

  // Nothing here pushes: Push is never clicked against the real Keitaro.
  async function openReal(page: Page) {
    await login(page);
    const row = page.getByRole('row', { name: /test_iudkin_test1/ });
    test.skip(
      (await row.count()) === 0,
      'campaign test_iudkin_test1 is not in GET /api/campaigns',
    );
    await row.getByRole('link', { name: 'Edit offers' }).click();
    await expect(page.getByRole('row', { name: /18813/ })).toBeVisible();
    // start from Keitaro's state: drop any leftover draft, then reload
    const cancel = page.getByRole('button', { name: 'Cancel' });
    if (await cancel.count()) await cancel.click();
    // wait for the fetch itself: the page already shows 100% before it ends
    const fetched = page.waitForResponse((r) => r.url().endsWith('/fetch'));
    await page.getByRole('button', { name: 'Fetch from KT' }).click();
    await fetched;
    await expect(page.getByText('unsaved changes')).toHaveCount(0);
    await expect(page.getByRole('row', { name: /18813/ })).toContainText(
      '100%',
    );
    const stream = page
      .getByRole('region')
      .filter({ has: page.getByRole('row', { name: /18813/ }) });
    return { stream, row18813: stream.getByRole('row', { name: /18813/ }) };
  }

  test('pin and unpin toggle aria-pressed', async ({ page }) => {
    const { row18813 } = await openReal(page);
    await row18813.getByRole('button', { name: 'Pin share' }).click();
    const unpin = row18813.getByRole('button', { name: 'Unpin share' });
    await expect(unpin).toHaveAttribute('aria-pressed', 'true');
    await unpin.click();
    await expect(
      row18813.getByRole('button', { name: 'Pin share' }),
    ).toHaveAttribute('aria-pressed', 'false');
  });

  test('Remove blocks Push, Cancel restores', async ({ page }) => {
    const { stream, row18813 } = await openReal(page);
    await row18813.getByRole('button', { name: 'Remove' }).click();
    await expect(row18813).toContainText('REMOVED');
    await expect(row18813).toContainText('0%');
    const push = page.getByRole('button', { name: 'Push to KT' });
    await expect(push).toBeDisabled();
    await expect(push).toHaveAttribute('title', 'Add at least one offer');
    await expect(stream.getByText('unsaved changes')).toBeVisible();

    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(row18813).toContainText('100%');
    await expect(stream.getByText('unsaved changes')).toHaveCount(0);
  });

  test('Remove then Bring back returns to a clean 100%', async ({ page }) => {
    const { stream, row18813 } = await openReal(page);
    await row18813.getByRole('button', { name: 'Remove' }).click();
    await expect(row18813).toContainText('REMOVED');
    await row18813.getByRole('button', { name: 'Bring back' }).click();
    await expect(row18813).toContainText('100%');
    await expect(stream.getByText('unsaved changes')).toHaveCount(0);
  });

  test('Fetch from KT reloads a clean campaign', async ({ page }) => {
    const { row18813 } = await openReal(page);
    await page.getByRole('button', { name: 'Fetch from KT' }).click();
    await expect(row18813).toContainText('100%');
    await expect(page.getByText('unsaved changes')).toHaveCount(0);
  });
});

test('offer search menu is not hidden behind the stream cards', async ({
  page,
}) => {
  await stubApi(page);
  const searches: URL[] = [];
  await page.route('**/api/offers?*', (route) => {
    searches.push(new URL(route.request().url()));
    return route.fulfill({
      json: [
        { id: 900001, name: '900001 FAKE offer one' },
        { id: 900002, name: '900002 FAKE offer two' },
        { id: 900003, name: '900003 FAKE offer three' },
      ],
    });
  });
  await login(page);
  await page.goto(`/campaigns/${CAMPAIGN_ID}`);
  await page.getByLabel('Add offer').fill('fake');
  // The add row is at the very bottom of the card, so a clipped menu hides
  // even its first option. Check without scrolling (click() would scroll the
  // clipping card and mask the bug): what is painted at the option's centre
  // must be the option itself.
  const first = page.getByRole('option', { name: /900001/ });
  await expect(first).toBeVisible();
  const onTop = await first.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(
      r.x + r.width / 2,
      r.y + r.height / 2,
    );
    return hit !== null && el.contains(hit);
  });
  expect(onTop).toBe(true);
  await first.click();
  await expect(page.getByRole('button', { name: 'Add' })).toBeEnabled();
  // the editor asks the server to leave out offers already in this stream
  const streamId = fakeStreams(null).find((s) => s.has_offers)!.id;
  expect(searches.at(-1)?.searchParams.get('exclude_stream')).toBe(streamId);
});

test('real backend: an offer already in the stream is not offered again', async ({
  page,
}) => {
  await login(page);
  const row = page.getByRole('row', { name: /test_iudkin_test1/ });
  test.skip(
    (await row.count()) === 0,
    'campaign test_iudkin_test1 is not in GET /api/campaigns',
  );
  await row.getByRole('link', { name: 'Edit offers' }).click();
  await expect(page.getByRole('row', { name: /18813/ })).toBeVisible();
  // 18813 is the only offer we can see and it is already in the stream
  await page.getByLabel('Add offer').fill('flex');
  await expect(page.getByText('No offers')).toBeVisible();
});
