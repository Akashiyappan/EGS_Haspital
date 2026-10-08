import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it } from 'vitest';

import { getErrorMessage } from './errors';

function axiosErrorWith(status: number, data: unknown) {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, {
    status,
    statusText: '',
    headers: {},
    config,
    data,
  });
}

describe('getErrorMessage', () => {
  it('uses the API error message', () => {
    const err = axiosErrorWith(401, { error: { code: 'x', message: 'Invalid email or password' } });
    expect(getErrorMessage(err)).toBe('Invalid email or password');
  });

  it('prefers the first validation detail', () => {
    const err = axiosErrorWith(422, {
      error: {
        message: 'Request validation failed',
        details: [{ loc: ['body', 'password'], msg: 'too short' }],
      },
    });
    expect(getErrorMessage(err)).toBe('password: too short');
  });

  it('reports network errors', () => {
    const err = new AxiosError('Network Error', 'ERR_NETWORK');
    expect(getErrorMessage(err)).toMatch(/unable to reach/i);
  });

  it('falls back for unknown values', () => {
    expect(getErrorMessage(42)).toBe('Something went wrong');
  });
});
