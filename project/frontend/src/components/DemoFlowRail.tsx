/** Hangi ekranda olunduğunu tek bakışta göstermek için (9 adımlı demo). */

const STEPS = [
  { n: 1, label: "CSV" },
  { n: 2, label: "Önizleme" },
  { n: 3, label: "Validation" },
  { n: 4, label: "Quality" },
  { n: 5, label: "Plan" },
  { n: 6, label: "Onay" },
  { n: 7, label: "Job" },
  { n: 8, label: "Sonuç" },
  { n: 9, label: "Explain" },
] as const;

export type DemoStageKey = "upload" | "dataset" | "plan" | "jobRun" | "result";

export default function DemoFlowRail(props: { stage: DemoStageKey }) {
  const activeThrough =
    props.stage === "upload"
      ? 1
      : props.stage === "dataset"
        ? 4
        : props.stage === "plan"
          ? 6
          : props.stage === "jobRun"
            ? 8
            : 9;

  return (
    <nav className="mb-8 rounded-xl border border-border bg-surface2 px-3 py-3" aria-label="Demo akışı">
      <p className="mb-2 text-center text-xs text-muted">
        Sıra rehberi — her ekranda hangi adımda olduğunuz kısa başlıkla da yazar; istekler{" "}
        <code className="rounded bg-border/40 px-1">docs/API_EXAMPLES.md</code> ile uyumludur.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-y-2">
        {STEPS.map((s, idx) => {
          const done = s.n < activeThrough;
          const current = s.n === activeThrough;
          return (
            <span key={s.n} className="flex items-center gap-1 sm:gap-2">
              <span
                className={
                  "flex h-7 min-w-7 items-center justify-center rounded-full px-1.5 text-xs font-semibold " +
                  (done
                    ? "bg-success/20 text-success"
                    : current
                      ? "bg-accent text-black"
                      : "bg-border/60 text-muted")
                }
                title={s.label}
              >
                {s.n}
              </span>
              <span className={"hidden text-xs sm:inline " + (current ? "font-medium text-text" : "text-muted")}>
                {s.label}
              </span>
              {idx < STEPS.length - 1 && <span className="px-0.5 text-muted sm:px-1">→</span>}
            </span>
          );
        })}
      </div>
    </nav>
  );
}
