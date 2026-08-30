import React, { useEffect, useState, useRef } from "react";
import { runEvaluation, getEvaluationStatus, listEvaluations, getEvaluationDetails } from "../services/evalApi";

export const EvaluationLab: React.FC<{ onExit?: () => void }> = ({ onExit }) => {
  const [reports, setReports] = useState<any[]>([]);
  const [selectedReport, setSelectedReport] = useState<any | null>(null);
  const [status, setStatus] = useState<any>({ running: false, progress: 0, total: 0 });
  const [customText, setCustomText] = useState("");
  const [inputType, setInputType] = useState<"default" | "text" | "file">("default");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const prevRunningRef = useRef(false);
  const [finishedRun, setFinishedRun] = useState<string | null>(null);

  useEffect(() => {
    fetchReports();
    const interval = setInterval(checkStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchReports = async () => {
    try {
      const data = await listEvaluations();
      setReports(data);
    } catch (e) {
      console.error(e);
    }
  };

  const checkStatus = async () => {
    try {
      const data = await getEvaluationStatus();
      setStatus(data);
      if (!data.running && prevRunningRef.current) {
        // Just finished
        if (data.last_result?.error) {
           alert(`Evaluation crashed on the backend: ${data.last_result.error}`);
        } else {
           const updatedReports = await listEvaluations();
           setReports(updatedReports);
           if (updatedReports.length > 0) {
             setFinishedRun(updatedReports[0].run_name);
           }
        }
      }
      prevRunningRef.current = data.running;
    } catch (e) {
      console.error(e);
    }
  };

  const handleRun = async () => {
    try {
      let customGoals = null;
      if (inputType === "file" && fileInputRef.current?.files?.length) {
        const file = fileInputRef.current.files[0];
        const text = await file.text();
        customGoals = JSON.parse(text);
      } else if (inputType === "text" && customText.trim()) {
        // Parse textarea lines into goals
        const lines = customText.split('\n').filter(l => l.trim().length > 0);
        customGoals = lines.map((line, idx) => ({
          id: `custom_goal_${idx + 1}`,
          spec: line.trim(),
          input: ""
        }));
      }
      
      await runEvaluation(customGoals);
      setFinishedRun(null);
      checkStatus();
      setCustomText("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      alert("Error starting evaluation. Make sure your JSON file is valid, or your text list is formatted correctly.");
      console.error(e);
    }
  };

  const handleSelectReport = async (runName: string) => {
    try {
      const details = await getEvaluationDetails(runName);
      
      setSelectedReport(details);
      setFinishedRun(null);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="eval-lab">
      <div className="eval-header">
        <h2>Evaluation Lab</h2>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '12px', width: '400px' }}>
          {onExit && (
            <button className="back-3d-btn" onClick={onExit}>
              &larr; Exit Lab
            </button>
          )}
          {status.running && (
            <div className="progress-bar" style={{ width: '100%' }}>
              <div className="progress-fill" style={{ width: `${(status.progress / status.total) * 100}%` }}></div>
              <span>Running: {status.current_goal} ({status.progress}/{status.total})</span>
            </div>
          )}
        </div>
      </div>

      <div className="eval-content">


        <div className="eval-main">
          {selectedReport ? (
            <div className="report-details">
              <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px' }}>
                <button 
                  onClick={() => { setSelectedReport(null); setFinishedRun(null); }}
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: 'white', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer' }}
                >
                  &larr; Back to Evaluation Lab
                </button>
                <h3 style={{ margin: 0 }}>Evaluation Report: {selectedReport.run_name}</h3>
              </div>
              
              <div className="metrics-grid">
                <div className="metric-card">
                  <h4>Self-Correction Enabled (Agent)</h4>
                  <p>Completion Rate: {(selectedReport.metrics_with_self_correction.completion_rate * 100).toFixed(0)}%</p>
                  <p>Avg Steps: {selectedReport.metrics_with_self_correction.avg_steps.toFixed(1)}</p>
                  <p>Self Corrections: {selectedReport.metrics_with_self_correction.total_self_corrections}</p>
                </div>
                <div className="metric-card baseline">
                  <h4>No Self-Correction (Baseline)</h4>
                  <p>Completion Rate: {(selectedReport.metrics_baseline.completion_rate * 100).toFixed(0)}%</p>
                  <p>Avg Steps: {selectedReport.metrics_baseline.avg_steps.toFixed(1)}</p>
                  <p>Self Corrections: {selectedReport.metrics_baseline.total_self_corrections}</p>
                </div>
              </div>

              <h4>Detailed Runs</h4>
              <div className="runs-list">
                {selectedReport.detailed_runs?.map((run: any, i: number) => (
                  <div key={i} className={`run-card ${run.success ? 'success' : 'fail'}`}>
                    <h5>{run.goal_id} - {run.self_correction_enabled ? 'Agent (SC)' : 'Baseline'}</h5>
                    <p><strong>Goal:</strong> {run.spec}</p>
                    <p><strong>Status:</strong> {run.success ? '✅ Success' : '❌ Failed'}</p>
                    <p><strong>Steps:</strong> {run.steps} | <strong>Corrections:</strong> {run.self_corrections}</p>
                    
                    <details>
                      <summary>View Structured ReAct Trace</summary>
                      <div className="react-trace">
                        {run.memory_dump?.steps && run.memory_dump.steps.length > 0 ? (
                          run.memory_dump.steps.map((step: any, idx: number) => (
                            <div key={idx} className="trace-step">
                              <div className="trace-thought"><strong>Think:</strong> {step.thought}</div>
                              <div className="trace-action"><strong>Act:</strong> {step.tool}({JSON.stringify(step.args)})</div>
                              <div className="trace-result"><strong>Observe:</strong> {JSON.stringify(step.result).substring(0, 200)}...</div>
                              {step.correction_trigger && (
                                <div className="trace-correction"><strong>Correction Triggered:</strong> {step.correction_trigger}</div>
                              )}
                            </div>
                          ))
                        ) : (
                          <div style={{ padding: '10px', color: 'rgba(255,255,255,0.5)', fontStyle: 'italic', textAlign: 'center' }}>
                            {run.memory_dump?.final_output ? (
                              <span style={{ color: '#ef4444' }}><strong>Error:</strong> {run.memory_dump.final_output}</span>
                            ) : (
                              "No ReAct trace available for this run."
                            )}
                          </div>
                        )}
                      </div>
                    </details>
                  </div>
                ))}
              </div>
            </div>
          ) : finishedRun ? (
            <div className="eval-setup" style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '600px', margin: '0 auto', marginTop: '100px', textAlign: 'center' }}>
              <h3 style={{ fontSize: '1.5rem', color: '#22c55e', margin: 0 }}>Evaluation test is completed</h3>
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
                <button 
                  onClick={() => handleSelectReport(finishedRun)} 
                  style={{ background: '#22c55e', color: 'black', border: 'none', padding: '12px 24px', borderRadius: '6px', cursor: 'pointer', fontSize: '1.1rem', fontWeight: 'bold' }}
                >
                  Show Result
                </button>
              </div>
            </div>
          ) : (
            <div className="eval-setup" style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '600px', margin: '0 auto', marginTop: '50px' }}>
              <h3 style={{ fontSize: '1.5rem', color: '#22c55e', margin: 0 }}>Start a New Evaluation</h3>
              
              <div style={{ display: 'flex', gap: '10px', paddingBottom: '10px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <button 
                  onClick={() => setInputType("default")} 
                  style={{ background: inputType === "default" ? 'rgba(34, 197, 94, 0.2)' : 'transparent', color: inputType === "default" ? '#22c55e' : 'white', border: '1px solid', borderColor: inputType === "default" ? '#22c55e' : 'rgba(255,255,255,0.2)', padding: '8px 12px', borderRadius: '6px', cursor: 'pointer' }}
                >
                  Default Suite
                </button>
                <button 
                  onClick={() => setInputType("text")} 
                  style={{ background: inputType === "text" ? 'rgba(34, 197, 94, 0.2)' : 'transparent', color: inputType === "text" ? '#22c55e' : 'white', border: '1px solid', borderColor: inputType === "text" ? '#22c55e' : 'rgba(255,255,255,0.2)', padding: '8px 12px', borderRadius: '6px', cursor: 'pointer' }}
                >
                  Paste Text
                </button>
                <button 
                  onClick={() => setInputType("file")} 
                  style={{ background: inputType === "file" ? 'rgba(34, 197, 94, 0.2)' : 'transparent', color: inputType === "file" ? '#22c55e' : 'white', border: '1px solid', borderColor: inputType === "file" ? '#22c55e' : 'rgba(255,255,255,0.2)', padding: '8px 12px', borderRadius: '6px', cursor: 'pointer' }}
                >
                  Upload JSON
                </button>
              </div>

              <div style={{ minHeight: '120px' }}>
                {inputType === "default" && (
                  <p style={{ color: 'rgba(255,255,255,0.7)', margin: 0, lineHeight: '1.6' }}>
                    This will run the predefined benchmark suite containing 10 diverse assignment tasks (including network failures, syntax errors, and algorithm implementation).
                  </p>
                )}
                
                {inputType === "text" && (
                  <textarea 
                    placeholder="Paste a list of goals here (one per line) to evaluate..."
                    value={customText}
                    onChange={e => setCustomText(e.target.value)}
                    style={{ width: '100%', minHeight: '120px', padding: '15px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', color: 'white', border: '1px solid rgba(255,255,255,0.2)', resize: 'vertical' }}
                  />
                )}
                
                {inputType === "file" && (
                  <div style={{ background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.2)', textAlign: 'center' }}>
                    <input type="file" accept=".json" ref={fileInputRef} style={{ fontSize: '1rem' }} title="Upload custom goals.json" />
                  </div>
                )}
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: '10px' }}>
                {status.running ? (
                  <span style={{ color: '#22c55e', fontWeight: 'bold' }}>Running...</span>
                ) : (
                  <button onClick={handleRun} className="run-eval-btn">Run Suite</button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
