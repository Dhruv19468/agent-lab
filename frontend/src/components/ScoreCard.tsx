// How good one generated test plan is. The bar *is* the formula:
//   overall = (0.25·structure + 0.45·coverage + 0.30·similarity) × faithfulness
// Each weight is a slot in the bar; the filled part of a slot is that metric's score.
// Faithfulness then scales the whole filled length, shown by the marker.

import { Check, Minus, X } from "lucide-react";
import { useState } from "react";

import type { Claim, CoveragePoint, Evaluation, SectionScore } from "../lib/types";
import { Badge, Table, Td, Th, cx } from "./ui";

const SLOTS = [
  { key: "structure", label: "Structure", weight: 0.25, color: "bg-ink-700", help: "required sections present" },
  { key: "coverage", label: "Coverage", weight: 0.45, color: "bg-signal-500", help: "reference points covered" },
  { key: "similarity", label: "Similarity", weight: 0.3, color: "bg-ink-400", help: "word overlap with reference" },
] as const;

export function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? "–" : `${(value * 100).toFixed(digits)}%`;
}

export function scoreTone(value: number | null | undefined): "ok" | "signal" | "bad" | "neutral" {
  if (value == null) return "neutral";
  if (value >= 0.7) return "ok";
  if (value >= 0.45) return "signal";
  return "bad";
}

