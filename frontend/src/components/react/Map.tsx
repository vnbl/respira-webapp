import * as React from "react";
import Map, {
  GeolocateControl,
  NavigationControl,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

function debounce(fn:any, ms:number) {
  let timer: number | undefined
  return () => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      timer = undefined
      fn.apply(this, arguments)
    }, ms)
  };
}

const MapComponent = () => {
  const [dimensions, setDimensions] = React.useState({ 
    height: window.innerHeight,
    width: window.innerWidth
  })
  React.useEffect(() => {
    const debouncedHandleResize = debounce(function handleResize() {
      setDimensions({
        height: window.innerHeight,
        width: window.innerWidth
      })
    }, 500)
    window.addEventListener('resize', debouncedHandleResize)

    return () => {
      window.removeEventListener('resize', debouncedHandleResize)
    }
  })
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
      mapStyle="https://api.maptiler.com/maps/442672a8-7228-4ab4-9780-83a9932987b5/style.json?key=NKY3xmA1haxXwc5Jm48B"
    >
      <GeolocateControl />
      <NavigationControl />
    </Map>
  );
};

export default MapComponent;