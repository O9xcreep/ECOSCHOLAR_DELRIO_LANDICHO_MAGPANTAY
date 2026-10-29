import './ApprovedNextSteps.css'

// Shown to a student once their approval is released. EcoScholar ends at the
// approval decision - the grant itself is released by the LGU's scholarship
// office - so this tells them what to expect rather than promising a date.
function ApprovedNextSteps() {
  return (
    <div className="ans-box">
      <p className="ans-title">Next step: Disbursement of your scholarship grant</p>
      <ol className="ans-steps">
        <li>
          Your LGU's scholarship office will announce the disbursement schedule and
          venue. Watch your EcoScholar notifications and your email.
        </li>
        <li>
          When you claim your grant, bring a valid ID and your School ID or proof of
          enrollment, in case the office asks to verify your identity.
        </li>
        <li>
          Keep your contact number and email up to date so the office can reach you.
        </li>
      </ol>
    </div>
  )
}

export default ApprovedNextSteps
