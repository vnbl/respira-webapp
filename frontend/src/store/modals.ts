import { atom } from "nanostores";

export const isShareModalOpen = atom<boolean>(false)
export const toggleShareModal = (value:boolean) => {
  isShareModalOpen.set(value)
}

export const isRecommendationsModalOpen = atom<boolean>(false)
export const toggleRecommendationsModal = (value:boolean) => {
  isRecommendationsModalOpen.set(value)
}


export const isAlertModalOpen = atom<boolean>(false)
export const toggleAlertModal = (value:boolean) => {
  isAlertModalOpen.set(value)
}