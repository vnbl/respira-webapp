import React from "react";
import type { PropsWithChildren } from "react";
import Close from "../../assets/icons/close_icon.svg?react"

type Props = {
  showModal: boolean;
  toggleModal: (value: boolean) => void;
  title?: string,
  props?: any,
  renderHeader?: boolean
}

export default function Modal({ showModal, toggleModal, title, children, renderHeader=true}: PropsWithChildren<Props>) {
  return (
    <>
      {showModal ? (
        <>
          <div
            className="justify-center items-center flex overflow-x-hidden overflow-y-auto fixed inset-0 z-50 outline-none focus:outline-none overscroll-contain"
          >
            <div className="relative w-auto mt-4 mx-auto max-w-3xl max-h-auto">
              <div className="border-0 rounded-lg shadow-lg relative flex flex-col w-full bg-base outline-none focus:outline-none ">
                {renderHeader && <div className="flex flex-row justify-between p-5 rounded-t items-center  flex-grow ">
                  <h3 className="text-xl font-serif mr-12">
                    {title || ""}
                  </h3>
                  <button
                    className="p-1 ml-auto bg-transparent border-0 text-black float-right text-3xl leading-none font-semibold "
                    onClick={() => toggleModal(false)}
                  >
                    <Close height={17} width={17} />
                  </button>
                </div>}

                {children}

              </div>
            </div>
          </div>
          <div className="opacity-25 fixed inset-0 z-40 bg-black"></div>
        </>
      ) : null}
    </>
  );
}
