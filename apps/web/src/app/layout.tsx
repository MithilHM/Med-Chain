import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Navbar from "@/components/Navbar";
import AuthShell from "@/components/AuthShell";

// Self-hosted at build time, so every workstation renders the same face instead of
// whatever sans-serif the operating system happens to have.
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });

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
    <html lang="en" className={inter.variable}>
      <body className="flex flex-col min-h-screen">
        <Navbar />
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
