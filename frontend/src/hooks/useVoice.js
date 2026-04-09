import { useEffect, useRef, useState } from 'react'
import { transcribeAudio } from '../api'

const MIN_AUDIO_BYTES = 1024

function useVoice({ onTranscript }) {
  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const onTranscriptRef = useRef(onTranscript)
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    onTranscriptRef.current = onTranscript
  }, [onTranscript])

  useEffect(() => {
    return () => {
      cleanupStream()
    }
  }, [])

  async function startRecording() {
    if (isRecording || isTranscribing) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Audio capture is not supported in this browser.')
      return
    }

    try {
      setError('')
      chunksRef.current = []
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const recorder = new MediaRecorder(stream, { mimeType })

      recorder.addEventListener('dataavailable', (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      })

      mediaRecorderRef.current = recorder
      recorder.start()
      setIsRecording(true)
    } catch (recordingError) {
      cleanupStream()
      setError('Microphone access was denied or unavailable.')
    }
  }

  async function stopRecording() {
    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state === 'inactive') {
      return
    }

    const audioBlob = await new Promise((resolve) => {
      recorder.addEventListener(
        'stop',
        () => {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
          resolve(blob)
        },
        { once: true },
      )
      recorder.stop()
    })

    setIsRecording(false)
    cleanupStream()

    if (!audioBlob || audioBlob.size < MIN_AUDIO_BYTES) {
      chunksRef.current = []
      return
    }

    setIsTranscribing(true)
    setError('')

    try {
      const result = await transcribeAudio(audioBlob)
      const transcript = result.transcript?.trim() ?? ''
      if (transcript) {
        onTranscriptRef.current?.({
          transcript,
          language: result.language ?? 'unknown',
          confidence: result.confidence ?? 0,
        })
      }
    } catch (transcriptionError) {
      setError(transcriptionError.message)
    } finally {
      setIsTranscribing(false)
      chunksRef.current = []
    }
  }

  function cancelRecording() {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
    chunksRef.current = []
    setIsRecording(false)
    cleanupStream()
  }

  function cleanupStream() {
    mediaRecorderRef.current = null
    const stream = streamRef.current
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }

  return {
    isRecording,
    isTranscribing,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  }
}

export default useVoice
