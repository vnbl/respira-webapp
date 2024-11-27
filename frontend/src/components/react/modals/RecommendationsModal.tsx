import React from "react"
import Modal from "../Modal"
import { useStore } from "@nanostores/react"
import { isRecommendationsModalOpen, toggleRecommendationsModal } from "../../../store/modals"
import { BASE_URL, FACEBOOK_SHARE, TELEGRAM_SHARE, TELEGRAM_URL, TWITTER_SHARE } from "../../../data/constants";
import { RECOMMENDATIONS_IMAGES } from "../../../data/images";
import { RecommendationTabs } from "../RecommendationTabs";
import { RecommendationSelect } from "../RecommendationSelect";


const RecommendationsModal = () => {
  const isOpen = useStore(isRecommendationsModalOpen)
  return (
    <Modal showModal={isOpen} toggleModal={toggleRecommendationsModal}>
      <div className="px-6 pb-6 justify-center md:min-w-[48rem] max-h-2/3 overflow-auto" style={{maxHeight: window.innerHeight * 0.8}}>
        <h1 className="font-serif font-bold text-[1.5rem] md:text-[2rem] text-gray mb-6">Recomendaciones por nivel</h1>
        {window.innerWidth < 640  && <RecommendationSelect/>}
        <RecommendationTabs />
        <h3 className="font-sans font-semibold text-[1.875rem]  text-gray text-center">¿Quiénes son las personas sensibles?</h3>
        <div className="grid md:grid-flow-col md:grid-cols-none grid-cols-2  gap-2 pt-6 justify-items-center">
          {RECOMMENDATIONS_IMAGES.map((image, key) => (
            <img key={key} alt={image.alt} src={image.path.src} height={100} width={100} className="col-span-1" />
          ))}
        </div>

      </div>
    </Modal>
  )
}

export { RecommendationsModal }