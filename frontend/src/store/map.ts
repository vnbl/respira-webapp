import { atom, computed, task } from "nanostores";
import { isBackendAvailable } from "./store";
import { createFetcherStore } from "./fetcher";
import { shared } from '@it-astro:request-nanostores';

export const fetchRegion = async () => {
    try {
        const response = await fetch(import.meta.env.PUBLIC_BACKEND_URL + `/map?entity=region&id=${import.meta.env.PUBLIC_REGION_DEFAULT_ID}`);
        return response.json()
    } catch(_){
        console.log("Error on fetching map data")
        errorStations.set(true)
        return undefined
    }
}


export const fetchStations = async () => {
    try {
        console.log(import.meta.env.BACKEND_URL)
        const stationsPromise = await fetch(import.meta.env.PUBLIC_BACKEND_URL + `/stations`)
        const s = await stationsPromise.json()
        const availableStations = s.filter(v => v.is_station_on)
        const parsedStations = await Promise.all(availableStations.map(async (value) => {
            const forecastPromise = await fetch(import.meta.env.PUBLIC_BACKEND_URL + `/stations/${value.id}/forecast`)
            if(forecastPromise.status !== 200) {
                return undefined
            }
            const f = await forecastPromise.json()
            return {...value, ...f}
        }))
        return parsedStations.filter( Boolean )

    } catch(err){
        console.log("Error on fetching station data", err)
        errorStations.set(true)
        return undefined
    }
}


export const data = shared('data', atom<any>(undefined))

// export const stations = shared('stations', atom<any>(undefined))

// export const stations = computed((bac'stations')

export const stations = computed(isBackendAvailable, backendAvailable => task(async () => {
    if(!backendAvailable) {
        return undefined
    }
    return fetchStations()
  }))



export const region = computed(isBackendAvailable, backendAvailable => task(async () => {
    if(!backendAvailable) {
        return undefined
    }
    return fetchRegion()
  }))


export const selectedStation = shared('selectedStation', atom<any>(undefined))

export const setSelectedStation = (station) => {
    console.log(station)
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
