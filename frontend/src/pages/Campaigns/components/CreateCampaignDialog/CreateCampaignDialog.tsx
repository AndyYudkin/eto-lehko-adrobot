import { useEffect, useState, type SubmitEvent } from 'react';

import { ApiError, useCreateCampaign, type OfferOption } from '../../../../api';
import { OfferSelect } from '../../../../components/OfferSelect';
import { GeoChips } from './components/GeoChips';

import styles from './CreateCampaignDialog.module.css';

type CreateCampaignDialogProps = {
  onClose: () => void;
};

export function CreateCampaignDialog({ onClose }: CreateCampaignDialogProps) {
  // the dialog is mounted only while open, so state starts fresh every time
  const [name, setName] = useState('');
  const [geo, setGeo] = useState<string[]>([]);
  const [offer, setOffer] = useState<OfferOption | null>(null);
  const create = useCreateCampaign();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  function handleSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canCreate || !offer) return;
    create.mutate(
      { name: name.trim(), geo, offer_id: offer.id },
      { onSuccess: onClose },
    );
  }

  const canCreate = name.trim() !== '' && geo.length > 0 && offer !== null;
  const error = create.error;
  const errorMessage = !error
    ? null
    : error instanceof ApiError && error.status !== 422
      ? error.detail
      : 'Check the fields';

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dlg-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.head}>
          <h2 id="dlg-title" className={styles.title}>
            New campaign
          </h2>
          <button
            type="button"
            className={styles.close}
            aria-label="Close"
            onClick={onClose}
          >
            <svg
              aria-hidden="true"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="name">Name</label>
            <input
              id="name"
              placeholder="Campaign name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="geo">Geo</label>
            <GeoChips value={geo} onChange={setGeo} />
          </div>

          <div className={styles.field}>
            <label htmlFor="offer">Offer</label>
            <OfferSelect inputId="offer" value={offer} onChange={setOffer} />
          </div>

          <div className={styles.preview}>
            <div className={styles.previewTitle}>Will be created</div>
            <div className={styles.line}>
              <span className={styles.lineLabel}>Flow #1</span>
              <span>
                {geo.length ? `Country ${geo.join(', ')}` : 'Country —'} →
                google.com
              </span>
            </div>
            <div className={styles.line}>
              <span className={styles.lineLabel}>Flow #2</span>
              <span>
                Everyone else → {offer ? `#${offer.id}` : 'no offer'} · 100%
              </span>
            </div>
          </div>

          {errorMessage && (
            <p role="alert" className={styles.error}>
              {errorMessage}
            </p>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.cancel} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={styles.create}
              disabled={!canCreate || create.isPending}
            >
              {create.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
