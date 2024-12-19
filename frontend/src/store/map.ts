import { atom, computed, task, type Task} from "nanostores";
import { isBackendAvailable } from "./store";
import { BACKEND_URL, EXCLUDED_STATIONS } from "../data/constants";


export type FORECAST = {
    value: number,
    timestamp: string
}
export type STATION = {
    id: number,
    name: string,
    coordinates: number[],
    is_station_on: boolean,
    aqi_pm2_5: number
}

export type STATION_FORECAST = {
    aqi: number,
    forecast_6h: FORECAST[],
    forecast_12h: FORECAST[]
}
export const errorRegion = atom<string | undefined>(undefined)
export const loadingRegion = atom<boolean>(false)

export const fetchRegion = async () => {
    loadingRegion.set(true)
    try {
        const response = await fetch(BACKEND_URL + `/map?entity=region&id=${import.meta.env.PUBLIC_REGION_DEFAULT_ID}`);
        loadingRegion.set(false)
        return response.json()
    } catch(_){
        loadingRegion.set(false)
        errorRegion.set("There has been an error getting the region.")
        return undefined
    }
}

export const region = computed(isBackendAvailable, backendAvailable => task(async () => {
    if(!backendAvailable) {
        return undefined
    }
    return fetchRegion()
}))

export const errorStations = atom<string | undefined>(undefined)
export const loadingStations = atom<boolean>(false)

export const fetchStations = async () => {
    loadingStations.set(true)
    try {
        const stationsPromise = await fetch(import.meta.env.PUBLIC_BACKEND_URL + `/stations`)
        const s = await stationsPromise.json()
        const availableStations = s.filter((v: STATION) => v.is_station_on && !(EXCLUDED_STATIONS.includes(v.id)) )
        loadingStations.set(false)

        return availableStations;
    } catch(err){
        loadingStations.set(false)
        console.log("Error on fetching station data", err)
        errorStations.set("Error getting the stations")
        return undefined
    }
}

export const stations = computed(isBackendAvailable, (backendAvailable): Task<STATION[]> => task(async () => {
    if(!backendAvailable) {
        return undefined
    }
    return fetchStations()
  }))


export const fetchForecast = async (id: number) => {
    try {
        const forecast = await fetch(BACKEND_URL + `/map?entity=station&id=${id}`)
        if(forecast.status !== 200) {
                return undefined
        }
        return forecast.json()

    } catch(err){
        console.log("Error on fetching forecast data", err)
        errorStations.set(`Error getting forecast of station ${id}`)
        return undefined
    }
}
export const selectedStationId =  atom<number | undefined>(undefined)

export const setSelectedStation = (station_id: number | undefined) => {
    selectedStationId.set(station_id);
}

export const selectedStation = computed([isBackendAvailable, selectedStationId, stations], (backendAvailable, id, stations) : Task<STATION & STATION_FORECAST> => task(async () => {
    if(!backendAvailable) {
        return undefined
    }
    if(!id || !stations) {
        return undefined
    }
    const stationForecast = await fetchForecast(id)
    const station = stations.filter((s: STATION) => s.id === id)[0]
    return {...station, ...stationForecast}
  }))







