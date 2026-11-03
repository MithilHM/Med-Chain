"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Database, Play, ShieldCheck } from "lucide-react";
import { ApiClient } from "@/lib/api";

type QueryInfo = { id: string; title: string; description: string };
type QueryResult = {
  id: string;
  title: string;
  sql: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  dialect: string;
  disclaimer: string;
};

export default function DbmsShowcasePage() {
  const [queries, setQueries] = useState<QueryInfo[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    ApiClient.getDbmsShowcaseQueries()
      .then((items) => {
        if (!active) return;
        setQueries(items);
        setSelectedId(items[0]?.id ?? "");
      })
      .catch((err: Error) => active && setError(err.message))
      .finally(() => active && setLoadingCatalog(false));
    return () => { active = false; };
  }, []);

  const runQuery = async (queryId: string) => {
    setSelectedId(queryId);
    setRunning(true);
    setError(null);
    try {
      const data = await ApiClient.runDbmsShowcaseQuery(queryId);
      setResult(data);
    } catch (err: any) {
      setResult(null);
      setError(err.message || "Unable to execute the selected query.");
    } finally {
      setRunning(false);
    }
  };

  const selectedQuery = queries.find((query) => query.id === selectedId);

  return (
    <div className="space-y-7 animate-in fade-in duration-200">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link href="/admin" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-300">
            <ArrowLeft className="h-3.5 w-3.5" /> System administration
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Database className="h-6 w-6 text-cyan-400" /> Relational DBMS Showcase
          </h1>
          <p className="mt-1 text-xs text-slate-400">Run fixed, read only examples against the configured relational database.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-[11px] text-emerald-300">
          <ShieldCheck className="h-4 w-4" /> Admin only · fixed query set · no patient identifiers in results
        </div>
      </div>

      {error && <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200">{error}</div>}

      {loadingCatalog ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 text-sm text-slate-400">Loading query catalog…</div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
          <section className="space-y-2">
            {queries.map((query) => (
              <button
                key={query.id}
                onClick={() => runQuery(query.id)}
                disabled={running}
                className={`w-full rounded-xl border p-4 text-left transition-colors ${selectedId === query.id ? "border-cyan-500/40 bg-cyan-500/10" : "border-slate-800 bg-slate-900/50 hover:border-slate-700"}`}
              >
                <span className="flex items-center justify-between gap-2 text-xs font-semibold text-white">
                  {query.title}<Play className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                </span>
                <span className="mt-2 block text-[11px] leading-relaxed text-slate-400">{query.description}</span>
              </button>
            ))}
            {!queries.length && <p className="rounded-xl border border-slate-800 p-4 text-xs text-slate-400">No showcase queries are available.</p>}
          </section>

          <section className="min-w-0 space-y-4">
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50">
              <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
                <h2 className="text-xs font-semibold text-white">{result?.title ?? selectedQuery?.title ?? "Query"}</h2>
                {result && <span className="text-[10px] font-mono text-slate-400">{result.dialect} · {result.row_count} rows</span>}
              </div>
              <pre className="max-h-72 overflow-auto p-4 text-[11px] leading-relaxed text-cyan-100"><code>{result?.sql ?? "Choose a query to view its SQL and results."}</code></pre>
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50">
              <div className="border-b border-slate-800 px-4 py-3 text-xs font-semibold text-white">Query results</div>
              {running ? (
                <p className="p-5 text-xs text-slate-400">Executing read only query…</p>
              ) : result?.rows.length ? (
                <div className="max-h-[28rem] overflow-auto">
                  <table className="w-full text-left text-[11px]">
                    <thead className="sticky top-0 bg-slate-950 text-slate-400">
                      <tr>{result.columns.map((column) => <th key={column} className="whitespace-nowrap px-4 py-3 font-semibold">{column}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {result.rows.map((row, index) => (
                        <tr key={index} className="text-slate-200">
                          {result.columns.map((column) => <td key={column} className="whitespace-nowrap px-4 py-3 font-mono">{String(row[column] ?? "—")}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-5 text-xs text-slate-400">{result ? "No rows met the query criteria." : "Run a query to see its result."}</p>
              )}
              {result && <p className="border-t border-slate-800 px-4 py-3 text-[10px] text-slate-500">{result.disclaimer}</p>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
