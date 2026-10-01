import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { mockConsultations } from './mockData'
import type { Consultation, ConsultationListResponse, FeedbackIssue, FeedbackRecord, FeedbackRequest, FeedbackSummary, KnowledgeSource, RetrievalCaseResult, RetrievalEvaluationComparison, RetrievalTrace, RiskLevel, WorkflowAction } from './types'

const riskLabels: Record<RiskLevel, string> = {
  Critical: '긴급 검토', High: '관리자 검토', Medium: '추가 확인', Low: '일반 검토', Unknown: '판단 보류',
}

const feedbackIssueLabels: Record<FeedbackIssue, string> = {
  wrong_evidence: '잘못된 근거',
  missing_evidence: '근거 부족',
  draft_quality: '초안 품질',
  other: '기타',
}

const feedbackIssueOptions: FeedbackIssue[] = ['wrong_evidence', 'missing_evidence', 'draft_quality']

function App() {
  const [consultations, setConsultations] = useState<Consultation[]>(mockConsultations)
  const [selected, setSelected] = useState<Consultation | null>(null)
  const [query, setQuery] = useState('')
  const [risk, setRisk] = useState<RiskLevel | 'All'>('All')
  const [apiState, setApiState] = useState<'loading' | 'connected' | 'mock'>('loading')
  const [view, setView] = useState<'consultations' | 'evaluation' | 'knowledge'>('consultations')

  useEffect(() => {
    fetch('/api/consultations')
      .then((response) => {
        if (!response.ok) throw new Error('API unavailable')
        return response.json() as Promise<ConsultationListResponse>
      })
      .then((data) => { setConsultations(data.items); setApiState('connected') })
      .catch(() => setApiState('mock'))
  }, [])

  const filtered = useMemo(() => consultations.filter((item) => {
    const matchesQuery = `${item.id} ${item.customer} ${item.summary}`.toLowerCase().includes(query.toLowerCase())
    return matchesQuery && (risk === 'All' || item.risk === risk)
  }), [consultations, query, risk])

  const highRiskCount = consultations.filter((item) => item.risk === 'High' || item.risk === 'Critical').length

  const handleAction = async (consultationId: string, action: WorkflowAction, confirmedChecks: string[]) => {
    if (apiState !== 'connected') throw new Error('API 연결 상태에서만 상담을 처리할 수 있습니다.')
    const response = await fetch(`/api/consultations/${consultationId}/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        actor: '박소영 상담사',
        note: '상담사 워크스페이스에서 처리',
        confirmed_checks: confirmedChecks,
      }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '상담 처리에 실패했습니다.')
    const updated = payload as Consultation
    setConsultations((items) => items.map((item) => item.id === updated.id ? updated : item))
    setSelected(updated)
    return updated
  }

  const handleFeedback = async (consultationId: string, feedback: FeedbackRequest) => {
    if (apiState !== 'connected') throw new Error('API 연결 상태에서만 피드백을 저장할 수 있습니다.')
    const response = await fetch(`/api/consultations/${consultationId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(feedback),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '피드백 저장에 실패했습니다.')
    return payload as FeedbackRecord
  }

  const handleGenerateDraft = async (consultationId: string) => {
    if (apiState !== 'connected') throw new Error('API 연결 상태에서만 AI 초안을 생성할 수 있습니다.')
    const response = await fetch(`/api/consultations/${consultationId}/draft/llm`, {
      method: 'POST',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'AI 초안 생성에 실패했습니다.')
    const updated = payload as Consultation
    setConsultations((items) => items.map((item) => item.id === updated.id ? updated : item))
    setSelected(updated)
    return updated
  }

  const handleAnalyze = async (consultationId: string) => {
    if (apiState !== 'connected') throw new Error('API 연결 상태에서만 AI 분석을 실행할 수 있습니다.')
    const response = await fetch(`/api/consultations/${consultationId}/analysis/llm`, {
      method: 'POST',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'AI 상담 분석에 실패했습니다.')
    const updated = payload as Consultation
    setConsultations((items) => items.map((item) => item.id === updated.id ? updated : item))
    setSelected(updated)
    return updated
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">BANCUE <span>상담 Copilot</span></div>
        <div className={`environment ${apiState}`}>{apiState === 'connected' ? 'API 연결' : apiState === 'mock' ? 'Synthetic' : '연결 중'}</div>
        <div className="user">박소영 상담사</div>
      </header>
      <aside className="sidebar">
        <nav>
          <button className={view === 'consultations' ? 'active' : ''} onClick={() => { setView('consultations'); setSelected(null) }}>상담 목록</button>
          <button>이관 큐</button>
          <button className={view === 'evaluation' ? 'active' : ''} onClick={() => { setView('evaluation'); setSelected(null) }}>품질 관리 <small>v3</small></button>
          <button className={view === 'knowledge' ? 'active' : ''} onClick={() => { setView('knowledge'); setSelected(null) }}>지식 관리 <small>v1</small></button>
        </nav>
        <p className="security-note">고객 정보와 피드백 메모는 마스킹됩니다.<br />상담 처리 이력은 로컬 SQLite에 저장됩니다.</p>
      </aside>
      <main className="main">
        {view === 'evaluation' ? (
          <EvaluationDashboard />
        ) : view === 'knowledge' ? (
          <KnowledgeDashboard />
        ) : selected ? (
          <Workspace consultation={selected} onBack={() => setSelected(null)} onAction={handleAction} onFeedback={handleFeedback} onGenerateDraft={handleGenerateDraft} onAnalyze={handleAnalyze} />
        ) : (
          <>
            <section className="page-heading">
              <div><p className="eyebrow">COUNSELOR WORKSPACE</p><h1>상담 목록</h1><p>위험도와 대기시간을 기준으로 처리할 상담을 선택하세요.</p></div>
              <button className="secondary">새로고침</button>
            </section>
            <section className="summary-grid">
              <Metric label="대기 상담" value={String(consultations.length)} />
              <Metric label="High 이상" value={String(highRiskCount)} tone="danger" />
              <Metric label="평균 대기" value="09:49" />
              <Metric label="금일 완료" value="126" />
            </section>
            <section className="list-card">
              <div className="filters">
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="고객명·상담번호·문의 내용 검색" />
                <select value={risk} onChange={(event) => setRisk(event.target.value as RiskLevel | 'All')}>
                  <option value="All">전체 위험도</option>
                  {Object.keys(riskLabels).map((level) => <option key={level}>{level}</option>)}
                </select>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>위험도</th><th>상담번호</th><th>고객</th><th>문의 요약</th><th>대기시간</th><th>상태</th></tr></thead>
                  <tbody>{filtered.map((item) => (
                    <tr key={item.id} onClick={() => setSelected(item)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && setSelected(item)}>
                      <td><RiskBadge risk={item.risk} /></td><td className="mono">{item.id}</td><td>{item.customer}</td><td><strong>{item.summary}</strong><span>{item.topic}</span></td><td className="mono">{item.waiting_time}</td><td>{item.status}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function Workspace({ consultation, onBack, onAction, onFeedback, onGenerateDraft, onAnalyze }: { consultation: Consultation; onBack: () => void; onAction: (id: string, action: WorkflowAction, checks: string[]) => Promise<Consultation>; onFeedback: (id: string, feedback: FeedbackRequest) => Promise<FeedbackRecord>; onGenerateDraft: (id: string) => Promise<Consultation>; onAnalyze: (id: string) => Promise<Consultation> }) {
  const restricted = consultation.risk === 'Critical' || consultation.risk === 'High'
  const completed = consultation.status === 'Completed'
  const [checkedItems, setCheckedItems] = useState<string[]>([])
  const [actionState, setActionState] = useState<'idle' | 'saving'>('idle')
  const [actionMessage, setActionMessage] = useState('')
  const [detailTab, setDetailTab] = useState<'review' | 'feedback'>('review')
  const [intentScore, setIntentScore] = useState(5)
  const [draftScore, setDraftScore] = useState(5)
  const [feedbackIssue, setFeedbackIssue] = useState<FeedbackIssue>('wrong_evidence')
  const [feedbackNote, setFeedbackNote] = useState('')
  const [feedbackState, setFeedbackState] = useState<'idle' | 'saving'>('idle')
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [llmState, setLlmState] = useState<'idle' | 'generating'>('idle')
  const [llmMessage, setLlmMessage] = useState('')
  const [analysisState, setAnalysisState] = useState<'idle' | 'analyzing'>('idle')
  const [analysisMessage, setAnalysisMessage] = useState('')
  const allChecksDone = consultation.required_checks.every((item) => checkedItems.includes(item))
  const qualityPassed = consultation.draft_quality?.status === 'Passed'

  useEffect(() => {
    setCheckedItems([])
    setActionMessage('')
    setDetailTab('review')
    setIntentScore(5)
    setDraftScore(5)
    setFeedbackIssue('wrong_evidence')
    setFeedbackNote('')
    setFeedbackMessage('')
    setLlmState('idle')
    setLlmMessage('')
    setAnalysisState('idle')
    setAnalysisMessage('')
  }, [consultation.id])

  const toggleCheck = (item: string) => {
    setCheckedItems((checked) => checked.includes(item) ? checked.filter((value) => value !== item) : [...checked, item])
  }

  const runAction = async (action: WorkflowAction) => {
    setActionState('saving')
    setActionMessage('')
    try {
      await onAction(consultation.id, action, checkedItems)
      const labels: Record<WorkflowAction, string> = { approve: '승인', reject: '반려', escalate: '관리자 이관' }
      setActionMessage(`${labels[action]} 처리가 완료되었습니다.`)
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : '상담 처리에 실패했습니다.')
    } finally {
      setActionState('idle')
    }
  }

  const submitFeedback = async () => {
    setFeedbackState('saving')
    setFeedbackMessage('')
    try {
      const saved = await onFeedback(consultation.id, {
        intent_score: intentScore,
        draft_score: draftScore,
        issue_types: Math.min(intentScore, draftScore) <= 3 ? [feedbackIssue] : [],
        note: feedbackNote.trim() || null,
        actor: '박소영 상담사',
      })
      setFeedbackMessage(saved.pii_masked ? `피드백을 저장했고 ${saved.pii_types.join(' · ')} 정보를 마스킹했습니다.` : '피드백을 품질 관리 기록에 저장했습니다.')
      setFeedbackNote('')
    } catch (error) {
      setFeedbackMessage(error instanceof Error ? error.message : '피드백 저장에 실패했습니다.')
    } finally {
      setFeedbackState('idle')
    }
  }

  const generateAiDraft = async () => {
    setLlmState('generating')
    setLlmMessage('')
    try {
      const updated = await onGenerateDraft(consultation.id)
      setLlmMessage(updated.draft_fallback_reason ? 'Gemini 호출 대신 안전한 템플릿 초안을 사용했습니다.' : 'Gemini 근거 기반 초안을 생성했습니다.')
    } catch (error) {
      setLlmMessage(error instanceof Error ? error.message : 'AI 초안 생성에 실패했습니다.')
    } finally {
      setLlmState('idle')
    }
  }

  const runAiAnalysis = async () => {
    setAnalysisState('analyzing')
    setAnalysisMessage('')
    try {
      const updated = await onAnalyze(consultation.id)
      setAnalysisMessage(updated.analysis_engine === 'gemini-structured-triage-v1' ? 'Gemini가 상담 의도·위험도·필수 확인 항목을 구조화했습니다.' : 'Gemini 분석 대신 기존 규칙 결과를 유지했습니다.')
    } catch (error) {
      setAnalysisMessage(error instanceof Error ? error.message : 'AI 상담 분석에 실패했습니다.')
    } finally {
      setAnalysisState('idle')
    }
  }

  return <>
    <section className="workspace-heading">
      <button className="back" onClick={onBack}>← 상담 목록</button>
      <div><span className="mono">{consultation.id}</span><h1>{consultation.customer} · {consultation.summary}</h1></div>
      <RiskBadge risk={consultation.risk} />
    </section>
    <section className="workspace-grid">
      <article className="panel conversation-panel"><PanelTitle title="상담 대화" subtitle="마스킹된 고객 문의" /><div className={`privacy-status ${consultation.pii_masked ? 'masked' : ''}`}><b>{consultation.pii_masked ? '개인정보 마스킹 완료' : '개인정보 감지 없음'}</b><span>{consultation.pii_masked ? consultation.pii_types.join(' · ') : '표시할 개인정보 유형이 없습니다.'}</span></div><div className="message customer"><b>고객</b><p>{consultation.question}</p></div><div className="message agent"><b>상담사</b><p>문의 내용을 확인하고 있습니다. 필요한 정보를 확인한 뒤 안내드리겠습니다.</p></div><textarea placeholder="고객에게 보낼 메시지를 입력하세요" /></article>
      <article className="panel analysis-panel">
        <PanelTitle title="AI 분석" subtitle="핵심 판단과 필수 확인" />
        <div className="analysis-summary"><Info label="의도" value={consultation.intent} /><Info label="위험도" value={`${consultation.risk} · ${riskLabels[consultation.risk]}`} /><Info label="처리 상태" value={consultation.status} /></div>
        <div className="analysis-controls"><button className="secondary" disabled={completed || analysisState === 'analyzing'} onClick={runAiAnalysis}>{analysisState === 'analyzing' ? 'Gemini 분석 중…' : 'Gemini로 상담 재분석'}</button><span>{consultation.analysis_engine ?? 'rules-v1'}{consultation.analysis_model ? ` · ${consultation.analysis_model}` : ''}{consultation.analysis_latency_ms != null ? ` · ${consultation.analysis_latency_ms}ms` : ''}</span></div>
        {analysisMessage ? <div className="action-message">{analysisMessage}</div> : null}
        <div className="reason-list"><b>판정 이유</b>{(consultation.analysis_rationale?.length ? consultation.analysis_rationale : consultation.risk_reasons).map((reason) => <p key={reason}>• {reason}</p>)}<span>{consultation.analysis_prompt_version ?? 'triage-v1'}{consultation.analysis_confidence != null ? ` · 신뢰도 ${Math.round(consultation.analysis_confidence * 100)}%` : ''} · {consultation.rule_ids.join(' · ')}</span></div>
        <div className="check-list"><b>필수 확인 항목</b>{consultation.required_checks.map((item) => <label key={item}><input type="checkbox" checked={checkedItems.includes(item)} disabled={completed} onChange={() => toggleCheck(item)} /> {item}</label>)}</div>
        {consultation.restriction_reason && <div className="warning"><b>자동 답변 제한</b><p>{consultation.restriction_reason}</p></div>}
        {consultation.retrieval_trace ? <details className="analysis-details"><summary>검색 판단 상세</summary><TraceSummary trace={consultation.retrieval_trace} compact /></details> : null}
        {consultation.action_history.length ? <details className="analysis-details"><summary>처리 이력 {consultation.action_history.length}건</summary><div className="action-history">{consultation.action_history.map((record) => <div key={`${record.created_at}-${record.action}`}><strong>{record.action === 'approve' ? '승인' : record.action === 'reject' ? '반려' : '관리자 이관'}</strong><span>{record.actor} · {new Date(record.created_at).toLocaleString('ko-KR')}</span></div>)}</div></details> : null}
      </article>
      <article className="panel evidence-panel">
        <PanelTitle title="근거 및 답변 초안" subtitle="공식 공개자료 요약 · 사람 검토 필수" />
        <div className="detail-tabs"><button className={detailTab === 'review' ? 'active' : ''} onClick={() => setDetailTab('review')}>답변 검토</button><button className={detailTab === 'feedback' ? 'active' : ''} onClick={() => setDetailTab('feedback')}>품질 피드백</button></div>
        {detailTab === 'review' ? <>
          {consultation.evidence.length ? <details className="evidence-details"><summary>근거 문서 {consultation.evidence.length}건 · {consultation.evidence.map((item) => item.document_id).join(' · ')}</summary>{consultation.evidence.map((item) => (
            <div className="evidence" key={item.document_id || item.title}>
              <div className="evidence-heading"><strong>{item.title}</strong>{item.score != null && <b>{item.score}점</b>}</div>
              <p>{item.section}</p>
              <span>{item.source_type === 'official-public' ? `공식 공개자료 · ${item.source_organization}` : '합성 테스트 문서'}{item.effective_date ? ` · 기준일 ${item.effective_date}` : ''}{item.document_id ? ` · ${item.document_id}` : ''}</span>
              {item.matched_terms?.length ? <small>일치 키워드: {item.matched_terms.join(' · ')}</small> : null}
              {item.query_expansions?.length ? <small className="query-expansion">질의 확장: {item.query_expansions.join(' · ')} ({item.query_rule_ids?.join(' · ')})</small> : null}
              {item.verified_at ? <small>출처 확인일: {item.verified_at} · {item.review_status === 'Verified' ? '검증 완료' : '재검토 필요'}</small> : null}
              {item.source_url ? <a className="source-link" href={item.source_url} target="_blank" rel="noreferrer">공식 원문 열기 ↗</a> : null}
            </div>
          ))}</details> : <div className="warning"><b>연결된 검증 근거 없음</b><p>{consultation.retrieval_trace?.reason ?? '답변 초안을 생성하지 않고 추가 정보 요청 또는 이관이 필요합니다.'}</p></div>}
          <div className={`draft-status ${consultation.draft_generated ? 'ready' : 'blocked'}`}><b>{consultation.draft_generated ? '초안 생성 완료' : '초안 생성 차단'}</b><p>{consultation.draft_notice}</p>{consultation.draft_source_ids.length ? <span>사용 근거: {consultation.draft_source_ids.join(' · ')}</span> : null}</div>
          <div className="llm-controls"><button className="primary" disabled={!consultation.evidence.length || completed || llmState === 'generating'} onClick={generateAiDraft}>{llmState === 'generating' ? 'Gemini 생성 중…' : 'Gemini로 근거 초안 생성'}</button>{consultation.draft_engine ? <span>{consultation.draft_engine}{consultation.draft_model ? ` · ${consultation.draft_model}` : ''}{consultation.draft_latency_ms != null ? ` · ${consultation.draft_latency_ms}ms` : ''}</span> : null}</div>
          {llmMessage ? <div className="action-message">{llmMessage}</div> : null}
          {consultation.draft_quality ? <details className={`quality-guardrail ${qualityPassed ? 'passed' : 'review'}`} open={!qualityPassed}><summary><span>답변 품질 가드레일</span><b>{consultation.draft_quality.score}점 · {qualityPassed ? '통과' : '검토 필요'}</b></summary><div className="quality-checks">{consultation.draft_quality.checks.map((check) => <div key={check.check_id} className={check.passed ? 'pass' : 'fail'}><b>{check.passed ? '✓' : '!'} {check.label}</b><span>{check.detail}</span></div>)}</div><small>{consultation.draft_prompt_version ?? 'grounded-draft-v2'} · {consultation.draft_quality.evaluator}</small></details> : null}
          <textarea className="draft" value={consultation.draft ?? ''} readOnly placeholder="유효한 근거가 연결되면 초안이 생성됩니다." />
          {actionMessage ? <div className="action-message">{actionMessage}</div> : null}
          <div className="action-bar"><button className="secondary" disabled={completed || actionState === 'saving'} onClick={() => runAction('reject')}>반려</button>{restricted ? <button className="primary danger" disabled={completed || actionState === 'saving'} onClick={() => runAction('escalate')}>관리자 이관</button> : <><button className="secondary" disabled={completed || actionState === 'saving'} onClick={() => runAction('escalate')}>관리자 이관</button><button className="primary" disabled={completed || actionState === 'saving' || !consultation.draft_generated || !allChecksDone || !qualityPassed} onClick={() => runAction('approve')}>승인</button></>}</div>
        </> : <div className="feedback-box score-feedback">
          <div><b>상담사 품질 피드백</b><span>항목별로 평가하면 어떤 기능을 개선해야 하는지 구분할 수 있습니다.</span></div>
          <ScoreSelector label="의도 파악이 정확한가요?" value={intentScore} onChange={setIntentScore} />
          <ScoreSelector label="답변 초안이 정확한가요?" value={draftScore} onChange={setDraftScore} />
          {Math.min(intentScore, draftScore) <= 3 ? <label className="feedback-issue"><span>개선 사유</span><select value={feedbackIssue} onChange={(event) => setFeedbackIssue(event.target.value as FeedbackIssue)}>{feedbackIssueOptions.map((value) => <option key={value} value={value}>{feedbackIssueLabels[value]}</option>)}</select></label> : <p className="score-guide">두 항목 모두 4점 이상이면 개선 사유를 선택하지 않아도 됩니다.</p>}
          <label className="feedback-note"><span>비고 <small>선택</small></span><textarea value={feedbackNote} maxLength={500} onChange={(event) => setFeedbackNote(event.target.value)} placeholder="고객 개인정보는 입력하지 마세요." /></label>
          <button className="primary feedback-submit" disabled={feedbackState === 'saving'} onClick={submitFeedback}>{feedbackState === 'saving' ? '저장 중' : '피드백 저장'}</button>
          {feedbackMessage ? <p className="feedback-message">{feedbackMessage}</p> : null}
        </div>}
      </article>
    </section>
  </>
}

function EvaluationDashboard() {
  const [comparison, setComparison] = useState<RetrievalEvaluationComparison | null>(null)
  const [feedbackSummary, setFeedbackSummary] = useState<FeedbackSummary | null>(null)
  const [error, setError] = useState('')
  const [feedbackError, setFeedbackError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setComparison(null)
    setFeedbackSummary(null)
    setError('')
    setFeedbackError('')
    fetch('/api/evaluation/retrieval/comparison')
      .then((response) => {
        if (!response.ok) throw new Error('평가 API를 불러오지 못했습니다.')
        return response.json() as Promise<RetrievalEvaluationComparison>
      })
      .then(setComparison)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '평가에 실패했습니다.'))
    fetch('/api/feedback/summary')
      .then((response) => {
        if (!response.ok) throw new Error('상담사 피드백을 불러오지 못했습니다.')
        return response.json() as Promise<FeedbackSummary>
      })
      .then(setFeedbackSummary)
      .catch((reason) => setFeedbackError(reason instanceof Error ? reason.message : '피드백 집계에 실패했습니다.'))
  }, [refreshKey])

  const percentage = (value: number) => `${Math.round(value * 100)}%`
  const report = comparison?.improved
  const resultLabel = (result: RetrievalCaseResult | undefined) => {
    if (!result) return '-'
    if (result.expected_no_answer) return result.retrieved_document_ids.length ? '오검색' : '무응답'
    return result.hit_rank ?? '실패'
  }

  return <>
    <section className="page-heading">
      <div><p className="eyebrow">RETRIEVAL EVALUATION</p><h1>RAG 검색 품질 관리</h1><p>정답셋과 검색 결과를 비교해 키워드 검색의 성능과 실패 원인을 확인합니다.</p></div>
      <button className="secondary" onClick={() => setRefreshKey((value) => value + 1)}>재평가</button>
    </section>
    {!comparison || !report ? <section className="list-card evaluation-loading">{error || '검색 평가를 실행하고 있습니다.'}</section> : <>
      <section className="summary-grid">
        <Metric label="기존 전체 정확도" value={percentage(comparison.baseline.overall_accuracy)} />
        <Metric label="개선 전체 정확도" value={percentage(report.overall_accuracy)} tone="good" />
        <Metric label="무응답 정확도" value={percentage(report.no_answer_accuracy)} tone="good" />
        <Metric label="오검색" value={`${report.false_positive_cases}건`} tone="good" />
      </section>
      <div className="quality-note"><b>기존 {comparison.baseline.passed_cases}건 → 개선 {report.passed_cases}건 성공</b><span>정답 문서가 있는 질문 {report.positive_cases}개와 검색하면 안 되는 질문 {report.no_answer_cases}개를 함께 평가합니다.</span></div>
      <FeedbackQuality summary={feedbackSummary} error={feedbackError} />
      <section className="list-card">
        <div className="table-wrap"><table>
          <thead><tr><th>케이스</th><th>평가 질문</th><th>질의 확장</th><th>정답 문서</th><th>개선 검색 결과</th><th>기존 순위</th><th>개선 순위</th><th>판정</th></tr></thead>
          <tbody>{report.results.map((result) => {
            const baseline = comparison.baseline.results.find((item) => item.case_id === result.case_id)
            return <tr key={result.case_id} className={result.outcome === 'correct-abstention' ? 'abstained-row' : result.added_terms.length ? 'expanded-row' : result.passed ? '' : 'failed-row'}>
              <td className="mono">{result.case_id}</td>
              <td><strong>{result.query}</strong><span>{result.description}</span></td>
              <td>{result.expected_no_answer ? <span className="no-expansion">범위 밖 질문</span> : result.added_terms.length ? <><div className="expansion-terms">{result.added_terms.map((term) => <span key={term}>{term}</span>)}</div><small className="rule-id">{result.query_rule_ids.join(' · ')}</small></> : <span className="no-expansion">직접 표현</span>}</td>
              <td className="mono">{result.expected_no_answer ? '검색 결과 없음' : result.expected_document_ids.join(' · ')}</td>
              <td className="mono">{result.retrieved_document_ids.length ? result.retrieved_document_ids.join(' → ') : '신뢰도 부족 · 검색 차단'}</td>
              <td>{resultLabel(baseline)}</td>
              <td>{resultLabel(result)}</td>
              <td><span className={`result-chip ${result.passed ? 'pass' : 'fail'}`}>{result.outcome === 'correct-abstention' ? '무응답 성공' : result.passed ? '검색 성공' : '실패'}</span></td>
            </tr>
          })}</tbody>
        </table></div>
      </section>
    </>}
  </>
}

function FeedbackQuality({ summary, error }: { summary: FeedbackSummary | null; error: string }) {
  if (!summary) return <section className="feedback-quality-card feedback-loading">{error || '상담사 피드백을 집계하고 있습니다.'}</section>
  return <section className="feedback-quality-card">
    <div className="feedback-quality-heading"><div><p className="eyebrow">HUMAN FEEDBACK</p><h2>상담사 피드백 현황</h2></div><span>메모는 개인정보 마스킹 후 SQLite에 저장됩니다.</span></div>
    <div className="feedback-metrics"><Metric label="점수형 피드백" value={`${summary.scored_feedback}건`} /><Metric label="의도 파악 평균" value={summary.scored_feedback ? `${summary.average_intent_score} / 5` : '-'} tone="good" /><Metric label="답변 초안 평균" value={summary.scored_feedback ? `${summary.average_draft_score} / 5` : '-'} tone="good" /><Metric label="개선 필요" value={`${summary.needs_improvement}건`} /></div>
    {summary.total === 0 ? <p className="feedback-empty">상담 상세에서 첫 번째 품질 피드백을 남기면 여기에 집계됩니다.</p> : <>
      <div className="feedback-issues"><b>개선 유형</b>{Object.entries(summary.issue_counts).length ? Object.entries(summary.issue_counts).map(([issue, count]) => <span key={issue}>{feedbackIssueLabels[issue as FeedbackIssue] ?? issue} {count}건</span>) : <span>등록된 개선 유형 없음</span>}</div>
      <div className="feedback-recent"><b>최근 기록</b>{summary.recent.slice(0, 5).map((item) => <div key={item.id}><strong>{item.consultation_id}</strong><span>{item.intent_score ? `의도 ${item.intent_score} · 초안 ${item.draft_score}` : '이전 방식 평가'} · {item.issue_types.map((issue) => feedbackIssueLabels[issue]).join(' · ') || '개선 사유 없음'} · {item.actor}</span>{item.note ? <p>{item.note}</p> : null}</div>)}</div>
    </>}
  </section>
}

function KnowledgeDashboard() {
  const [sources, setSources] = useState<KnowledgeSource[] | null>(null)
  const [error, setError] = useState('')
  const [explainQuery, setExplainQuery] = useState('해외송금 회사에 취업하려면 어떤 자격증이 필요한가요?')
  const [trace, setTrace] = useState<RetrievalTrace | null>(null)
  const [traceState, setTraceState] = useState<'idle' | 'loading' | 'error'>('idle')

  useEffect(() => {
    fetch('/api/knowledge/sources')
      .then((response) => {
        if (!response.ok) throw new Error('지식 출처 API를 불러오지 못했습니다.')
        return response.json() as Promise<KnowledgeSource[]>
      })
      .then(setSources)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '출처 목록을 불러오지 못했습니다.'))
  }, [])

  const verified = sources?.filter((source) => source.review_status === 'Verified').length ?? 0
  const official = sources?.filter((source) => source.source_type === 'official-public').length ?? 0

  const runExplain = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (explainQuery.trim().length < 2) return
    setTraceState('loading')
    setTrace(null)
    try {
      const response = await fetch(`/api/knowledge/explain?q=${encodeURIComponent(explainQuery.trim())}`)
      if (!response.ok) throw new Error('검색 판단 API를 불러오지 못했습니다.')
      setTrace(await response.json() as RetrievalTrace)
      setTraceState('idle')
    } catch {
      setTraceState('error')
    }
  }

  return <>
    <section className="page-heading">
      <div><p className="eyebrow">KNOWLEDGE GOVERNANCE</p><h1>지식 출처 관리</h1><p>답변 근거의 원문, 제공 기관, 확인일과 재검토 상태를 관리합니다.</p></div>
    </section>
    {!sources ? <section className="list-card evaluation-loading">{error || '지식 출처를 불러오고 있습니다.'}</section> : <>
      <section className="summary-grid">
        <Metric label="전체 근거" value={String(sources.length)} />
        <Metric label="공식 공개자료" value={String(official)} tone="good" />
        <Metric label="검증 완료" value={String(verified)} tone="good" />
        <Metric label="재검토 필요" value={String(sources.length - verified)} />
      </section>
      <div className="quality-note"><b>공식 원문 5건 연결</b><span>원문 전체가 아니라 검색에 필요한 내용을 요약해 사용하며, 실제 안내 전 원문과 고객 계약 조건을 다시 확인합니다.</span></div>
      <section className="trace-card">
        <div className="trace-card-heading"><div><p className="eyebrow">RETRIEVAL TRACE</p><h2>검색 판단 확인</h2><span>질문을 넣고 후보 점수와 근거 연결·중단 이유를 확인하세요.</span></div><b>최소 기준 8점</b></div>
        <form className="trace-form" onSubmit={runExplain}>
          <input value={explainQuery} onChange={(event) => setExplainQuery(event.target.value)} placeholder="검색 판단을 시험할 질문" />
          <button className="primary" disabled={traceState === 'loading'}>{traceState === 'loading' ? '계산 중' : '판단 확인'}</button>
        </form>
        {traceState === 'error' ? <div className="warning"><b>판단 확인 실패</b><p>API 서버 연결 상태를 확인해 주세요.</p></div> : null}
        {trace ? <TraceSummary trace={trace} /> : <p className="trace-placeholder">예시 질문이 입력되어 있습니다. ‘판단 확인’을 눌러 검색 중단 사례를 확인해 보세요.</p>}
      </section>
      <section className="list-card">
        <div className="table-wrap"><table>
          <thead><tr><th>문서 ID</th><th>근거 자료</th><th>제공 기관</th><th>기준일</th><th>확인일</th><th>상태</th><th>원문</th></tr></thead>
          <tbody>{sources.map((source) => <tr key={source.document_id}>
            <td className="mono">{source.document_id}</td>
            <td><strong>{source.title}</strong><span>{source.section}</span></td>
            <td>{source.source_organization || '-'}</td>
            <td>{source.effective_date || '원문 확인'}</td>
            <td>{source.verified_at || '-'}</td>
            <td><span className={`result-chip ${source.review_status === 'Verified' ? 'pass' : 'fail'}`}>{source.review_status === 'Verified' ? '검증 완료' : '재검토 필요'}</span></td>
            <td>{source.source_url ? <a className="source-link compact" href={source.source_url} target="_blank" rel="noreferrer">열기 ↗</a> : '-'}</td>
          </tr>)}</tbody>
        </table></div>
      </section>
    </>}
  </>
}

function TraceSummary({ trace, compact = false }: { trace: RetrievalTrace; compact?: boolean }) {
  const grounded = trace.decision === 'grounded'
  return <div className={`trace-result ${grounded ? 'grounded' : 'abstained'} ${compact ? 'compact' : ''}`}>
    <div className="trace-decision"><b>검색 판단</b><span className={`decision-chip ${grounded ? 'grounded' : 'abstained'}`}>{grounded ? '근거 연결' : '검색 중단'}</span></div>
    <p>{trace.reason}</p>
    {!compact ? <div className="trace-queries"><div><span>원본 질문</span><strong>{trace.original_query}</strong></div><div><span>확장 질의</span><strong>{trace.expanded_query}</strong>{trace.query_rule_ids.length ? <small>{trace.query_rule_ids.join(' · ')}</small> : null}</div></div> : null}
    {trace.candidates.length ? <div className="trace-candidates">{trace.candidates.map((candidate) => <div key={candidate.document_id}><div><strong>{candidate.document_id} · {candidate.title}</strong><span>{candidate.accepted ? '기준 통과' : '기준 미달'}</span></div><p>일치어 {candidate.matched_terms.join(' · ')} · <b>{candidate.score}점 / 기준 {trace.minimum_score}점</b></p></div>)}</div> : <small className="trace-empty">표시할 키워드 후보가 없습니다.</small>}
    {compact && trace.query_expansions.length ? <small className="trace-rules">질의 확장: {trace.query_expansions.join(' · ')} ({trace.query_rule_ids.join(' · ')})</small> : null}
  </div>
}

function ScoreSelector({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <div className="score-selector"><div><b>{label}</b><span>{value}점</span></div><small>1 매우 부정확 · 5 매우 정확</small><div>{[1, 2, 3, 4, 5].map((score) => <button type="button" key={score} className={value === score ? 'active' : ''} aria-label={`${label} ${score}점`} onClick={() => onChange(score)}>{score}</button>)}</div></div>
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) { return <article className={`metric ${tone ?? ''}`}><span>{label}</span><strong>{value}</strong></article> }
function RiskBadge({ risk }: { risk: RiskLevel }) { return <span className={`risk-badge ${risk.toLowerCase()}`}>{risk}<small>{riskLabels[risk]}</small></span> }
function PanelTitle({ title, subtitle }: { title: string; subtitle: string }) { return <div className="panel-title"><h2>{title}</h2><span>{subtitle}</span></div> }
function Info({ label, value }: { label: string; value: string }) { return <div className="info"><span>{label}</span><strong>{value}</strong></div> }

export default App
