import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from './client';

export type Campaign = {
  id: string;
  kt_id: number;
  name: string;
  url: string;
  geo: string[];
  offer_id: number;
  created_at: string;
  synced_at: string | null;
};

export type OfferOption = { id: number; name: string };

export type CreateCampaignInput = {
  name: string;
  geo: string[];
  offer_id: number;
};

function getCampaigns() {
  return request<Campaign[]>({ url: '/api/campaigns' });
}

function createCampaign(input: CreateCampaignInput) {
  return request<Campaign>({
    url: '/api/campaigns',
    method: 'POST',
    data: input,
  });
}

// excludeStreamId: leave out offers already in that stream (server-side)
export function searchOffers(q: string, excludeStreamId?: string) {
  const params = new URLSearchParams({ q });
  if (excludeStreamId) params.set('exclude_stream', excludeStreamId);
  return request<OfferOption[]>({ url: `/api/offers?${params}` });
}

export function useCampaigns() {
  return useQuery({ queryKey: ['campaigns'], queryFn: getCampaigns });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCampaign,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['campaigns'] }),
  });
}
