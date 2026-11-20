import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Campaign } from './campaigns';
import { ApiError, request } from './client';

export type StreamOffer = {
  offer_id: number;
  name: string;
  share: number;
  pinned: boolean;
  active: boolean;
};

export type PushBlockReason = 'no_offers' | 'sum_not_100';

export type Stream = {
  id: string;
  kt_id: number;
  name: string;
  position: number;
  type: string;
  schema: string;
  has_offers: boolean;
  filters: { name: string; mode: string; payload: string[] }[];
  action_payload: string | null;
  dirty: boolean;
  push_block_reason: PushBlockReason | null;
  offers: StreamOffer[];
};

export type CampaignStreams = {
  campaign: Campaign;
  streams: Stream[];
};

function getCampaignStreams(id: string) {
  return request<CampaignStreams>({ url: `/api/campaigns/${id}/streams` });
}

export function useCampaignStreams(id: string) {
  return useQuery({
    queryKey: ['campaign', id, 'streams'],
    queryFn: () => getCampaignStreams(id),
    retry: false,
  });
}

export type StreamAction =
  | { type: 'add'; offerId: number }
  | { type: 'remove'; offerId: number }
  | { type: 'pin'; offerId: number; pinned: boolean };

function runStreamAction(streamId: string, action: StreamAction) {
  const base = `/api/streams/${streamId}`;
  switch (action.type) {
    case 'add':
      return request<Stream>({
        url: `${base}/offers`,
        method: 'POST',
        data: { offer_id: action.offerId },
      });
    case 'remove':
      return request<Stream>({
        url: `${base}/offers/${action.offerId}`,
        method: 'DELETE',
      });
    case 'pin':
      return request<Stream>({
        url: `${base}/offers/${action.offerId}`,
        method: 'PATCH',
        data: { pinned: action.pinned },
      });
  }
}

// one mutation per stream card: isPending/error describe the latest action
export function useStreamAction(campaignId: string, streamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: StreamAction) => runStreamAction(streamId, action),
    onSuccess: (stream) =>
      queryClient.setQueryData<CampaignStreams>(
        ['campaign', campaignId, 'streams'],
        (old) =>
          old && {
            ...old,
            streams: old.streams.map((s) => (s.id === stream.id ? stream : s)),
          },
      ),
  });
}

export type CampaignAction = 'fetch' | 'push' | 'cancel';

// Fetch when the draft is empty, Push / Cancel when it has changes: all three
// work on the whole campaign and return its streams
export function useCampaignAction(campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: CampaignAction) =>
      request<CampaignStreams>({
        url: `/api/campaigns/${campaignId}/${action}`,
        method: 'POST',
      }),
    onSuccess: (data) =>
      queryClient.setQueryData(['campaign', campaignId, 'streams'], data),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 410) {
        void queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      }
    },
  });
}
