const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:9000";

export async function runEvaluation(customGoals?: any) {
  const options: RequestInit = { method: "POST" };
  if (customGoals) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify({ custom_goals: customGoals });
  }
  const res = await fetch(`${API_BASE}/api/evaluations/run`, options);
  return res.json();
}

export async function getEvaluationStatus() {
  const res = await fetch(`${API_BASE}/api/evaluations/status`, { cache: 'no-store' });
  return res.json();
}

export async function listEvaluations() {
  const res = await fetch(`${API_BASE}/api/evaluations`, { cache: 'no-store' });
  return res.json();
}

export async function getEvaluationDetails(runName: string) {
  const res = await fetch(`${API_BASE}/api/evaluations/${runName}`, { cache: 'no-store' });
  return res.json();
}
