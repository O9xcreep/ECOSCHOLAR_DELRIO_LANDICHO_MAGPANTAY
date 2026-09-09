import './AdminGuide.css'

// Static walkthrough of the admin-side process - unlike student Guidelines
// (Guidelines.jsx/GuidelinesEditor.jsx), this describes how the *system itself*
// works, which is the same for every LGU, so it isn't admin-editable.
const STEPS = [
  {
    title: '1. Get your organization approved',
    body: (
      <>
        <p>
          A brand-new LGU is created through the public "Apply for Admin Access" page,
          choosing "Create a new organization." That request - including proof of
          employment/ID - goes to the platform Super Admin for review, the same way it
          would for someone joining an org that already exists. Once approved, your
          organization is active and you're its first admin.
        </p>
      </>
    ),
  },
  {
    title: '2. Set up your scholarship program',
    body: (
      <>
        <p>
          Nothing can happen until a program exists - students can't apply, and the
          application form is still editable. Go to <strong>Settings &rarr; System</strong> and
          fill in the "Scholarship Program Creation" card:
        </p>
        <ul>
          <li><strong>Accepted Applicant Limit</strong> - how many slots this program has (adjustable later too, from here or the Ranking page).</li>
          <li><strong>Result Visibility</strong> - whether students see an Approved/Rejected decision the moment it's made, or only after a date you set.</li>
          <li><strong>Batch</strong> - name the program by academic year, e.g. 2025-2026.</li>
          <li><strong>Application deadline</strong> - optional, but once set it's a hard cutoff: applications close automatically the moment it passes, with no extra step needed from you.</li>
        </ul>
        <p>
          Click <strong>Set Up Scholarship Program</strong> and students can start applying immediately.
        </p>
      </>
    ),
  },
  {
    title: '3. Configure the application form',
    body: (
      <>
        <p>
          In <strong>Settings &rarr; System</strong>, under Form Builder, you can add custom
          fields and choose which documents applicants must upload - but only
          <strong> before a program starts or after it ends</strong>. Once a program is
          open, the form locks so a mid-program change can't invalidate applications
          already in progress. The core fields the eligibility model reads (income,
          GWA, household details, etc.) can never be edited or removed - only added-to.
        </p>
      </>
    ),
  },
  {
    title: '4. Review applications',
    body: (
      <>
        <p>
          On the <strong>Applications</strong> page, open a pending applicant and choose one of two actions:
        </p>
        <ul>
          <li>
            <strong>Verify Documents &amp; Decide Eligibility</strong> - once the uploaded documents
            look correct and complete, this runs the eligibility model and immediately decides
            Approved or Rejected. This is final - a decided application can't be edited,
            withdrawn, or have its documents changed afterward, by the student or by you.
          </li>
          <li>
            <strong>Request Changes</strong> - if a document is missing, blurry, or wrong, write a
            comment instead of verifying. The applicant is notified with your comment and can
            submit a corrected application - nothing is decided yet, so this never touches the
            eligibility model.
          </li>
        </ul>
        <p>
          The OCR check available in the applicant modal is a manual aid for you during review -
          it never runs on the student's side and never decides anything by itself.
        </p>
      </>
    ),
  },
  {
    title: '5. Check the ranking',
    body: (
      <>
        <p>
          The <strong>Ranking</strong> page lists every scored applicant by the model's score,
          split into "Within Slots" (top N, where N is your Accepted Applicant Limit) and
          "Waitlisted" (eligible, but bumped by the slot limit - promoted automatically if a
          slot opens up). Adjust the limit here or in Settings at any time; raising or lowering
          it recomputes who's Approved without re-reviewing anyone.
        </p>
      </>
    ),
  },
  {
    title: '6. End the program and start the next one',
    body: (
      <>
        <p>
          Once the deadline passes (or you're just done reviewing), a banner appears on the
          Dashboard reminding you to export the ranking and reset. From the Ranking page,
          click <strong>Export Ranking PDF</strong> for your records, then go to{' '}
          <strong>Settings &rarr; System</strong> and use <strong>Reset &amp; Start New Program</strong>.
          Nothing is ever deleted - every past program's applicants stay fully visible in
          Reports/Dashboard, they just stop counting toward the new one.
        </p>
      </>
    ),
  },
  {
    title: '7. Manage your team',
    body: (
      <>
        <p>
          From <strong>Settings &rarr; Team</strong>, invite other LGU staff and choose what they
          can do: review applicants, manage the team, and/or reset the program. Granting
          "manage team" specifically requires a second admin's approval before it takes
          effect - a safeguard against one compromised or careless approval snowballing into
          more admin accounts.
        </p>
      </>
    ),
  },
]

function AdminGuide() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">How EcoScholar Works</h4>
        <p className="info-sub">
          A step-by-step walkthrough of the process, from getting your organization
          approved to closing out a program. Each step links to where you'd actually do it.
        </p>
      </div>

      {STEPS.map(step => (
        <div key={step.title} className="settings-card">
          <h4 className="card-label">{step.title}</h4>
          <div className="guide-body">
            {step.body}
          </div>
        </div>
      ))}
    </div>
  )
}

export default AdminGuide
