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
import { statisticsSelectedStation } from "../../store/statistics";


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

const PlaceHolderMap = () => {
  const data = useStore(statisticsSelectedStation);
  console.log(data)
  const [dimensions, setDimensions] = React.useState({
    height: 300,
    width: '100%',
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


  
  return (
    <Map
      initialViewState={{
        longitude: data?.coordinates[1] || -57.65,
        latitude: data?.coordinates[0] || -25.28,
        zoom: 15,
      }}
      dragRotate={false}
      touchPitch={false}
      touchZoomRotate={true}
      minZoom={5.5}
      attributionControl={false}
      style={{...dimensions}}
      interactive={false}
      maxBounds={[
        [-67.0435297482847, -28.42576579802394],
        [-45.05865460568049, -17.608237804262302],
      ]}
      mapStyle="https://api.maptiler.com/maps/442672a8-7228-4ab4-9780-83a9932987b5/style.json?key=NKY3xmA1haxXwc5Jm48B"
    >
       <Marker
              key={`marker-${data?.id}`}
              longitude={data?.coordinates[1]}
              latitude={data?.coordinates[0]}
              anchor="center"
            >
              <Pin
                fill={getColorRange(data?.aqi_pm2_5 || 0)}
                value={data?.aqi_pm2_5}
              />
            </Marker>
    </Map>
  );
};

export default PlaceHolderMap;
