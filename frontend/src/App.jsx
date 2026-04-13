import { useEffect, useRef, useState } from 'react'
import {
  fetchShipDestinations,
  fetchShipDetail,
  fetchShipHistory,
  fetchShips,
  mergePositions,
  queryAgent,
  speakText,
} from './api'
import ConflictPanel from './components/ConflictPanel'
import Map from './components/Map'
import ShipPanel from './components/ShipPanel'
import TranscriptRail from './components/TranscriptRail'
import VoiceButton from './components/VoiceButton'
import useSelection from './hooks/useSelection'
import useVoice from './hooks/useVoice'

const EMPTY_TRACK = { type: 'FeatureCollection', features: [] }
const EMPTY_MEMORY = {
  active_vessel: null,
  last_question: null,
  last_assistant_reply: null,
  last_analytics_question: null,
  last_analytics_summary: null,
  last_destination: null,
  last_action: null,
}

function App() {
  const [ships, setShips] = useState({ type: 'FeatureCollection', features: [] })
  const [shipDetail, setShipDetail] = useState(null)
  const [track, setTrack] = useState(EMPTY_TRACK)
  const [activeTrackMmsi, setActiveTrackMmsi] = useState(null)
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
  const [conversationMemory, setConversationMemory] = useState(EMPTY_MEMORY)
  const [error, setError] = useState('')
  const [selectionVersion, setSelectionVersion] = useState(0)
  const chatHistoryRef = useRef([])
  const audioRef = useRef(null)
  const audioUrlRef = useRef(null)
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
    return () => {
      stopReplyAudio()
    }
  }, [])

  useEffect(() => {
    if (!selectedMMSI) {
      setConversationMemory((current) => ({
        ...current,
        active_vessel: null,
      }))
      setTrack(EMPTY_TRACK)
      setActiveTrackMmsi(null)
      return
    }

    setInsight(null)
  }, [selectedMMSI])

  useEffect(() => {
    if (!shipDetail?.identity) {
      return
    }

    setConversationMemory((current) => ({
      ...current,
      active_vessel: {
        mmsi: shipDetail.identity.mmsi,
        name: shipDetail.identity.name,
      },
    }))
  }, [shipDetail])

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
        setActiveTrackMmsi(null)
        setDestinations([])
        setInsight(null)
        setLoadingDetail(false)
        setLoadingTrack(false)
        return
      }

      setLoadingDetail(true)
      setLoadingTrack(false)

      try {
        const [detail, recentDestinations] = await Promise.all([
          fetchShipDetail(selectedMMSI),
          fetchShipDestinations(selectedMMSI, 5),
        ])

        if (!active) {
          return
        }

        setShipDetail(detail)
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

  function handleSelectShip(mmsi) {
    setTrack(EMPTY_TRACK)
    setActiveTrackMmsi(null)
    setInsight(null)
    select(mmsi)
  }

  function updateConversationMemory(updates) {
    setConversationMemory((current) => ({
      ...current,
      ...updates,
    }))
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
    const requestMemory = {
      ...conversationMemory,
      last_question: transcript,
      last_destination:
        extractDestinationReference(transcript) ?? conversationMemory.last_destination,
    }
    updateConversationMemory(requestMemory)

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
        conversation_memory: requestMemory,
      })

      const assistantEntry = buildChatEntry('assistant', response.reply)
      appendChatEntry(assistantEntry)
      syncConversationMemory(response, transcript)
      void speakReply(response.reply)
      applyAgentAction(response.action, response.payload)
    } catch (agentError) {
      const reply = agentError.message || 'The assistant could not complete that request.'
      appendChatEntry(buildChatEntry('assistant', reply))
      updateConversationMemory({
        last_assistant_reply: reply,
      })
      void speakReply(reply)
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
      setLoadingTrack(false)
      setTrack({ type: 'FeatureCollection', features: [payload.history.track] })
      setActiveTrackMmsi(payload.mmsi ?? selectedMMSI)
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

  function syncConversationMemory(response, transcript) {
    const nextMemory = {
      last_assistant_reply: response.reply,
      last_action: response.action,
    }

    if (response.payload?.mmsi) {
      nextMemory.active_vessel = {
        mmsi: response.payload.mmsi,
        name:
          response.payload.ship_detail?.identity?.name ??
          selectionContext?.name ??
          conversationMemory.active_vessel?.name ??
          null,
      }
    }

    if (response.payload?.insight?.summary) {
      nextMemory.last_analytics_question = transcript
      nextMemory.last_analytics_summary = response.payload.insight.summary
    }

    const destination = extractDestinationReference(transcript) ?? conversationMemory.last_destination
    if (destination) {
      nextMemory.last_destination = destination
    }

    updateConversationMemory(nextMemory)
  }

  async function speakReply(text) {
    if (!text) {
      return
    }

    try {
      stopReplyAudio()
      const audioBlob = await speakText(text)
      const audioUrl = URL.createObjectURL(audioBlob)
      const audio = new Audio(audioUrl)
      audioRef.current = audio
      audioUrlRef.current = audioUrl
      audio.addEventListener(
        'ended',
        () => {
          if (audioRef.current === audio) {
            audioRef.current = null
          }
          if (audioUrlRef.current === audioUrl) {
            URL.revokeObjectURL(audioUrl)
            audioUrlRef.current = null
          }
        },
        { once: true },
      )
      await audio.play()
    } catch (speechError) {
      console.warn('Piper playback unavailable:', speechError)
    }
  }

  function stopReplyAudio() {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
      audioRef.current = null
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
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
      if (selectedMMSI && activeTrackMmsi === selectedMMSI) {
        setLoadingTrack(true)
        const history = await fetchShipHistory(selectedMMSI, 24)
        setTrack({ type: 'FeatureCollection', features: [history.track] })
        setLoadingTrack(false)
      }
      const reply =
        activeTrackMmsi === selectedMMSI
          ? 'Resolved the conflict and refreshed the selected track.'
          : 'Resolved the conflict and refreshed the selected vessel.'
      appendChatEntry(buildChatEntry('assistant', reply))
      void speakReply(reply)
    } catch (mergeError) {
      const reply = mergeError.message || 'The conflict could not be resolved.'
      appendChatEntry(buildChatEntry('assistant', reply))
      void speakReply(reply)
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
            <span>
              {loadingTrack
                ? 'Loading track...'
                : track.features.length
                  ? 'Track loaded'
                  : selectedMMSI
                    ? 'Last known position loaded'
                    : 'No track loaded'}
            </span>
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
          onSelectShip={handleSelectShip}
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

function extractDestinationReference(text) {
  const match = text.match(/\b(?:to|been to|visit|visited)\s+([a-zA-Z.'\-\s]+)\??$/i)
  return match ? match[1].trim().replace(/[?.!]+$/, '') : null
}

export default App
