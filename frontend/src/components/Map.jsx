import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const SHIP_SOURCE_ID = 'ships'
const SHIP_LAYER_ID = 'ships-layer'
const TRACK_SOURCE_ID = 'selected-track'
const TRACK_LAYER_ID = 'selected-track-layer'

function Map({ ships, track, onSelectShip, onDeselect, onViewportChange, selectedMmsi }) {
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const onSelectShipRef = useRef(onSelectShip)
  const onDeselectRef = useRef(onDeselect)
  const onViewportChangeRef = useRef(onViewportChange)

  useEffect(() => {
    onSelectShipRef.current = onSelectShip
  }, [onSelectShip])

  useEffect(() => {
    onDeselectRef.current = onDeselect
  }, [onDeselect])

  useEffect(() => {
    onViewportChangeRef.current = onViewportChange
  }, [onViewportChange])

  useEffect(() => {
    if (mapRef.current || !mapContainerRef.current) {
      return undefined
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster',
            tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
          },
        },
        layers: [
          {
            id: 'basemap-layer',
            type: 'raster',
            source: 'basemap',
          },
        ],
      },
      center: [-63.5, 44.5],
      zoom: 6,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')

    map.on('load', () => {
      map.addSource(SHIP_SOURCE_ID, {
        type: 'geojson',
        data: ships,
      })

      map.addSource(TRACK_SOURCE_ID, {
        type: 'geojson',
        data: track,
      })

      map.addLayer({
        id: SHIP_LAYER_ID,
        type: 'circle',
        source: SHIP_SOURCE_ID,
        paint: {
          'circle-radius': [
            'case',
            ['==', ['get', 'mmsi'], selectedMmsi ?? -1],
            7,
            5,
          ],
          'circle-color': [
            'case',
            ['==', ['get', 'mmsi'], selectedMmsi ?? -1],
            '#f97316',
            '#0f766e',
          ],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
        },
      })

      map.addLayer({
        id: TRACK_LAYER_ID,
        type: 'line',
        source: TRACK_SOURCE_ID,
        layout: {
          'line-cap': 'round',
          'line-join': 'round',
        },
        paint: {
          'line-color': '#0ea5e9',
          'line-width': 3,
          'line-opacity': 0.85,
        },
      })

      map.on('click', (event) => {
        const shipFeatures = map.queryRenderedFeatures(event.point, { layers: [SHIP_LAYER_ID] })
        const mmsi = shipFeatures[0]?.properties?.mmsi

        if (mmsi) {
          onSelectShipRef.current?.(Number(mmsi))
          return
        }

        onDeselectRef.current?.()
      })

      map.on('mouseenter', SHIP_LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })

      map.on('mouseleave', SHIP_LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      const emitViewport = () => {
        const bounds = map.getBounds()
        if (!bounds) {
          return
        }
        const bbox = [
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ].join(',')
        onViewportChangeRef.current?.(bbox)
      }

      emitViewport()
      map.on('moveend', emitViewport)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) {
      return
    }
    const source = map.getSource(SHIP_SOURCE_ID)
    if (source) {
      source.setData(ships)
    }
  }, [ships])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) {
      return
    }
    const source = map.getSource(TRACK_SOURCE_ID)
    if (source) {
      source.setData(track)
    }
  }, [track])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer(SHIP_LAYER_ID)) {
      return
    }

    map.setPaintProperty(SHIP_LAYER_ID, 'circle-radius', [
      'case',
      ['==', ['get', 'mmsi'], selectedMmsi ?? -1],
      7,
      5,
    ])
    map.setPaintProperty(SHIP_LAYER_ID, 'circle-color', [
      'case',
      ['==', ['get', 'mmsi'], selectedMmsi ?? -1],
      '#f97316',
      '#0f766e',
    ])
  }, [selectedMmsi])

  return <div ref={mapContainerRef} className="map-container" />
}

export default Map
