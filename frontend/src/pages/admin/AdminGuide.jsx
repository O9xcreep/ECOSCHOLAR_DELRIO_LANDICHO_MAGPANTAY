import './AdminGuide.css'

// Static walkthrough of the admin-side process - unlike student Guidelines
// (Guidelines.jsx/GuidelinesEditor.jsx), this describes how the *system itself*
// works, which is the same for every LGU, so it isn't admin-editable.
// Shown under Settings -> Team for every staff member.

const TERMS = [
  ['Program', 'One scholarship round, from when applications open until you start the next one.'],
  ['Eligibility bar', 'How needy an applicant must be to qualify at all, e.g. "top 30% of need". Chosen when a program starts; it stays the same for the whole program.'],
  ['Applicant limit', 'How many scholarships you can give. You can change it any time.'],
  ['Waitlisted', 'Qualified, but there was no slot left. They move up automatically if a slot opens.'],
]

const STEPS = [
  {
    title: '1. Get your LGU on EcoScholar',
    items: [
      <>Apply on the <strong>Apply for Admin Access</strong> page and choose <strong>Create a new organization</strong>. The platform admin checks your proof of employment and approves it.</>,
      <>Give students your LGU&apos;s <strong>join code</strong> (Settings &rarr; Team). They need it to register.</>,
    ],
  },
  {
    title: '2. Prepare the application form (optional)',
    items: [
      <>In <strong>Settings &rarr; System</strong>, add extra questions, pick the required documents, and write the student guidelines.</>,
      <>Do this <strong>before</strong> you start the program. The form locks while a program is open, so the rules can&apos;t change halfway.</>,
    ],
  },
  {
    title: '3. Start the program',
    items: [
      <>Go to <strong>Settings &rarr; System &rarr; Scholarship Program Creation</strong>.</>,
      <>Set the <strong>applicant limit</strong>, when students can see their <strong>results</strong>, the <strong>batch</strong> year, the <strong>application deadline</strong>, and the <strong>eligibility bar</strong>.</>,
      <>Click <strong>Set Up Scholarship Program</strong>. Students can apply right away, and applications close by themselves at the deadline.</>,
    ],
  },
  {
    title: '4. Review each application',
    items: [
      <>On the <strong>Applications</strong> page, open an applicant and check their documents.</>,
      <>Something wrong or missing? Click <strong>Request Changes</strong> and say what to fix. The student is notified and can send it again.</>,
      <>Everything looks right? Click <strong>Start Eligibility</strong>. The system reads the documents and decides: applicants who don&apos;t meet the eligibility bar are <strong>Rejected</strong>; the rest go to the ranking.</>,
      <>A decision is final. It can&apos;t be edited or withdrawn afterward.</>,
    ],
  },
  {
    title: '5. Check the ranking',
    items: [
      <>The <strong>Ranking</strong> page lists qualified applicants from most to least in need.</>,
      <>The top ones, up to your applicant limit, are <strong>Approved</strong>. The rest are <strong>Waitlisted</strong>.</>,
      <>Raise the limit and the next waitlisted applicants are approved automatically. No one needs to be reviewed again.</>,
    ],
  },
  {
    title: '6. Finish and start the next program',
    items: [
      <>After the deadline, click <strong>Export Ranking PDF</strong> on the Ranking page to keep a copy.</>,
      <>Then use <strong>Reset &amp; Start New Program</strong> in Settings &rarr; System. You can pick a new eligibility bar here.</>,
      <>Nothing is deleted. Past programs stay in your records.</>,
    ],
  },
  {
    title: '7. Add your team',
    items: [
      <>In <strong>Settings &rarr; Team</strong>, add staff and choose what each person can do: review applicants, manage the team, or manage the program.</>,
      <>Only give &quot;manage the team&quot; to someone you trust, since they can add and remove others.</>,
    ],
  },
]

function AdminGuide() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Words to know</h4>
        <div className="guide-body">
          <ul>
            {TERMS.map(([term, meaning]) => (
              <li key={term}><strong>{term}</strong> - {meaning}</li>
            ))}
          </ul>
        </div>
      </div>

      {STEPS.map(step => (
        <div key={step.title} className="settings-card">
          <h4 className="card-label">{step.title}</h4>
          <div className="guide-body">
            <ul>
              {step.items.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
        </div>
      ))}
    </div>
  )
}

export default AdminGuide
