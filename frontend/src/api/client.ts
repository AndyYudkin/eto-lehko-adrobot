import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios';

const NO_REFRESH_PATHS = ['/api/auth/login', '/api/auth/refresh'];

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

type RequestConfig = {
  url: string;
  method?: AxiosRequestConfig['method'];
  data?: unknown;
};

let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

const api = axios.create({
  withCredentials: true,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

function toApiError(error: AxiosError<{ detail?: unknown }>): ApiError {
  if (error.response) {
    const { status, statusText, data } = error.response;
    const detail = typeof data?.detail === 'string' ? data.detail : statusText;
    return new ApiError(status, detail);
  }
  if (error.code === AxiosError.ECONNABORTED) {
    return new ApiError(0, 'Request timed out');
  }
  return new ApiError(0, 'Network error');
}

function refreshOnce(): Promise<boolean> {
  refreshPromise ??= api
    .post('/api/auth/refresh')
    .then(() => true)
    .catch(() => false)
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

api.interceptors.response.use(undefined, async (error: unknown) => {
  if (!axios.isAxiosError(error)) throw error;
  const config = error.config as RetriableConfig | undefined;
  if (
    error.response?.status === 401 &&
    config &&
    !config._retry &&
    !NO_REFRESH_PATHS.includes(config.url ?? '')
  ) {
    config._retry = true;
    if (await refreshOnce()) return api(config);
  }
  throw toApiError(error);
});

export async function request<T>({
  url,
  method = 'GET',
  data,
}: RequestConfig): Promise<T> {
  const res = await api.request({ url, method, data });
  if (res.status === 204) return undefined as T;
  return res.data as T;
}
