import { atom, task, onMount } from 'nanostores';
import { allTasks } from 'nanostores'
import { BACKEND_URL } from '../data/constants';



export const backendHealthCheck= async () => {
    try {
        const response = await fetch(BACKEND_URL + '/health');
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
