import { useState } from 'react';

import { Header } from '../../components/Header';
import { CampaignsTable } from './components/CampaignsTable';
import { CreateCampaignDialog } from './components/CreateCampaignDialog';

import styles from './Campaigns.module.css';

export function Campaigns() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div>
      <Header />
      <main className={styles.main}>
        <div className={styles.top}>
          <h1 className={styles.title}>Campaigns</h1>
          <button
            type="button"
            className={styles.newButton}
            onClick={() => setDialogOpen(true)}
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            New campaign
          </button>
        </div>
        <CampaignsTable />
      </main>
      {dialogOpen && (
        <CreateCampaignDialog onClose={() => setDialogOpen(false)} />
      )}
    </div>
  );
}
