import type { StreamOffer } from '../../../../../../api';

import styles from './OfferRow.module.css';

type OfferRowProps = {
  offer: StreamOffer;
  disabled: boolean;
  onPin: (pinned: boolean) => void;
  onRemove: () => void;
  onBringBack: () => void;
};

export function OfferRow({
  offer,
  disabled,
  onPin,
  onRemove,
  onBringBack,
}: OfferRowProps) {
  const label = (
    <>
      <span className={styles.id}>#{offer.offer_id}</span> {offer.name}
    </>
  );

  if (!offer.active) {
    return (
      <tr className={styles.removed}>
        <td className={styles.first}>
          <span className={styles.struck}>{label}</span>
          <span className={styles.tagRemoved}>REMOVED</span>
        </td>
        <td className={styles.zero}>0%</td>
        <td className={styles.last}>
          <button
            type="button"
            className={styles.bringBack}
            disabled={disabled}
            onClick={onBringBack}
          >
            Bring back
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td className={styles.first}>{label}</td>
      <td>
        <div className={styles.share}>
          <span className={styles.value}>{offer.share}%</span>
          <button
            type="button"
            aria-label={offer.pinned ? 'Unpin share' : 'Pin share'}
            aria-pressed={offer.pinned}
            className={offer.pinned ? styles.pinOn : styles.pin}
            disabled={disabled}
            onClick={() => onPin(!offer.pinned)}
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill={offer.pinned ? 'currentColor' : 'none'}
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 17v5" />
              <path d="M9 3h6l-1 6 3 3H7l3-3-1-6z" />
            </svg>
          </button>
        </div>
      </td>
      <td className={styles.last}>
        <button
          type="button"
          className={styles.remove}
          disabled={disabled}
          onClick={onRemove}
        >
          Remove
        </button>
      </td>
    </tr>
  );
}
