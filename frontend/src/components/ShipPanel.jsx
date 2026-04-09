function formatValue(value) {
  if (value === null || value === undefined || value === '') {
    return 'Unknown'
  }
  return value
}

function ShipPanel({ shipDetail, destinations, loading, selectionContext }) {
  if (loading) {
    return (
      <div className="panel-card">
        <h2>Ship Detail</h2>
        <p>Loading selected vessel...</p>
      </div>
    )
  }

  if (!shipDetail) {
    return (
      <div className="panel-card">
        <h2>Ship Detail</h2>
        <p>Select a vessel on the map to inspect its identity, 24h track, and recent destinations.</p>
      </div>
    )
  }

  const { identity, last_position: lastPosition } = shipDetail

  return (
    <div className="panel-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Selected Vessel</p>
          <h2>{formatValue(identity.name)}</h2>
        </div>
        <span className="pill">MMSI {identity.mmsi}</span>
      </div>

      <dl className="detail-grid">
        <div>
          <dt>Flag</dt>
          <dd>{formatValue(identity.flag)}</dd>
        </div>
        <div>
          <dt>Ship Type</dt>
          <dd>{formatValue(identity.ship_type)}</dd>
        </div>
        <div>
          <dt>IMO</dt>
          <dd>{formatValue(identity.imo)}</dd>
        </div>
        <div>
          <dt>Call Sign</dt>
          <dd>{formatValue(identity.call_sign)}</dd>
        </div>
        <div>
          <dt>Nav Status</dt>
          <dd>{formatValue(lastPosition.nav_status)}</dd>
        </div>
        <div>
          <dt>SOG</dt>
          <dd>{formatValue(lastPosition.sog)} kn</dd>
        </div>
        <div>
          <dt>COG</dt>
          <dd>{formatValue(lastPosition.cog)}°</dd>
        </div>
        <div>
          <dt>Last Seen</dt>
          <dd>{new Date(lastPosition.timestamp).toLocaleString()}</dd>
        </div>
      </dl>

      <div className="subpanel">
        <div className="subpanel-header">
          <h3>Selection Context</h3>
          <span>{selectionContext?.mmsi ?? identity.mmsi}</span>
        </div>
        <p className="context-copy">
          {selectionContext?.name ?? identity.name} is the active vessel for later voice and agent actions.
        </p>
      </div>

      <div className="subpanel">
        <div className="subpanel-header">
          <h3>Recent Destinations</h3>
          <span>{destinations.length}</span>
        </div>
        {destinations.length ? (
          <ul className="destination-list">
            {destinations.map((entry) => (
              <li key={`${entry.destination}-${entry.last_seen}`}>
                <strong>{entry.destination}</strong>
                <span>{new Date(entry.last_seen).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="context-copy">No recent destinations available for this vessel.</p>
        )}
      </div>
    </div>
  )
}

export default ShipPanel