function FormulaBar({ evaluation }: { evaluation: Evaluation }) {
  const faithfulness = evaluation.faithfulness ?? 1;
  const weighted = SLOTS.reduce((sum, slot) => sum + slot.weight * (evaluation[slot.key] ?? 0), 0);
  return (
    <div>
      <div className="relative flex h-9 overflow-hidden rounded border border-line bg-paper">
        {SLOTS.map((slot) => (
          <div key={slot.key} className="relative h-full border-r border-surface last:border-r-0" style={{ width: `${slot.weight * 100}%` }}>
            <div className={cx("h-full", slot.color)} style={{ width: `${(evaluation[slot.key] ?? 0) * 100}%` }} />
          </div>
        ))}
        {/* faithfulness shrinks the weighted score to the overall: the marker shows where it lands */}
        <div
          className="absolute inset-y-0 w-0.5 bg-bad-600"
          style={{ left: `${weighted * faithfulness * 100}%` }}
          title={`overall = ${pct(weighted, 1)} × faithfulness ${pct(faithfulness, 0)}`}
        />
      </div>
      <div className="mt-1.5 flex text-xs text-ink-500">
        {SLOTS.map((slot) => (
          <div key={slot.key} style={{ width: `${slot.weight * 100}%` }} className="pr-2">
            {slot.label} · {slot.weight * 100}%
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, help }: { label: string; value: number | null; help: string }) {
  return (
    <div className="min-w-0">
      <p className="text-sm text-ink-500">{label}</p>
      <p className="font-mono text-xl text-ink-950">{pct(value)}</p>
      <p className="text-xs text-ink-400">{help}</p>
    </div>
  );
}

function SectionsTable({ sections }: { sections: SectionScore[] }) {
  return (
    <Table
      head={
        <>
          <Th>Section</Th>
          <Th className="text-center">In plan</Th>
          <Th className="text-center">In reference</Th>
          <Th className="text-right">Points covered</Th>
          <Th className="text-right">Similarity</Th>
        </>
      }
    >
      {sections.map((section) => (
        <tr key={section.key} className={cx(section.required && !section.inPlan && "bg-bad-50/60")}>
          <Td>
            {section.title}
            {!section.required && <span className="ml-2 text-xs text-ink-400">optional</span>}
          </Td>
          <Td className="text-center">
            {section.inPlan ? <Check className="mx-auto size-4 text-ok-600" aria-label="yes" /> : <X className="mx-auto size-4 text-bad-600" aria-label="no" />}
          </Td>
          <Td className="text-center">
            {section.inReference ? <Check className="mx-auto size-4 text-ink-500" aria-label="yes" /> : <Minus className="mx-auto size-4 text-ink-200" aria-label="no" />}
          </Td>
          <Td className="text-right font-mono text-sm">{section.points ? `${section.covered} / ${section.points}` : "–"}</Td>
          <Td className="text-right font-mono text-sm">{pct(section.similarity)}</Td>
        </tr>
      ))}
    </Table>
  );
}

function Quote({ children }: { children: string }) {
  return <q className="text-ink-500 italic">{children}</q>;
}

function PointsList({ points }: { points: CoveragePoint[] }) {
  if (points.length === 0) return <p className="text-ink-500">Every reference point is covered.</p>;
  return (
    <ul className="divide-y divide-line">
      {points.map((point, index) => (
        <li key={index} className="py-2.5">
          <p>
            <span className="mr-2 font-mono text-xs text-ink-400">{point.section}</span>
            {point.point}
          </p>
          <p className="mt-0.5 text-sm">
            Reference: <Quote>{point.quote}</Quote>
          </p>
          {point.note && <p className="text-xs text-bad-600">{point.note}</p>}
        </li>
      ))}
    </ul>
  );
}

function ClaimsList({ claims }: { claims: Claim[] }) {
  if (claims.length === 0) return <p className="text-ink-500">Every checked claim is backed by the BRD or the diagram.</p>;
  return (
    <ul className="divide-y divide-line">
      {claims.map((claim, index) => (
        <li key={index} className="py-2.5">
          <p>{claim.claim}</p>
          <p className="mt-0.5 text-sm">
            Plan says: <Quote>{claim.planQuote}</Quote>
          </p>
          {claim.note && <p className="text-xs text-bad-600">{claim.note}</p>}
        </li>
      ))}
    </ul>
  );
}

type Detail = "sections" | "missed" | "unsupported";

export function ScoreCard({ evaluation }: { evaluation: Evaluation }) {
  const [detail, setDetail] = useState<Detail>("sections");
  const { details } = evaluation;
  const missed = (details.points ?? []).filter((point) => !point.covered);
  const unsupported = (details.claims ?? []).filter((claim) => claim.support === "none");
  const counts = details.counts;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
        <div>
          <p className="text-sm text-ink-500">Overall</p>
          <p className="font-mono text-[38px] leading-none font-semibold tracking-tight text-ink-950">{pct(evaluation.overall, 1)}</p>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric label="Structure" value={evaluation.structure} help={`${20 - (details.missingRequired?.length ?? 0)} of 20 required sections`} />
          <Metric label="Coverage" value={evaluation.coverage} help={counts ? `${counts.covered} of ${counts.points} reference points` : "reference points"} />
          <Metric label="Similarity" value={evaluation.similarity} help="word overlap, per section" />
          <Metric
            label="Faithfulness"
            value={evaluation.faithfulness}
            help={counts ? `${counts.supported} of ${counts.claims} claims backed` : "claims backed by BRD"}
          />
        </div>
      </div>

      <FormulaBar evaluation={evaluation} />
      <p className="text-sm text-ink-500">
        Overall = (0.25 × structure + 0.45 × coverage + 0.30 × similarity) × faithfulness. Reference: {evaluation.referenceSource === "gold" ? "gold answer key" : "the human test plan"}{" "}
        for {evaluation.project}. Judge: {evaluation.judgeModel}.
      </p>

      <div role="tablist" className="flex gap-2">
        {(
          [
            ["sections", "Sections"],
            ["missed", `Missed points (${missed.length})`],
            ["unsupported", `Unsupported claims (${unsupported.length})`],
          ] as Array<[Detail, string]>
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={detail === id}
            onClick={() => setDetail(id)}
            className={cx(
              "rounded-full border px-3 py-1 text-sm",
              detail === id ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong text-ink-700 hover:border-ink-400",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {detail === "sections" && details.sections && <SectionsTable sections={details.sections} />}
      {detail === "missed" && <PointsList points={missed} />}
      {detail === "unsupported" && <ClaimsList claims={unsupported} />}
    </div>
  );
}

export function ScoreBadge({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-ink-400">–</span>;
  return <Badge tone={scoreTone(value)}>{pct(value, 1)}</Badge>;
}
