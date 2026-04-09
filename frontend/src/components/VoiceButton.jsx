function VoiceButton({
  isRecording,
  isTranscribing,
  error,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
}) {
  function handlePointerDown(event) {
    event.preventDefault()
    onStartRecording()
  }

  function handlePointerUp(event) {
    event.preventDefault()
    onStopRecording()
  }

  function handlePointerCancel(event) {
    event.preventDefault()
    onCancelRecording()
  }

  function handlePointerLeave(event) {
    if (!isRecording) {
      return
    }
    if (event.buttons === 1) {
      onCancelRecording()
    }
  }

  let statusLabel = 'Hold to talk'
  if (isRecording) {
    statusLabel = 'Recording... release to send'
  } else if (isTranscribing) {
    statusLabel = 'Transcribing...'
  } else if (error) {
    statusLabel = error
  }

  return (
    <div className="voice-card">
      <button
        type="button"
        className={`voice-button ${isRecording ? 'recording' : ''}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onPointerLeave={handlePointerLeave}
        disabled={isTranscribing}
      >
        {isRecording ? 'Release' : 'Push To Talk'}
      </button>
      <p className={`voice-status ${error ? 'error' : ''}`}>{statusLabel}</p>
    </div>
  )
}

export default VoiceButton
