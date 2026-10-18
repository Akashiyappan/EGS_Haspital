import { toast } from 'sonner';
import type { UseMutationOptions } from '@tanstack/react-query';

export function useToast() {
  return {
    success: (message: string) => toast.success(message),
    error: (message: string) => toast.error(message),
    info: (message: string) => toast.info(message),
    warning: (message: string) => toast.warning(message),
    promise: <T,>(
      promise: Promise<T>,
      messages: { loading: string; success: string | ((data: T) => string); error: string | ((error: Error) => string) }
    ) => toast.promise(promise, messages),
  };
}

export function withToast<TData, TError, TVariables, TContext>(
  options: UseMutationOptions<TData, TError, TVariables, TContext> & {
    successMessage?: string | ((data: TData) => string);
    errorMessage?: string | ((error: TError) => string);
  }
): UseMutationOptions<TData, TError, TVariables, TContext> {
  const { successMessage, errorMessage, onSuccess, onError, ...rest } = options;

  return {
    ...rest,
    onSuccess: (data, variables, context) => {
      if (successMessage) {
        toast.success(typeof successMessage === 'function' ? successMessage(data) : successMessage);
      }
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      if (errorMessage) {
        toast.error(typeof errorMessage === 'function' ? errorMessage(error) : errorMessage);
      }
      onError?.(error, variables, context);
    },
  };
}