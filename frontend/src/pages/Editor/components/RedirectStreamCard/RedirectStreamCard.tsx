import type { Stream } from '../../../../api';

import styles from './RedirectStreamCard.module.css';

type RedirectStreamCardProps = {
  stream: Stream;
};

export function RedirectStreamCard({ stream }: RedirectStreamCardProps) {
  const headingId = `stream-${stream.id}`;

  return (
    <section aria-labelledby={headingId} className={styles.card}>
      <div>
        <h2 id={headingId} className={styles.title}>
          {stream.name}{' '}
          <span className={styles.position}>#{stream.position}</span>
        </h2>
        <div className={styles.meta}>stream {stream.kt_id} · read only</div>
      </div>
      <div className={styles.details}>
        {stream.filters.map((f) => (
          <span key={f.name} className={styles.filter}>
            {f.name === 'country' ? 'Country' : f.name}
            {f.payload.map((p) => (
              <span key={p} className={styles.chip}>
                {p}
              </span>
            ))}
          </span>
        ))}
        <span aria-hidden="true" className={styles.arrow}>
          →
        </span>
        <span>{stream.action_payload}</span>
      </div>
    </section>
  );
}
