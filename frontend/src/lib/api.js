/**
 * Thin API client for the PrivGuard backend.
 *
 * Everything goes through here so that Cycle 2 can add authentication
 * handling (401 -> redirect to login) in exactly one place.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  constructor(message, { status = null, cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.cause = cause
  }
}

export async function apiGet(path) {
  let response
  try {
    // credentials: 'include' sends the session cookie. Pairs with Django's
    // CORS_ALLOW_CREDENTIALS = True. Needed from Cycle 2 onward.
    response = await fetch(`${BASE_URL}${path}`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
  } catch (cause) {
    // fetch() only rejects on network-level failure: backend down, wrong port,
    // or a CORS rejection. Distinct from "backend answered with an error".
    throw new ApiError('Cannot reach the PrivGuard backend.', { cause })
  }

  if (!response.ok) {
    throw new ApiError(`Request failed with status ${response.status}.`, {
      status: response.status,
    })
  }

  return response.json()
}

export { BASE_URL }
