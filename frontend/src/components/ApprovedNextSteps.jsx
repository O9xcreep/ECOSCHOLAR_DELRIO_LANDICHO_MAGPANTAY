import './ApprovedNextSteps.css'

// Shown to a student once their approval is released. EcoScholar ends at the
// approval decision - the grant itself is released by the LGU's scholarship
// office - so this tells them what to expect rather than promising a date.
function ApprovedNextSteps() {
  return (
    <p className="ans-note">
      <strong>What happens next:</strong> your LGU's scholarship office will let you know
      when and where to claim your grant. Keep an eye on your notifications and email,
      and bring a valid ID when you go.
    </p>
  )
}

export default ApprovedNextSteps
