import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';

import { ApiError, useMe } from '../../api';

type RequireAuthProps = {
  children: ReactNode;
};

export function RequireAuth({ children }: RequireAuthProps) {
  const { isPending, error } = useMe();

  if (isPending) return null;
  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to="/login" replace />;
  }
  if (error) return <p role="alert">Something went wrong. Try again later.</p>;
  return children;
}
