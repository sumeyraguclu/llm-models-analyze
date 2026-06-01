import { useEffect, useState } from "react";

import { fetchCurrentUser, logout } from "./api/client";
import { isLoggedIn } from "./auth/token";
import type { AnalysisPlan, ModelMetrics } from "./types";
import AuthPage from "./components/AuthPage";
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

function planUserGoalForTemplate(template?: string): string | undefined {
  if (template === "uplift") {
    return "recommended_template uplift. customer-level campaign data with treatment and outcome columns.";
  }
  if (template === "segmentasyon") {
    return "recommended_template segmentasyon. ecommerce transaction rows for customer segmentation.";
  }
  if (template === "churn") {
    return "recommended_template churn. ecommerce transaction rows for customer churn.";
  }
  return undefined;
}

function railStageForState(state: AppState): DemoStageKey {
  if (state.stage === "upload") return "upload";
  if (state.stage === "dataset") return "dataset";
  if (state.stage === "plan") return "plan";
  if (state.stage === "jobRun") return "jobRun";
  return "result";
}

export default function App() {
  const [state, setState] = useState<AppState>({ stage: "upload" });
  const [authenticated, setAuthenticated] = useState(() => isLoggedIn());
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!authenticated) {
      setUserEmail(null);
      return;
    }
    fetchCurrentUser()
      .then((u) => setUserEmail(u.email))
      .catch(() => {
        logout();
        setAuthenticated(false);
      });
  }, [authenticated]);

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-bg px-6 py-12">
        <AuthPage onAuthenticated={() => setAuthenticated(true)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-4 flex items-center justify-end gap-3 text-sm text-muted">
          {userEmail && <span>{userEmail}</span>}
          <button
            type="button"
            className="rounded-md border border-border px-3 py-1 text-fg hover:bg-surface"
            onClick={() => {
              logout();
              setAuthenticated(false);
              setState({ stage: "upload" });
            }}
          >
            Çıkış
          </button>
        </div>
        <DemoFlowRail stage={railStageForState(state)} />

        {state.stage === "upload" && (
          <UploadPage
            onReady={({ ingest, demoScenario }) =>
              setState({
                stage: "dataset",
                datasetId: ingest.dataset_id,
                tableName: ingest.table_name,
                preferredTemplate:
                  demoScenario === "uplift"
                    ? "uplift"
                    : demoScenario === "segmentasyon"
                      ? "segmentasyon"
                      : "churn",
              })
            }
          />
        )}

        {state.stage === "dataset" && (
          <DatasetPage
            key={`${state.datasetId}-${state.preferredTemplate ?? "churn"}`}
            datasetId={state.datasetId}
            tableName={state.tableName}
            initialTemplate={state.preferredTemplate ?? "churn"}
            onStartAnalysis={(selectedTemplate) =>
              setState({
                stage: "plan",
                datasetId: state.datasetId,
                tableName: state.tableName,
                preferredTemplate: selectedTemplate,
                planUserGoal: planUserGoalForTemplate(selectedTemplate),
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
            preferredTemplate={state.preferredTemplate}
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
