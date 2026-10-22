/**
 * Thin API client for the PrivGuard backend.
 *
 * Every request goes through `request()`, so cookies, CSRF, and error
 * handling are decided in exactly one place.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

// The CSRF token lives in this module variable only - never localStorage or
// sessionStorage. Storage outlives the page and is readable by any injected
// script; a module variable disappears on reload and is re-fetched.
let csrfToken = null

export class ApiError extends Error {
  constructor(message, { status = null, data = null, cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.cause = cause
  }
}

/** Called after login: Django's login() rotates the token server-side. */
export function setCsrfToken(token) {
  csrfToken = token
}

async function getCsrfToken() {
  if (!csrfToken) {
    const data = await request('GET', '/auth/csrf/')
    csrfToken = data.csrfToken
  }
  return csrfToken
}

/** Turn DRF's error shapes into one human-readable message. */
function errorMessage(data, status) {
  if (data?.detail) return String(data.detail)
  if (Array.isArray(data?.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors.join(' ')
  }
  if (data && typeof data === 'object') {
    const first = Object.values(data).flat().find(Boolean)
    if (first) return String(first)
  }
  return `Request failed with status ${status}.`
}

async function request(method, path, body, { retryOnCsrf = true } = {}) {
  const unsafe = UNSAFE_METHODS.has(method)
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (unsafe) headers['X-CSRFToken'] = await getCsrfToken()

  let response
  try {
    // credentials: 'include' sends the HttpOnly session cookie. Pairs with
    // Django's CORS_ALLOW_CREDENTIALS = True.
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    // fetch() only rejects on network-level failure: backend down, wrong port,
    // or a CORS rejection. Distinct from "backend answered with an error".
    throw new ApiError('Cannot reach the PrivGuard backend.', { cause })
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    // A stale CSRF token - for example after logging in from another tab,
    // which rotates it - fails with 403 "CSRF Failed". Refetch once and retry.
    const csrfFailed = String(data?.detail ?? '').startsWith('CSRF Failed')
    if (unsafe && retryOnCsrf && response.status === 403 && csrfFailed) {
      csrfToken = null
      return request(method, path, body, { retryOnCsrf: false })
    }
    throw new ApiError(errorMessage(data, response.status), { status: response.status, data })
  }

  return data
}

export const apiGet = (path) => request('GET', path)
export const apiPost = (path, body) => request('POST', path, body)

export { BASE_URL }
