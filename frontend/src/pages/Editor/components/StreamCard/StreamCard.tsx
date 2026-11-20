import { useState } from 'react';

import {
  useStreamAction,
  type OfferOption,
  type Stream,
} from '../../../../api';
import { OfferSelect } from '../../../../components/OfferSelect';
import { PUSH_HINTS } from '../../pushHints';
import { OfferRow } from './components/OfferRow';

import styles from './StreamCard.module.css';

type StreamCardProps = {
  campaignId: string;
  stream: Stream;
};

export function StreamCard({ campaignId, stream }: StreamCardProps) {
  const [offer, setOffer] = useState<OfferOption | null>(null);
  const action = useStreamAction(campaignId, stream.id);
  const busy = action.isPending;
  const pushHint = stream.push_block_reason
    ? PUSH_HINTS[stream.push_block_reason]
    : undefined;
  const addInputId = `add-offer-${stream.id}`;
  const headingId = `stream-${stream.id}`;
  const errorText = action.error?.message;
  const cardClass = stream.dirty ? styles.cardDirty : styles.card;

  return (
    <section aria-labelledby={headingId} className={cardClass}>
      <div className={styles.head}>
        <div>
          <h2 id={headingId} className={styles.title}>
            Offer <span className={styles.position}>#{stream.position}</span>
          </h2>
          <div className={styles.meta}>
            {stream.name} · stream {stream.kt_id}
            {stream.dirty && (
              <>
                {' · '}
                <span className={styles.dirty}>unsaved changes</span>
              </>
            )}
            {stream.dirty && pushHint && (
              <>
                {' · '}
                <span className={styles.hint}>{pushHint}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className={styles.tableBox}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.first}>Offer</th>
              <th className={styles.shareCol}>Share</th>
              <th className={styles.actionsCol}>
                <span className={styles.srOnly}>Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {stream.offers.map((o) => (
              <OfferRow
                key={o.offer_id}
                offer={o}
                disabled={busy}
                onPin={(pinned) =>
                  action.mutate({ type: 'pin', offerId: o.offer_id, pinned })
                }
                onRemove={() =>
                  action.mutate({ type: 'remove', offerId: o.offer_id })
                }
                onBringBack={() =>
                  action.mutate({ type: 'add', offerId: o.offer_id })
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.addRow}>
        <label htmlFor={addInputId} className={styles.srOnly}>
          Add offer
        </label>
        <div className={styles.select}>
          <OfferSelect
            inputId={addInputId}
            excludeStreamId={stream.id}
            value={offer}
            onChange={setOffer}
          />
        </div>
        <button
          type="button"
          className={styles.add}
          disabled={busy || offer === null}
          onClick={() => {
            if (!offer) return;
            action.mutate(
              { type: 'add', offerId: offer.id },
              { onSuccess: () => setOffer(null) },
            );
          }}
        >
          Add
        </button>
      </div>
      {errorText && (
        <p role="alert" className={styles.error}>
          {errorText}
        </p>
      )}
    </section>
  );
}
