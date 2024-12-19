import { atom, computed, task, type Task } from "nanostores";
import { isBackendAvailable } from "./store";
import { BACKEND_URL } from "../data/constants";
import type { FORECAST, STATION } from "./map";
import { shared } from '@it-astro:request-nanostores';


export type HISTORIC_FORECAST = {
  aqi_level: FORECAST[],
  forecast_6h: FORECAST[],
  forecast_12h: FORECAST[]
}

export const statisticsSelectedStation =  shared('statisticsSelectedStation',atom<STATION | undefined>(undefined))

export const errorHistoricForecast = atom<string | undefined>(undefined)
export const loadingHistoricForecast = atom<boolean>(false)

export const fetchHistoricForecast = async (stationId: number) => {
  loadingHistoricForecast.set(true)
  try {
    const response = await fetch(BACKEND_URL + `/stations/${stationId}/forecast`);
    loadingHistoricForecast.set(false)
    console.log("response")
    console.log(response)
    return response.json()
  } catch (_) {
    loadingHistoricForecast.set(false)
    errorHistoricForecast.set("There has been an error getting the region.")
    return undefined
  }
}

export const historicForecastData = computed([isBackendAvailable, statisticsSelectedStation], (backendAvailable, station): Task<HISTORIC_FORECAST> => task(async () => {
  console.log(backendAvailable, station)
  if (!backendAvailable) {
    return undefined
  }
  if (!station) {
    return undefined
  }
  return fetchHistoricForecast(station.id)
}))




export const errorBoxplotWeek = atom<string | undefined>(undefined)
export const loadingBoxplotWeek = atom<boolean>(false)

export const fetchBoxplotWeek = async (stationId: number) => {
  loadingBoxplotWeek.set(true)
  try {
    const response = await fetch(BACKEND_URL + `/stations/${stationId}/boxplot/?period=7d`);
    loadingBoxplotWeek.set(false)
    return response.json()
  } catch (_) {
    loadingBoxplotWeek.set(false)
    errorBoxplotWeek.set("There has been an error getting the region.")
    return undefined
  }
}

export const boxplotWeekData = computed([isBackendAvailable, statisticsSelectedStation], (backendAvailable, station): Task<HISTORIC_FORECAST> => task(async () => {
  console.log(backendAvailable, station)
  if (!backendAvailable) {
    return undefined
  }
  if (!station) {
    return undefined
  }
  return fetchBoxplotWeek(station.id)
}))


export const errorBoxplotMonth = atom<string | undefined>(undefined)
export const loadingBoxplotMonth= atom<boolean>(false)

export const fetchBoxplotMonth = async (stationId: number) => {
  loadingBoxplotMonth.set(true)
  try {
    const response = await fetch(BACKEND_URL + `/stations/${stationId}/boxplot/?period=30d`);
    loadingBoxplotMonth.set(false)
    return response.json()
  } catch (_) {
    loadingBoxplotMonth.set(false)
    errorBoxplotMonth.set("There has been an error getting the region.")
    return undefined
  }
}

export const boxplotMonthData = computed([isBackendAvailable, statisticsSelectedStation], (backendAvailable, station): Task<HISTORIC_FORECAST> => task(async () => {
  console.log(backendAvailable, station)
  if (!backendAvailable) {
    return undefined
  }
  if (!station) {
    return undefined
  }
  return fetchBoxplotMonth(station.id)
}))

export const errorBoxplotYear = atom<string | undefined>(undefined)
export const loadingBoxplotYear= atom<boolean>(false)

export const fetchBoxplotYear = async (stationId: number) => {
  loadingBoxplotYear.set(true)
  try {
    const response = await fetch(BACKEND_URL + `/stations/${stationId}/boxplot/?period=1y`);
    loadingBoxplotYear.set(false)
    return response.json()
  } catch (_) {
    loadingBoxplotYear.set(false)
    errorBoxplotYear.set("There has been an error getting the region.")
    return undefined
  }
}

export const boxplotYearData = computed([isBackendAvailable, statisticsSelectedStation], (backendAvailable, station): Task<HISTORIC_FORECAST> => task(async () => {
  console.log(backendAvailable, station)
  if (!backendAvailable) {
    return undefined
  }
  if (!station) {
    return undefined
  }
  return fetchBoxplotYear(station.id)
}))








