import { useEffect, useRef } from 'react';
import { Navigate } from 'react-router-dom';

import { useLogout } from '../../api';

export function Logout() {
  const { mutate, isIdle, isPending } = useLogout();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    mutate();
  }, [mutate]);

  if (isIdle || isPending) return <p>Logging out…</p>;
  return <Navigate to="/login" replace />;
}
