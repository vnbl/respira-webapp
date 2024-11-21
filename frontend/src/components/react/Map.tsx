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
  type STATION,
} from "../../store/map";
import Pin from "./Pin";

import { getColorRange } from "../../utils";
import { MapTooltip } from "./MapTooltip";


function debounce(fn: any, ms: number) {
  let timer: NodeJS.Timeout | undefined;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      fn.apply(undefined, arguments);
    }, ms);
  };
}

const MapComponent = () => {
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

  const [popupInfo, setPopupInfo] = React.useState<STATION | undefined>(undefined);

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
                setSelectedStation(station.id);
              }}
            >
              <Pin
                fill={getColorRange(station.aqi_pm2_5 || 0)}
                value={station.aqi_pm2_5}
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
      touchZoomRotate={true}
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
      {data && pins}
      {popupInfo && ( 
        <Popup
          anchor="bottom-left"
          offset={10}
          longitude={Number(popupInfo.coordinates[1])}
          latitude={Number(popupInfo.coordinates[0])}
          onClose={() => setPopupInfo(undefined)}
        >
          <div className="flex flex-col">
            <p className="font-bold text-[16px] text-white">Estación {popupInfo.id}</p>
            <p className="font-bold font-xs text-white">{popupInfo.name}</p>
            {/* <a><p className="text-green font-bold underline">Ver estadisticas</p></a> */}
          </div>
        </Popup>
      )}
      <GeolocateControl position="bottom-right"  showAccuracyCircle={false} />
      <NavigationControl position="bottom-right"/>
      <MapTooltip />
    </Map>
  );
};

export default MapComponent;
