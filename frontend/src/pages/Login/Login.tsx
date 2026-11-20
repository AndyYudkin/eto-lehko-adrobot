import { useState, type SubmitEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { ApiError, useLogin, useMe } from '../../api';

import styles from './Login.module.css';

export function Login() {
  const navigate = useNavigate();
  const me = useMe();
  const login = useLogin();
  const [loginValue, setLoginValue] = useState('');
  const [password, setPassword] = useState('');

  if (me.isSuccess) return <Navigate to="/campaigns" replace />;

  function handleSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    login.mutate(
      { login: loginValue, password },
      { onSuccess: () => navigate('/campaigns') },
    );
  }

  const error = login.error;
  const errorMessage = !error
    ? null
    : error instanceof ApiError && error.status === 401
      ? 'Invalid login or password'
      : 'Something went wrong. Try again later.';

  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <div className={styles.logo}>AdRobot</div>
        <form className={styles.card} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="login">Login</label>
            <input
              id="login"
              autoComplete="username"
              placeholder="Login"
              required
              value={loginValue}
              onChange={(e) => setLoginValue(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className={styles.submit}
            disabled={login.isPending}
          >
            {login.isPending ? 'Logging in…' : 'Log in'}
          </button>
          {errorMessage && (
            <p role="alert" className={styles.error}>
              {errorMessage}
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
