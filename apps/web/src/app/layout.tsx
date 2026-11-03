import "./globals.css";
import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import AuthShell from "@/components/AuthShell";

export const metadata: Metadata = {
  title: "MedChain | Privacy-Preserving Healthcare Intelligence & Audit Database",
  description: "Advanced multi-model DBMS platform integrating PostgreSQL, MongoDB, Neo4j, and EVM smart contracts.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 flex flex-col min-h-screen">
        <Navbar />
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
