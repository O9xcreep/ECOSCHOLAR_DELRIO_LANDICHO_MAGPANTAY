import './Guidelines.css'

function Guidelines() {
  return (
    <div className="guidelines-page">

      {/* Header */}
      <div className="gl-header">
        <h2 className="page-title">Application Guidelines</h2>
        <p className="page-sub">
          Please read the rules and instructions carefully before submitting.
        </p>
      </div>

      {/* Section 1 */}
      <div className="gl-card">
        <h3 className="gl-section-title">
          <span className="gl-dot blue" />
          General Eligibility Criteria
        </h3>
        <ul className="gl-list">
          <li>Must be a registered resident of the city with a valid Barangay Certificate.</li>
          <li>Must be currently enrolled or an incoming first-year college student in an accredited institution.</li>
          <li>Must maintain a minimum general weighted average (GWA) or GPA requirement as specified by your specific scholarship type.</li>
          <li>Combined family annual income must not exceed the threshold set for financial assistance (unless applying for pure merit-based slots).</li>
          <li>Must not be a recipient of any other government scholarship at the time of application.</li>
          <li>Must be a Filipino citizen.</li>
        </ul>
      </div>

      {/* Section 2 */}
      <div className="gl-card">
        <h3 className="gl-section-title">
          <span className="gl-dot blue" />
          Document Submission Rules
        </h3>
        <ul className="gl-list">
          <li><strong>File Format:</strong> All uploaded files must be in clear PDF, PNG, or JPEG format.</li>
          <li><strong>File Size:</strong> Individual document file sizes must not exceed 5MB.</li>
          <li>Ensure that scanned documents or photos are completely readable — blurry submissions can cause automatic rejection or delay processing.</li>
          <li>The <em>Proof of Income</em> must be an official Certificate of Indigency from your Barangay or an ITR from the BIR.</li>
          <li>All documents must be current and valid — expired documents will not be accepted.</li>
        </ul>
      </div>

      {/* Section 3 */}
      <div className="gl-card">
        <h3 className="gl-section-title">
          <span className="gl-dot blue" />
          Scholarship Types & Requirements
        </h3>
        <div className="gl-table-wrapper">
          <table className="gl-table">
            <thead>
              <tr>
                <th>Scholarship Type</th>
                <th>Minimum GWA</th>
                <th>Income Limit</th>
                <th>Slots</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Academic Merit</td>
                <td>1.75</td>
                <td>No limit</td>
                <td>60</td>
              </tr>
              <tr>
                <td>Financial Aid</td>
                <td>2.50</td>
                <td>Below ₱10,000/mo</td>
                <td>30</td>
              </tr>
              <tr>
                <td>Full Scholar</td>
                <td>1.50</td>
                <td>Below ₱5,000/mo</td>
                <td>20</td>
              </tr>
              <tr>
                <td>Loyalty Grant</td>
                <td>2.00</td>
                <td>Below ₱20,000/mo</td>
                <td>40</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Section 4 */}
      <div className="gl-card">
        <h3 className="gl-section-title">
          <span className="gl-dot blue" />
          Application Process
        </h3>
        <div className="gl-steps">
          {[
            { step: '1', title: 'Fill Personal Information', desc: 'Complete all required fields in Step 1 including parental and financial details.' },
            { step: '2', title: 'Provide Academic Information', desc: 'Enter your school, course, GWA, and semester details in Step 2.' },
            { step: '3', title: 'Upload Required Documents', desc: 'Upload all required supporting documents in Step 3 before submitting.' },
            { step: '4', title: 'Submit Application', desc: 'Click Submit Application. Your application will be reviewed by the scholarship committee.' },
            { step: '5', title: 'Wait for Results', desc: 'You will be notified via email once your application has been reviewed.' },
          ].map((item, i) => (
            <div key={i} className="gl-step">
              <div className="gl-step-circle">{item.step}</div>
              <div>
                <p className="gl-step-title">{item.title}</p>
                <p className="gl-step-desc">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Important Reminders */}
      <div className="gl-card gl-warning-card">
        <h3 className="gl-section-title">
          <span className="gl-dot yellow" />
          Important Reminders
        </h3>
        <div className="gl-warning">
          
          <p>
            <strong>Double-Check Your Data:</strong> Once you click{' '}
            <strong>Submit Application</strong> on Step 3, your files and
            details are sent directly to the screening committee. You will
            not be able to edit your entries while the review is active.
          </p>
        </div>
        <div className="gl-reminders">
          <div className="gl-reminder-item">
            
            <div>
              <p className="reminder-title">Deadline</p>
              <p className="reminder-desc">Applications close on June 30, 2026. Late submissions will not be accepted unless the system allows late applications.</p>
            </div>
          </div>
          <div className="gl-reminder-item">
            
            <div>
              <p className="reminder-title">Data Privacy</p>
              <p className="reminder-desc">All information submitted is protected under the Data Privacy Act of 2012 (RA 10173). Your data will only be used for scholarship evaluation.</p>
            </div>
          </div>
          <div className="gl-reminder-item">
            
            <div>
              <p className="reminder-title">Need Help?</p>
              <p className="reminder-desc">Contact the scholarship office at scholarship@ecoscolar.edu.ph or visit City Hall during office hours (8AM - 5PM, Mon-Fri).</p>
            </div>
          </div>
        </div>
      </div>

    </div>
  )
}

export default Guidelines