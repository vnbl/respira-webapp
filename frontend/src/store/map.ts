import { atom, computed, task } from "nanostores";
import { isBackendAvailable } from "./store";
import { createFetcherStore } from "./fetcher";


// export const $data = createFetcherStore<any>([import.meta.env.BACKEND_URL + '/map?entity=region']);

export const fetchMap = async () => {
    try {
        const response = await fetch(import.meta.env.BACKEND_URL + '/map?entity=region');
        return response.json()
    } catch(_){
        console.log("Error on fetching map data")
        error.set(true)
    }
}




export const error = atom<boolean>(false)

export const data=computed([isBackendAvailable], (backendAvailable) => task(async () => {
    if(!backendAvailable){
        console.log("returning early")
        return 
    }
    return fetchMap();
}))

export const loading = computed([data], (data) => {
    if(!data){
        return true
    } else {
        return false
    }
})
