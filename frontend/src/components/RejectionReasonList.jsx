// The reasons a reviewer ticked for a rejected application. The server only sends
// them once results are released, and never for waitlisted applicants.
function RejectionReasonList({ application }) {
  const reasons = [...(application?.rejection_reasons || [])]
  if (application?.rejection_note) reasons.push(application.rejection_note)
  if (reasons.length === 0) return null
  return (
    <div style={{ marginTop: '10px', fontSize: '13px' }}>
      <strong>Reasons given by the reviewer</strong>
      <ul style={{ margin: '6px 0 0 20px', lineHeight: 1.6 }}>
        {reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  )
}

export default RejectionReasonList
