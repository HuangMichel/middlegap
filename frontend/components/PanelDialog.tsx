'use client';
import { useEffect, useRef } from 'react';

export default function PanelDialog({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="settings-dialog"
      aria-labelledby="settings-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header className="drawer-header">
        <h2 id="settings-title">Workspace settings</h2>
        <button aria-label="Close workspace settings" onClick={onClose}>
          Close ×
        </button>
      </header>
      <div className="settings-body">{children}</div>
    </dialog>
  );
}
