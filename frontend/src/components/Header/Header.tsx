import { Link } from 'react-router-dom';

import styles from './Header.module.css';

export function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <div className={styles.logo}>AdRobot</div>
        <Link to="/logout" className={styles.logout}>
          Log out
        </Link>
      </div>
    </header>
  );
}
