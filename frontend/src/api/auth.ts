import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from './client';

type Credentials = { login: string; password: string };
type Me = { login: string };

function login(credentials: Credentials) {
  return request<void>({
    url: '/api/auth/login',
    method: 'POST',
    data: credentials,
  });
}

function logout() {
  return request<void>({ url: '/api/auth/logout', method: 'POST' });
}

function getMe() {
  return request<Me>({ url: '/api/auth/me' });
}

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: getMe });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: login,
    // wait for fresh /me so route guards see the new session
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSettled: () => queryClient.clear(),
  });
}
