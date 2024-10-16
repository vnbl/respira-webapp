import { atom, computed, task } from "nanostores";
import { isBackendAvailable } from "./store";
import { createFetcherStore } from "./fetcher";
import { shared } from '@it-astro:request-nanostores';

export const fetchRegion = async () => {
    try {
        if(!isBackendAvailable.get()) {
            console.log("Error on fetching map data")
            errorStations.set(true)
        }
        const response = await fetch(import.meta.env.BACKEND_URL + `/map?entity=region&id=${import.meta.env.REGION_DEFAULT_ID}`);
        data.set(await response.json())
    } catch(_){
        console.log("Error on fetching map data")
        errorStations.set(true)
    }
}


export const fetchStations = async () => {
    try {
        if(!isBackendAvailable.get()) {
            console.log("Error on fetching stations data")
            error.set(true)
        }
        const stationsPromise = await fetch(import.meta.env.BACKEND_URL + `/stations`)
        const s = await stationsPromise.json()
        const availableStations = s.filter(v => v.is_station_on)
        const parsedStations = await Promise.all(availableStations.map(async (value) => {
            const forecastPromise = await fetch(import.meta.env.BACKEND_URL + `/stations/${value.id}/forecast`)
            if(forecastPromise.status !== 200) {
                return undefined
            }
            const f = await forecastPromise.json()
            return {...value, ...f}
        }))
        stations.set(parsedStations.filter( Boolean ))

    } catch(err){
        console.log("Error on fetching station data", err)
        errorStations.set(true)
    }
}


export const data = shared('data', atom<any>(undefined))

export const stations = shared('stations', atom<any>(undefined))

export const selectedStation = shared('selectedStation', atom<any>(undefined))

export const setSelectedStation = (station) => {
    selectedStation.set(station)
    console.log("setting station")
}


export const error = atom<boolean>(false)


export const errorStations = atom<boolean>(false)

export const loading=computed([data], (data) => {
    if(!data){
        return true
    } else {
        return false
    }
})
