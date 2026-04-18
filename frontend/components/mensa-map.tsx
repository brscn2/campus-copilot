"use client"

import * as React from "react"
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import type { MensaCanteen } from "@/lib/api"

const MENSA_ICON = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

const USER_ICON = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

const SELECTED_ICON = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

function FlyToSelected({ canteens, selectedMensa }: { canteens: MensaCanteen[]; selectedMensa: string }) {
  const map = useMap()
  const prevSelected = React.useRef(selectedMensa)

  React.useEffect(() => {
    if (prevSelected.current === selectedMensa) return
    prevSelected.current = selectedMensa
    const c = canteens.find((x) => x.canteen_id === selectedMensa)
    if (c?.latitude && c?.longitude) {
      map.flyTo([c.latitude, c.longitude], 14, { duration: 0.8 })
    }
  }, [selectedMensa, canteens, map])

  return null
}

function FitInitialBounds({ canteens, userPos }: { canteens: MensaCanteen[]; userPos: [number, number] | null }) {
  const map = useMap()
  const fitted = React.useRef(false)

  React.useEffect(() => {
    if (fitted.current || canteens.length === 0) return
    fitted.current = true
    const points: [number, number][] = canteens
      .filter((c) => c.latitude && c.longitude)
      .slice(0, 10)
      .map((c) => [c.latitude, c.longitude])
    if (userPos) points.push(userPos)
    if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points.map(([lat, lng]) => L.latLng(lat, lng))), { padding: [30, 30] })
    } else if (points.length === 1) {
      map.setView(points[0], 14)
    }
  }, [canteens, userPos, map])

  return null
}

interface MensaMapProps {
  canteens: MensaCanteen[]
  selectedMensa: string
  userPos: [number, number] | null
  onSelectMensa: (id: string) => void
  distanceFn: (lat: number, lng: number) => number | null
}

export default function MensaMap({ canteens, selectedMensa, userPos, onSelectMensa, distanceFn }: MensaMapProps) {
  const visibleCanteens = canteens.filter((c) => c.latitude && c.longitude)
  const defaultCenter: [number, number] = [48.2648, 11.6709]

  return (
    <div className="relative z-0 h-[350px] w-full overflow-hidden rounded-lg border border-border">
      <MapContainer
        center={defaultCenter}
        zoom={12}
        className="h-full w-full"
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitInitialBounds canteens={visibleCanteens} userPos={userPos} />
        <FlyToSelected canteens={visibleCanteens} selectedMensa={selectedMensa} />

        {userPos && (
          <>
            <Marker position={userPos} icon={USER_ICON}>
              <Popup>
                <strong>You are here</strong>
              </Popup>
            </Marker>
            <Circle
              center={userPos}
              radius={1000}
              pathOptions={{ color: "#3b82f6", fillColor: "#3b82f6", fillOpacity: 0.08, weight: 1 }}
            />
          </>
        )}

        {visibleCanteens.map((c) => {
          const dist = distanceFn(c.latitude, c.longitude)
          const isSelected = c.canteen_id === selectedMensa
          return (
            <Marker
              key={c.canteen_id}
              position={[c.latitude, c.longitude]}
              icon={isSelected ? SELECTED_ICON : MENSA_ICON}
              eventHandlers={{ click: () => onSelectMensa(c.canteen_id) }}
            >
              <Popup>
                <div className="min-w-[160px]">
                  <strong className="text-sm">{c.name}</strong>
                  <div className="text-xs text-gray-600 mt-0.5">{c.address}</div>
                  {dist !== null && (
                    <div className="text-xs font-medium mt-1">
                      {dist < 1 ? `${Math.round(dist * 1000)}m away` : `${dist.toFixed(1)}km away`}
                    </div>
                  )}
                  <button
                    className="mt-1.5 text-xs font-medium text-blue-600 hover:underline"
                    onClick={() => onSelectMensa(c.canteen_id)}
                  >
                    Show menu
                  </button>
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
    </div>
  )
}
