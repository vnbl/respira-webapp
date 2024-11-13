import React from "react"
import Modal from "../Modal"
import { useStore } from "@nanostores/react"
import { isShareModalOpen, toggleShareModal } from "../../../store/modals"
import Copy from "../../../assets/icons/copy_icon.svg?react";
import Telegram from "../../../assets/icons/telegram_icon_gray.svg?react"
import Facebook from "../../../assets/icons/facebook_icon_gray.svg?react"
import Twitter from "../../../assets/icons/x_icon_gray.svg?react"

import { BASE_URL, FACEBOOK_SHARE, TELEGRAM_SHARE, TELEGRAM_URL, TWITTER_SHARE } from "../../../data/constants";


const ShareModal = () => {
  const isOpen = useStore(isShareModalOpen)
  return (
    <Modal showModal={isOpen} toggleModal={toggleShareModal} title="Comparti el link">
      <div className="flex flex-col pt-0 p-6 ">

        <div className="w-full px-2 border-[0.5px] mb-4"></div>
        <div className="flex flex-row space-x-4 justify-between">
          <a href={TELEGRAM_SHARE} target="_blank">
            <Telegram height={50} width={50} />
          </a>
          <a href={FACEBOOK_SHARE} target="_blank" data-href="" >
            <Facebook height={50} width={50} />
          </a>
          <a href={TWITTER_SHARE} target="_blank" data-href="" >
            <Twitter height={50} width={50} />
          </a>
        </div>
        <h5 className="text-md uppercase font-semibold font-sans mt-6 mb-2">Link de la página</h5>
        <div
          className="bg-white rounded-lg border-lightgray border-2 p-3 flex flex-row items-center w-98"
        >
          <p className="text-lightgray font-sans flex-grow max-w-2/3 text-ellipsis">{BASE_URL}</p>
          <button className="copy">
            <Copy />
          </button>
        </div>
      </div>
    </Modal>
  )
}

export { ShareModal }