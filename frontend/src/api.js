export async function createDashboard(profile, signal) {
  const response = await fetch('/api/recommendations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
    cache: 'no-store',
    signal,
  })
  if (response.status === 422) throw new Error('Check the client details and try again. Some values are invalid.')
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(typeof error.detail === 'string' ? error.detail : 'The dashboard could not be created. Please try again.')
  }
  return response.json()
}
