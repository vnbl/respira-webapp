import { atom } from "nanostores";

export const isShareModalOpen = atom<boolean>(false)
export const toggleModal = (value:boolean) => {
  isShareModalOpen.set(value)
}