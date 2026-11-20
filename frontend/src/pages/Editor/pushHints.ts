import type { PushBlockReason } from '../../api';

export const PUSH_HINTS: Record<PushBlockReason, string> = {
  no_offers: 'Add at least one offer',
  sum_not_100: 'Shares must add up to 100%',
};
