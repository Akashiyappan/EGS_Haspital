export const env = {
  appName: import.meta.env.VITE_APP_NAME || 'Onezae',
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, ''),
  isDev: import.meta.env.DEV,
} as const;
