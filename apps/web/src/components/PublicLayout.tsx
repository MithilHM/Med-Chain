import React from "react";
import { CalendarCheck, FileHeart, Phone, ShieldCheck } from "lucide-react";

const POINTS = [
  { icon: FileHeart, title: "Your records in one place", text: "Visits, diagnoses, prescriptions, and lab results from your care team." },
  { icon: ShieldCheck, title: "You decide who sees them", text: "Grant or withdraw research consent at any time. Every access is logged." },
  { icon: CalendarCheck, title: "Built for care teams", text: "Clinicians see the patients they treat, with hospital single sign-on." },
];

/** Two-column layout for the public sign-in and sign-up pages. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section className="hidden lg:flex flex-col justify-between bg-brand-700 text-white px-12 py-12">
        <div className="max-w-md space-y-8">
          <div>
            <h1 className="text-3xl font-bold leading-tight text-white">Secure access to clinical records</h1>
            <p className="mt-3 text-brand-100 text-[15px] leading-relaxed">
              For patients of participating hospitals and the clinicians who care for them.
            </p>
          </div>
          <ul className="space-y-5">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="w-10 h-10 shrink-0 rounded-lg bg-white/10 flex items-center justify-center">
                  <Icon className="w-5 h-5 text-white" />
                </span>
                <span>
                  <span className="block font-semibold text-white">{title}</span>
                  <span className="block text-sm text-brand-100 leading-relaxed">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="max-w-md flex items-start gap-3 rounded-lg bg-white/10 px-4 py-3 text-sm text-white">
          <Phone className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            <strong className="font-semibold">Medical emergency?</strong> Do not use this portal. Call your local emergency number or go to the nearest emergency department.
          </span>
        </div>
      </section>

      <section className="flex items-start lg:items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">{children}</div>
      </section>
    </div>
  );
}
