import * as React from "react";
import Map, {
  GeolocateControl,
  NavigationControl,
  Marker,
  Popup,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { useStore } from "@nanostores/react";
import {
  stations,
  setSelectedStation,
  fetchStations,
} from "../../store/map";
import Pin from "./Pin";

import { AQI_COLORS } from "../../data/constants";
import { getAQIIndex,getColorRange } from "../../utils";
import { isBackendAvailable } from "../../store/store";


function debounce(fn: any, ms: number) {
  let timer: number | undefined;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      fn.apply(this, arguments);
    }, ms);
  };
}

const MapComponent = () => {
  const backendIsAvailable = useStore(isBackendAvailable);
  const data = useStore(stations);

  const [dimensions, setDimensions] = React.useState({
    height: window.innerHeight,
    width: window.innerWidth,
  });

  React.useEffect(() => {
    const debouncedHandleResize = debounce(function handleResize() {
      setDimensions({
        height: window.innerHeight,
        width: window.innerWidth,
      });
    }, 500);
    window.addEventListener("resize", debouncedHandleResize);

    return () => {
      window.removeEventListener("resize", debouncedHandleResize);
    };
  });

  const [popupInfo, setPopupInfo] = React.useState(null);

  const pins = React.useMemo(
    () =>
      data
        ? data.map((station, index) => (
            <Marker
              key={`marker-${index}`}
              longitude={station.coordinates[1]}
              latitude={station.coordinates[0]}
              anchor="center"
              onClick={(e) => {
                // If we let the click event propagates to the map, it will immediately close the popup
                // with `closeOnClick: true`
                e.originalEvent.stopPropagation();
                setPopupInfo(station);
                setSelectedStation(station);
              }}
            >
              <Pin
                fill={getColorRange(station.forecast_6h[0].value)}
                value={station.forecast_6h[0].value}
              />
            </Marker>
          ))
        : [],
    [data]
  );

  
  return (
    <Map
      initialViewState={{
        longitude: -57.65,
        latitude: -25.28,
        zoom: 12.5,
      }}
      dragRotate={false}
      touchPitch={false}
      touchZoomRotate={false}
      minZoom={5.5}
      attributionControl={false}
      style={{ width: dimensions.width, height: dimensions.height * 0.75 }}
      maxBounds={[
        [-67.0435297482847, -28.42576579802394],
        [-45.05865460568049, -17.608237804262302],
      ]}
      onClick={() => setSelectedStation(undefined)}
      mapStyle="https://api.maptiler.com/maps/442672a8-7228-4ab4-9780-83a9932987b5/style.json?key=NKY3xmA1haxXwc5Jm48B"
    >
      {pins}
      {popupInfo && (
        <Popup
          anchor="top"
          offset={20}
          longitude={Number(popupInfo.coordinates[1])}
          latitude={Number(popupInfo.coordinates[0])}
          onClose={() => setPopupInfo(null)}
        >
          <div className="flex flex-col">
            <p className="font-bold font-sm">Estacion {popupInfo.id}</p>
            <p className="font-bold font-xs">{popupInfo.name}</p>
            <a>Ver estadisticas</a>
          </div>
        </Popup>
      )}
      <GeolocateControl position="bottom-right" />
      <NavigationControl position="bottom-right" />
    </Map>
  );
};

export default MapComponent;
