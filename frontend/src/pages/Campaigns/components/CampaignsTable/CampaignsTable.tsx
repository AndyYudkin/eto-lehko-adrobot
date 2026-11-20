import { Link } from 'react-router-dom';

import { useCampaigns } from '../../../../api';

import styles from './CampaignsTable.module.css';

export function CampaignsTable() {
  const { data, isPending, isError } = useCampaigns();

  if (isPending) return <p className={styles.message}>Loading…</p>;
  if (isError) {
    return (
      <p role="alert" className={styles.error}>
        Could not load campaigns
      </p>
    );
  }
  if (data.length === 0) {
    return <p className={styles.message}>No campaigns yet</p>;
  }

  return (
    <div className={styles.box}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.first}>Name</th>
            <th>Geo → Google</th>
            <th>Offer</th>
            <th className={styles.last}>
              <span className={styles.srOnly}>Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((c) => (
            <tr key={c.id}>
              <td className={styles.first}>
                <div className={styles.name}>{c.name}</div>
              </td>
              <td>{c.geo.join(', ')}</td>
              <td>#{c.offer_id}</td>
              <td className={styles.last}>
                <Link to={`/campaigns/${c.id}`} className={styles.action}>
                  Edit offers
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
