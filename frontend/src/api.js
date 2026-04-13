export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) {
    let payload
    try {
      payload = await response.json()
    } catch {
      throw new Error(`Request failed with status ${response.status}`)
    }
    const detail = payload.detail ?? payload
    throw new Error(detail.message ?? `Request failed with status ${response.status}`)
  }
  return response.json()
}

export async function requestAudio(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) {
    let payload
    try {
      payload = await response.json()
    } catch {
      throw new Error(`Request failed with status ${response.status}`)
    }
    const detail = payload.detail ?? payload
    throw new Error(detail.message ?? `Request failed with status ${response.status}`)
  }
  return response.blob()
}

export function fetchShips(bbox) {
  if (!bbox) {
    return request('/ships')
  }

  return request(`/ships?bbox=${encodeURIComponent(bbox)}`)
}

export function fetchShipDetail(mmsi) {
  return request(`/ships/${mmsi}`)
}

export function fetchShipHistory(mmsi, hours = 24) {
  return request(`/ships/${mmsi}/history?hours=${hours}`)
}

export function fetchShipDestinations(mmsi, limit = 5) {
  return request(`/ships/${mmsi}/destinations?limit=${limit}`)
}

export function transcribeAudio(audioBlob) {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'utterance.webm')

  return request('/voice/transcribe', {
    method: 'POST',
    body: formData,
  })
}

export function speakText(text) {
  return requestAudio('/voice/speak', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text }),
  })
}

export function queryAgent(payload) {
  return request('/agent/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}

export function mergePositions(payload) {
  return request('/positions/merge', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}
