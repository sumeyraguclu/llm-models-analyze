import { useState } from "react";

import type { AnalysisPlan, ModelMetrics } from "./types";
import DatasetPage from "./components/DatasetPage";
import DemoFlowRail, { type DemoStageKey } from "./components/DemoFlowRail";
import JobRunPage from "./components/JobRunPage";
import PlanPage from "./components/PlanPage";
import ResultPage from "./components/ResultPage";
import UploadPage from "./components/UploadPage";

type AppState =
  | { stage: "upload" }
  | { stage: "dataset"; datasetId: number; tableName: string; preferredTemplate?: string }
  | { stage: "plan"; datasetId: number; tableName: string; preferredTemplate?: string; planUserGoal?: string }
  | { stage: "jobRun"; datasetId: number; planId: number; plan: AnalysisPlan }
  | {
      stage: "result";
      modelId: number;
      template: string;
      metrics: ModelMetrics;
      summary: string;
      dataWarning: string | null;
    };

function railStageForState(state: AppState): DemoStageKey {
  if (state.stage === "upload") return "upload";
  if (state.stage === "dataset") return "dataset";
  if (state.stage === "plan") return "plan";
  if (state.stage === "jobRun") return "jobRun";
  return "result";
}

export default function App() {
  const [state, setState] = useState<AppState>({ stage: "upload" });

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <DemoFlowRail stage={railStageForState(state)} />

        {state.stage === "upload" && (
          <UploadPage
            onReady={({ ingest, demoScenario }) =>
              setState({
                stage: "dataset",
                datasetId: ingest.dataset_id,
                tableName: ingest.table_name,
                preferredTemplate: demoScenario === "uplift" ? "uplift" : "churn",
              })
            }
          />
        )}

        {state.stage === "dataset" && (
          <DatasetPage
            datasetId={state.datasetId}
            tableName={state.tableName}
            initialTemplate={state.preferredTemplate ?? "churn"}
            onStartAnalysis={() =>
              setState({
                stage: "plan",
                datasetId: state.datasetId,
                tableName: state.tableName,
                preferredTemplate: state.preferredTemplate,
                planUserGoal:
                  state.preferredTemplate === "uplift"
                    ? "uplift campaign CampaignSent Purchased customer_level"
                    : undefined,
              })
            }
          />
        )}

        {state.stage === "jobRun" && (
          <JobRunPage
            datasetId={state.datasetId}
            planId={state.planId}
            plan={state.plan}
            onComplete={(payload) =>
              setState({
                stage: "result",
                modelId: payload.modelId,
                template: payload.template,
                metrics: payload.metrics,
                summary: payload.summary,
                dataWarning: payload.dataWarning ?? null,
              })
            }
            onBackToStart={() => setState({ stage: "upload" })}
          />
        )}

        {state.stage === "plan" && (
          <PlanPage
            datasetId={state.datasetId}
            tableName={state.tableName}
            userGoal={state.planUserGoal}
            onApprove={(planId, plan) =>
              setState({ stage: "jobRun", datasetId: state.datasetId, planId, plan })
            }
            onBack={() =>
              setState({
                stage: "dataset",
                datasetId: state.datasetId,
                tableName: state.tableName,
                preferredTemplate: state.preferredTemplate,
              })
            }
          />
        )}

        {state.stage === "result" && (
          <ResultPage
            modelId={state.modelId}
            template={state.template}
            metrics={state.metrics}
            summary={state.summary}
            dataWarning={state.dataWarning}
            onNewAnalysis={() => setState({ stage: "upload" })}
          />
        )}
      </div>
    </div>
  );
}
