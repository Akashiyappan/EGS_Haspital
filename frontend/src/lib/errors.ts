import { isAxiosError } from 'axios';

interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: { loc?: (string | number)[]; msg?: string }[];
  };
}

/** Turns any thrown value into a message that is safe to show to users. */
export function getErrorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (isAxiosError<ApiErrorBody>(error)) {
    if (!error.response) {
      return 'Unable to reach the server. Check your connection and try again.';
    }
    const body = error.response.data?.error;
    const firstDetail = body?.details?.[0];
    if (firstDetail?.msg) {
      const field = firstDetail.loc?.at(-1);
      return typeof field === 'string' ? `${field}: ${firstDetail.msg}` : firstDetail.msg;
    }
    return body?.message ?? fallback;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

export function getErrorStatus(error: unknown): number | undefined {
  return isAxiosError(error) ? error.response?.status : undefined;
}
