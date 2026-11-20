import { Link, useParams } from 'react-router-dom';

import { ApiError, useCampaignAction, useCampaignStreams } from '../../api';
import { Header } from '../../components/Header';
import { RedirectStreamCard } from './components/RedirectStreamCard';
import { StreamCard } from './components/StreamCard';
import { PUSH_HINTS } from './pushHints';

import styles from './Editor.module.css';

function syncedLabel(syncedAt: string | null) {
  if (!syncedAt) return 'Not synced yet';
  const minutes = Math.floor(
    (Date.now() - new Date(syncedAt).getTime()) / 60000,
  );
  if (minutes < 1) return 'Synced from Keitaro just now';
  if (minutes < 60) return `Synced from Keitaro ${minutes} min ago`;
  if (minutes < 24 * 60) {
    return `Synced from Keitaro ${Math.floor(minutes / 60)} h ago`;
  }
  return `Synced from Keitaro ${new Date(syncedAt).toLocaleDateString()}`;
}

export function Editor() {
  const { id } = useParams();
  const campaignId = id ?? '';
  const { data, isPending, isError, error } = useCampaignStreams(campaignId);
  const sync = useCampaignAction(campaignId);
  const dirtyStreams = data?.streams.filter((s) => s.dirty) ?? [];
  const dirty = dirtyStreams.length > 0;
  const blockReason = dirtyStreams.find(
    (s) => s.push_block_reason,
  )?.push_block_reason;
  const pushHint = blockReason ? PUSH_HINTS[blockReason] : undefined;

  let content;
  if (sync.error instanceof ApiError && sync.error.status === 410) {
    content = (
      <>
        <p role="alert" className={styles.error}>
          Campaign was deleted in Keitaro
        </p>
        <Link to="/campaigns">Back to campaigns</Link>
      </>
    );
  } else if (isPending) {
    content = <p className={styles.message}>Loading…</p>;
  } else if (isError && !(error instanceof ApiError && error.status === 404)) {
    content = (
      <p role="alert" className={styles.error}>
        Could not load the campaign
      </p>
    );
  } else if (isError) {
    content = (
      <>
        <p className={styles.message}>Campaign not found</p>
        <Link to="/campaigns">Back to campaigns</Link>
      </>
    );
  } else {
    const { campaign, streams } = data;
    content = (
      <>
        <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
          <Link to="/campaigns" className={styles.crumbLink}>
            Campaigns
          </Link>
          <span aria-hidden="true">/</span>
          <span className={styles.current}>{campaign.name}</span>
        </nav>
        <div className={styles.top}>
          <div>
            <h1 className={styles.title}>{campaign.name}</h1>
            <div className={styles.synced}>
              {syncedLabel(campaign.synced_at)}
            </div>
          </div>
          {dirty ? (
            <div className={styles.actions}>
              {pushHint && <span className={styles.hint}>{pushHint}</span>}
              <button
                type="button"
                className={styles.cancel}
                disabled={sync.isPending}
                onClick={() => sync.mutate('cancel')}
              >
                Cancel
              </button>
              <button
                type="button"
                className={styles.push}
                disabled={sync.isPending || pushHint !== undefined}
                title={pushHint}
                onClick={() => sync.mutate('push')}
              >
                Push to KT
              </button>
            </div>
          ) : (
            <button
              type="button"
              className={styles.fetchButton}
              disabled={sync.isPending}
              onClick={() => sync.mutate('fetch')}
            >
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                <path d="M21 4v5h-5" />
              </svg>
              Fetch from KT
            </button>
          )}
        </div>
        {sync.isError && (
          <p role="alert" className={styles.error}>
            {sync.error.message}
          </p>
        )}
        {streams.map((s) =>
          s.has_offers ? (
            <StreamCard key={s.id} campaignId={campaignId} stream={s} />
          ) : (
            <RedirectStreamCard key={s.id} stream={s} />
          ),
        )}
        <p role="note" className={styles.note}>
          Shares are recalculated automatically: pinned offers keep their share,
          the rest is split evenly. Nothing reaches Keitaro until you press Push
          to KT.
        </p>
      </>
    );
  }

  return (
    <div>
      <Header />
      <main className={styles.main}>{content}</main>
    </div>
  );
}
