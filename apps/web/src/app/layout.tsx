import "./globals.css";
import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";

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
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-gradient-to-b from-slate-950 via-slate-900/30 to-slate-950">
            <div className="max-w-7xl mx-auto space-y-6">
              {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
