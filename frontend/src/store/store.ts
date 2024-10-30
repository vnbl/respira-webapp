import { atom, computed, task, onMount } from 'nanostores';
import { shared } from '@it-astro:request-nanostores';
import { allTasks } from 'nanostores'

type STATION = {
    id: number,
    name: string,
    coordinates: string[],
    is_station_on: boolean,
    
}

export const backendHealthCheck= async () => {
    try {
        console.log(import.meta.env.PUBLIC_BACKEND_URL )
        const response = await fetch(import.meta.env.PUBLIC_BACKEND_URL + '/health');
        if(response.status !== 200) {
           return false
        }
        return true
    } catch (_) {
        console.log("Backend not available")
        return false
    }
}


export const isBackendAvailable = atom<boolean>(false)

onMount(isBackendAvailable, () => {
    task(async () => {
        isBackendAvailable.set(await backendHealthCheck())
    })
  })

isBackendAvailable.listen(() => {})
await allTasks()
