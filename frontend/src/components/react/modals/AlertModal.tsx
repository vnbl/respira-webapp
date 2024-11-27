import React from "react"
import Modal from "../Modal"
import { useStore } from "@nanostores/react"
import { isAlertModalOpen, toggleAlertModal } from "../../../store/modals"
import Close from "../../../assets/icons/close_icon.svg?react"


const AlertModal = (props: any) => {
  const isOpen = useStore(isAlertModalOpen)
  return (
    <Modal showModal={isOpen} toggleModal={toggleAlertModal} renderHeader={false}>
      <div className="flex flex-row rounded-t items-center flex-grow h-12">
        <div className="w-1/2 h-full bg-bg-gray rounded-tl-lg "></div>
        <div className="w-1/2 bg-cyan p-2 h-full rounded-tr-lg"> 
        <button
          className="p-1 ml-auto bg-transparent border-0 text-black float-right text-3xl leading-none font-semibold "
          onClick={() => toggleAlertModal(false)}
        >
          <Close height={17} width={17} />
        </button></div>


      </div>
      <div className="flex flex-row  max-w-[96rem] rounded-b-lg overflow-clip">
        <div className="w-1/2">{props.left}</div>
        <div className="w-1/2">{props.right}</div>
      </div>
    </Modal>
  )
}

export { AlertModal }