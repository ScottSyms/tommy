function formatPosition(position) {
  if (!position) {
    return null
  }

  return [
    { label: 'Position ID', value: position.position_id },
    { label: 'Timestamp', value: new Date(position.timestamp).toLocaleString() },
    { label: 'Latitude', value: position.lat },
    { label: 'Longitude', value: position.lon },
    { label: 'SOG', value: position.sog ?? 'Unknown' },
    { label: 'COG', value: position.cog ?? 'Unknown' },
  ]
}

function ConflictPanel({ conflict, resolving, onResolve, onCancel }) {
  if (!conflict) {
    return null
  }

  const first = formatPosition(conflict.position_1)
  const second = formatPosition(conflict.position_2)

  return (
    <div className="conflict-backdrop" role="dialog" aria-modal="true">
      <div className="conflict-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Conflict</p>
            <h2>Timestamp Collision</h2>
          </div>
          <span className="pill">{conflict.conflict_type}</span>
        </div>

        <p className="context-copy">{conflict.message}</p>

        <div className="conflict-grid">
          {[first, second].map((entries, index) => (
            <section key={index} className="conflict-card">
              <h3>{index === 0 ? 'Position 1' : 'Position 2'}</h3>
              <dl className="conflict-details">
                {entries.map((entry) => (
                  <div key={entry.label}>
                    <dt>{entry.label}</dt>
                    <dd>{entry.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        <div className="conflict-actions">
          <button type="button" className="secondary-button" onClick={() => onResolve('keep_most_recent')} disabled={resolving}>
            Keep Most Recent
          </button>
          <button type="button" className="secondary-button" onClick={() => onResolve('keep_other')} disabled={resolving}>
            Keep Other
          </button>
          <button type="button" className="secondary-button" onClick={() => onResolve('manual')} disabled={resolving}>
            Merge Manually
          </button>
          <button type="button" className="secondary-button" onClick={onCancel} disabled={resolving}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConflictPanel
