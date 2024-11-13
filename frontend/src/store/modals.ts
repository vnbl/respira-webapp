import { atom } from "nanostores";

export const isShareModalOpen = atom<boolean>(true)
export const toggleModal = (value:boolean) => {
  isShareModalOpen.set(value)
}