import React from "react"
import Modal from "../Modal"
import { useStore } from "@nanostores/react"
import { isShareModalOpen, toggleModal } from "../../../store/modals"
import Copy from "../../../assets/icons/copy_icon.svg?react";
import { TELEGRAM_URL } from "../../../data/constants";


const ShareModal = () => {
  const isOpen = useStore(isShareModalOpen)
  return (
    <Modal showModal={isOpen} toggleModal={toggleModal} title="Comparti el link">
      <h5 className="text-md uppercase font-semibold font-sans">Link de la página</h5>
      <div
        className="bg-white rounded-lg border-lightgray border-2 p-3 flex flex-row items-center"
      >
        <p className="text-lightgray font-sans flex-grow max-w-2/3 text-ellipsis">{TELEGRAM_URL}</p>
        <button className="copy">
          <Copy />
        </button>
      </div>
    </Modal>
  )
}

export { ShareModal }