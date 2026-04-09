import { useEffect, useMemo, useState } from 'react'

function useSelection(shipDetail) {
  const [selectedMMSI, setSelectedMMSI] = useState(null)

  const selectionContext = useMemo(() => {
    if (!selectedMMSI) {
      return null
    }

    return {
      mmsi: selectedMMSI,
      name: shipDetail?.identity?.name ?? null,
      lastPosition: shipDetail?.last_position ?? null,
    }
  }, [selectedMMSI, shipDetail])

  useEffect(() => {
    if (selectionContext) {
      console.log('selectionContext', selectionContext)
    }
  }, [selectionContext])

  function select(mmsi) {
    setSelectedMMSI(mmsi)
  }

  function deselect() {
    setSelectedMMSI(null)
  }

  return {
    selectedMMSI,
    select,
    deselect,
    selectionContext,
  }
}

export default useSelection
