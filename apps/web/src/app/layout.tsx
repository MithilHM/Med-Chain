import "./globals.css";
import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import AuthShell from "@/components/AuthShell";

export const metadata: Metadata = {
  title: "MedChain Health | Clinical Records Portal",
  description: "Secure clinical records, patient consent, and audited data sharing for hospital care teams and patients.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex flex-col min-h-screen">
        <Navbar />
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
