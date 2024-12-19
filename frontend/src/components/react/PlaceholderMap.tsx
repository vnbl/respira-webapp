import * as React from "react";
import Map, {
  GeolocateControl,
  NavigationControl,
  Marker,
  Popup,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { useStore } from "@nanostores/react";
import Pin from "./Pin";

import { getColorRange } from "../../utils";
import { statisticsSelectedStation } from "../../store/statistics";




const PlaceHolderMap = () => {
  const data = useStore(statisticsSelectedStation);

  console.log(data)
  const [dimensions, _] = React.useState({
    height: 300,
    width: '100%',
  });

  return (
    <>
      {data ?
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
          style={{ ...dimensions }}
          interactive={false}
          maxBounds={[
            [-67.0435297482847, -28.42576579802394],
            [-45.05865460568049, -17.608237804262302],
          ]}
          mapStyle="https://api.maptiler.com/maps/442672a8-7228-4ab4-9780-83a9932987b5/style.json?key=NKY3xmA1haxXwc5Jm48B"
        >
         <Marker
            key={`marker-${data.id}`}
            longitude={data.coordinates[1]}
            latitude={data.coordinates[0]}
            anchor="center"
          >
            <Pin
              fill={getColorRange(data.aqi_pm2_5 || 0)}
              value={data.aqi_pm2_5}
            />
          </Marker>
        </Map> 
        : 
        <svg className="animate-spin h-20 w-20 mr-3 ..." viewBox="0 0 24 24">
      </svg>
      }
    </>
  );
};

export default PlaceHolderMap;
