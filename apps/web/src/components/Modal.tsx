"use client";

import React, { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";

/**
 * Native modal dialog. The browser traps focus inside it, closes it on Escape (routed to
 * onClose so React state stays the source of truth), and returns focus to the opener.
 */
export function DialogShell({ onClose, label, labelledBy, className = "max-w-lg border-slate-200", children }: {
  onClose: () => void;
  label?: string;
  labelledBy?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    // React removes the element before this cleanup runs, so the browser cannot restore
    // focus on its own; remember the opener and return focus to it.
    const opener = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) {
      dialog.showModal();
      // Start on the first field (e.g. the MRN), not the close button.
      dialog.querySelector<HTMLElement>("input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])")?.focus();
    }
    return () => {
      dialog?.close();
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={label}
      aria-labelledby={labelledBy}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      // !m-auto: parent `space-y-*` rules would otherwise override the native centring margin.
      className={`motion-dialog-in glass-panel !m-auto w-[calc(100%-2rem)] rounded-xl border shadow-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto text-slate-800 backdrop:bg-slate-900/50 backdrop:backdrop-blur-sm ${className}`}
    >
      {children}
    </dialog>
  );
}

export default function Modal({ title, icon: Icon, onClose, children, tone = "border-slate-200" }: {
  title: string; icon: React.ElementType; onClose: () => void; children: React.ReactNode; tone?: string;
}) {
  const titleId = useId();
  return (
    <DialogShell onClose={onClose} labelledBy={titleId} className={`max-w-lg ${tone}`}>
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <h2 id={titleId} className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Icon className="w-5 h-5 text-brand-700" aria-hidden="true" />
          {title}
        </h2>
        <button type="button" onClick={onClose} aria-label="Close" className="p-1 -m-1 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100">
          <X className="w-5 h-5" />
        </button>
      </div>
      {children}
    </DialogShell>
  );
}
