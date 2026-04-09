function TranscriptRail({ chatHistory }) {
  return (
    <section className="transcript-rail">
      <div className="rail-header">
        <div>
          <p className="eyebrow">Voice Log</p>
          <h2>Transcript Rail</h2>
        </div>
        <span>{chatHistory.length} turns</span>
      </div>
      {chatHistory.length ? (
        <ul className="chat-list">
          {chatHistory.map((entry) => (
            <li key={entry.id} className={`chat-entry ${entry.role}`}>
              <div className="chat-meta">
                <strong>{entry.role === 'user' ? 'User' : 'Assistant'}</strong>
                <span>{new Date(entry.timestamp).toLocaleTimeString()}</span>
              </div>
              <p>{entry.text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-rail">Hold the voice button and speak to capture the first transcript.</p>
      )}
    </section>
  )
}

export default TranscriptRail
