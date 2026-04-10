import { useEffect, useRef, useState } from 'react'
import {
  fetchShipDestinations,
  fetchShipDetail,
  fetchShipHistory,
  fetchShips,
  mergePositions,
  queryAgent,
} from './api'
import ConflictPanel from './components/ConflictPanel'
import Map from './components/Map'
import ShipPanel from './components/ShipPanel'
import TranscriptRail from './components/TranscriptRail'
import VoiceButton from './components/VoiceButton'
import useSelection from './hooks/useSelection'
import useVoice from './hooks/useVoice'

const EMPTY_TRACK = { type: 'FeatureCollection', features: [] }

function App() {
  const [ships, setShips] = useState({ type: 'FeatureCollection', features: [] })
  const [shipDetail, setShipDetail] = useState(null)
  const [track, setTrack] = useState(EMPTY_TRACK)
  const [destinations, setDestinations] = useState([])
  const [insight, setInsight] = useState(null)
  const [shipsBbox, setShipsBbox] = useState(null)
  const [loadingShips, setLoadingShips] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [loadingTrack, setLoadingTrack] = useState(false)
  const [agentBusy, setAgentBusy] = useState(false)
  const [conflictState, setConflictState] = useState(null)
  const [resolvingConflict, setResolvingConflict] = useState(false)
  const [chatHistory, setChatHistory] = useState([])
  const [error, setError] = useState('')
  const [selectionVersion, setSelectionVersion] = useState(0)
  const chatHistoryRef = useRef([])
  const { selectedMMSI, select, deselect, selectionContext } = useSelection(shipDetail)
  const {
    isRecording,
    isTranscribing,
    error: voiceError,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useVoice({
    onTranscript: ({ transcript, language, confidence }) => {
      const entry = buildChatEntry('user', transcript, { language, confidence })
      appendChatEntry(entry)
      void runAgent(transcript, entry)
    },
  })

  useEffect(() => {
    chatHistoryRef.current = chatHistory
  }, [chatHistory])

  useEffect(() => {
    let active = true

    async function loadShips() {
      setLoadingShips(true)
      try {
        const data = await fetchShips(shipsBbox)
        if (active) {
          setShips(data)
          setError('')
        }
      } catch (loadError) {
        if (active) {
          setError(loadError.message)
        }
      } finally {
        if (active) {
          setLoadingShips(false)
        }
      }
    }

    loadShips()
    return () => {
      active = false
    }
  }, [shipsBbox])

  useEffect(() => {
    setConflictState(null)
  }, [selectedMMSI])

  useEffect(() => {
    let active = true

    async function loadSelectionData() {
      if (!selectedMMSI) {
        setShipDetail(null)
        setTrack(EMPTY_TRACK)
        setDestinations([])
        setInsight(null)
        setLoadingDetail(false)
        setLoadingTrack(false)
        return
      }

      setLoadingDetail(true)
      setLoadingTrack(true)
      setTrack(EMPTY_TRACK)

      try {
        const [detail, history, recentDestinations] = await Promise.all([
          fetchShipDetail(selectedMMSI),
          fetchShipHistory(selectedMMSI, 24),
          fetchShipDestinations(selectedMMSI, 5),
        ])

        if (!active) {
          return
        }

        setShipDetail(detail)
        setTrack({ type: 'FeatureCollection', features: [history.track] })
        setDestinations(recentDestinations)
        setInsight(null)
        setError('')
      } catch (loadError) {
        if (!active) {
          return
        }

        setShipDetail(null)
        setTrack(EMPTY_TRACK)
        setDestinations([])
        setInsight(null)
        setError(loadError.message)
      } finally {
        if (active) {
          setLoadingDetail(false)
          setLoadingTrack(false)
        }
      }
    }

    loadSelectionData()
    return () => {
      active = false
    }
  }, [selectedMMSI, selectionVersion])

  function refreshSelectionData() {
    setSelectionVersion((current) => current + 1)
  }

  function appendChatEntry(entry) {
    setChatHistory((current) => [entry, ...current].slice(0, 20))
  }

  function buildChatEntry(role, text, extra = {}) {
    return {
      id: crypto.randomUUID(),
      role,
      text,
      timestamp: new Date().toISOString(),
      ...extra,
    }
  }

  async function runAgent(transcript, userEntry) {
    setAgentBusy(true)
    try {
      const response = await queryAgent({
        transcript,
        selection_context: selectionContext
          ? {
              mmsi: selectionContext.mmsi,
              name: selectionContext.name,
              last_position: selectionContext.lastPosition,
            }
          : null,
        chat_history: [userEntry, ...chatHistoryRef.current].slice(0, 6).map((entry) => ({
          role: entry.role,
          text: entry.text,
          timestamp: entry.timestamp,
        })),
      })

      const assistantEntry = buildChatEntry('assistant', response.reply)
      appendChatEntry(assistantEntry)
      speakReply(response.reply)
      applyAgentAction(response.action, response.payload)
    } catch (agentError) {
      const reply = agentError.message || 'The assistant could not complete that request.'
      appendChatEntry(buildChatEntry('assistant', reply))
      speakReply(reply)
    } finally {
      setAgentBusy(false)
    }
  }

  function applyAgentAction(action, payload) {
    if (!action || !payload) {
      return
    }

    if (payload.mmsi && payload.mmsi !== selectedMMSI) {
      select(payload.mmsi)
    }

    if (action === 'SHOW_TRACK' && payload.history?.track) {
      setTrack({ type: 'FeatureCollection', features: [payload.history.track] })
    }

    if (action === 'SHOW_PANEL') {
      if (payload.ship_detail) {
        setShipDetail(payload.ship_detail)
      }
      if (payload.destinations) {
        setDestinations(payload.destinations)
      }
      if (payload.insight) {
        setInsight(payload.insight)
      } else if (payload.ship_detail || payload.destinations) {
        setInsight(null)
      }
    }

    if (action === 'SHOW_CONFLICT') {
      setConflictState(payload)
    }
  }

  function speakReply(text) {
    if (!window.speechSynthesis || !text) {
      return
    }
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
  }

  async function handleResolveConflict(resolution) {
    if (!conflictState) {
      return
    }

    setResolvingConflict(true)
    try {
      await mergePositions({
        position_id_1: conflictState.position_1.position_id,
        position_id_2: conflictState.position_2.position_id,
        resolution,
      })
      setConflictState(null)
      refreshSelectionData()
      const reply = 'Resolved the conflict and refreshed the selected track.'
      appendChatEntry(buildChatEntry('assistant', reply))
      speakReply(reply)
    } catch (mergeError) {
      const reply = mergeError.message || 'The conflict could not be resolved.'
      appendChatEntry(buildChatEntry('assistant', reply))
      speakReply(reply)
    } finally {
      setResolvingConflict(false)
    }
  }

  return (
    <div className="app-shell">
      <section className="map-column">
        <header className="topbar">
          <div>
            <p className="eyebrow">Phase 5</p>
            <h1>Maritime COP Prototype</h1>
          </div>
          <div className="status-group">
            <span>{loadingShips ? 'Loading ships...' : `${ships.features.length} ships loaded`}</span>
            {selectedMMSI ? <span>Selected MMSI {selectedMMSI}</span> : <span>No ship selected</span>}
            <span>{loadingTrack ? 'Loading 24h track...' : track.features.length ? '24h track active' : 'No track loaded'}</span>
            <span>{agentBusy ? 'Assistant working...' : 'Assistant idle'}</span>
            <button type="button" className="secondary-button" onClick={deselect} disabled={!selectedMMSI}>
              Clear selection
            </button>
          </div>
        </header>
        {error ? <div className="error-banner">{error}</div> : null}
        <Map
          ships={ships}
          track={track}
          onSelectShip={select}
          onDeselect={deselect}
          onViewportChange={setShipsBbox}
          selectedMmsi={selectedMMSI}
        />
        <section className="voice-layout">
          <VoiceButton
            isRecording={isRecording}
            isTranscribing={isTranscribing}
            error={voiceError}
            onStartRecording={startRecording}
            onStopRecording={stopRecording}
            onCancelRecording={cancelRecording}
          />
          <TranscriptRail chatHistory={chatHistory} />
        </section>
      </section>
      <aside className="panel-column">
        <ShipPanel
          shipDetail={shipDetail}
          destinations={destinations}
          insight={insight}
          loading={loadingDetail}
          selectionContext={selectionContext}
        />
      </aside>
      <ConflictPanel
        conflict={conflictState}
        resolving={resolvingConflict}
        onResolve={handleResolveConflict}
        onCancel={() => setConflictState(null)}
      />
    </div>
  )
}

export default App
