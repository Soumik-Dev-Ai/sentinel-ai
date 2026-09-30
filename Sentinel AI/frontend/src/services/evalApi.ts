const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function runEvaluation(customGoals?: any) {
  const options: RequestInit = { 
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ custom_goals: customGoals || null })
  };
  const res = await fetch(`${API_BASE}/api/evaluations/run`, options);
  if (!res.ok) {
    throw new Error(`Server returned ${res.status}`);
  }
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

export async function getRunHistory(limit = 50, offset = 0) {
  const res = await fetch(
    `${API_BASE}/api/history?limit=${limit}&offset=${offset}`,
    { cache: "no-store" }
  );
  return res.json();
}
