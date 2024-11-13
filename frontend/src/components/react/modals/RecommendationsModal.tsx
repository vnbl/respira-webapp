import React from "react"
import Modal from "../Modal"
import { useStore } from "@nanostores/react"
import { isRecommendationsModalOpen, toggleRecommendationsModal } from "../../../store/modals"

import { BASE_URL, FACEBOOK_SHARE, TELEGRAM_SHARE, TELEGRAM_URL, TWITTER_SHARE } from "../../../data/constants";


const RecommendationsModal = () => {
  const isOpen = useStore(isRecommendationsModalOpen)
  return (
    <Modal showModal={isOpen} toggleModal={toggleRecommendationsModal}>

    </Modal>
  )
}

export { RecommendationsModal }