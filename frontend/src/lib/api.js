/**
 * Thin API client for the PrivGuard backend.
 *
 * Every request goes through here, so cookies, CSRF, errors and session
 * expiry are handled in exactly one place.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

// The CSRF token lives in this module variable only - never localStorage or
// sessionStorage. Storage outlives the page and is readable by any injected
// script; a module variable disappears on reload and is re-fetched.
let csrfToken = null

// Registered by AuthProvider. Called when a request is refused with 401/403,
// which may mean the 8-hour session expired while the tab stayed open. The
// handler RE-CHECKS /auth/me/ instead of assuming: a 403 can also be an
// ordinary "you are not allowed to do this".
let sessionCheck = null

export class ApiError extends Error {
  constructor(message, { status = null, data = null, cause = null, aborted = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.cause = cause
    this.aborted = aborted
  }
}

/** Called after login: Django's login() rotates the token server-side. */
export function setCsrfToken(token) {
  csrfToken = token
}

export function setSessionCheck(handler) {
  sessionCheck = handler
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

function isCsrfFailure(status, data) {
  return status === 403 && String(data?.detail ?? '').startsWith('CSRF Failed')
}

function reportRefusal(path, status) {
  // /auth/* is excluded: /auth/me/ itself returns 403 when logged out, and
  // re-checking it from here would loop.
  if ((status === 401 || status === 403) && !path.startsWith('/auth/')) {
    sessionCheck?.()
  }
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
    if (unsafe && retryOnCsrf && isCsrfFailure(response.status, data)) {
      csrfToken = null
      return request(method, path, body, { retryOnCsrf: false })
    }
    reportRefusal(path, response.status)
    throw new ApiError(errorMessage(data, response.status), { status: response.status, data })
  }

  return data
}

export const apiGet = (path) => request('GET', path)
export const apiPost = (path, body) => request('POST', path, body)
export const apiDelete = (path) => request('DELETE', path)

/**
 * POST a multipart form, reporting upload progress (0..1) as it goes.
 *
 * Uses XMLHttpRequest because fetch() cannot report UPLOAD progress - it has
 * no equivalent of xhr.upload.onprogress - and a large upload with no
 * progress bar looks frozen. Pass an AbortSignal to let the user cancel.
 */
export async function apiUpload(path, formData, { onProgress, signal } = {}) {
  const token = await getCsrfToken()

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE_URL}${path}`)
    xhr.withCredentials = true // send the session cookie, like fetch's credentials: 'include'
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-CSRFToken', token)
    // Deliberately NO Content-Type header: the browser must write
    // "multipart/form-data; boundary=...". Setting it by hand would leave out
    // the boundary, and the server could not split the parts.

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total)
    }

    xhr.onload = () => {
      let data = null
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        data = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data)
        return
      }
      if (isCsrfFailure(xhr.status, data)) {
        // Not retried automatically: that would resend the whole upload.
        csrfToken = null
        reject(new ApiError('Your security token was out of date. Please start the upload again.', {
          status: xhr.status,
          data,
        }))
        return
      }
      reportRefusal(path, xhr.status)
      reject(new ApiError(errorMessage(data, xhr.status), { status: xhr.status, data }))
    }

    xhr.onerror = () =>
      reject(new ApiError('The upload failed: the backend could not be reached or closed the connection.'))
    xhr.onabort = () => reject(new ApiError('Upload cancelled.', { aborted: true }))

    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(formData)
  })
}

export { BASE_URL }
