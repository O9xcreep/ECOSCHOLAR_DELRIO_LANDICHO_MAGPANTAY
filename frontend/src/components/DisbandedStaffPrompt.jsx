import { useNavigate } from 'react-router-dom'
import './DisbandedOrganizationPrompt.css'

// Admin-portal counterpart of DisbandedOrganizationPrompt, for staff whose LGU was
// deleted. Staff can't join another org with just a code - a join code isn't a
// secret, so it needs an existing admin's approval - which is why this points to
// the request form in Settings instead of taking a code itself.
function DisbandedStaffPrompt({ disbandedName, onSettings }) {
  const navigate = useNavigate()

  return (
    <div className="dop-wrap">
      <div className="dop-card">
        <h2 className="dop-title">
          {disbandedName ? 'Your organization has been disbanded' : "You're not part of an organization"}
        </h2>
        {disbandedName ? (
          <p className="dop-text">
            <strong>{disbandedName}</strong> has been disbanded by its administrator, so you no longer
            have access to it.
          </p>
        ) : (
          <p className="dop-text">You need to belong to an organization before you can review anything.</p>
        )}
        <p className="dop-text">
          To keep working, request to join another organization with its join code. An admin there
          will review your request.
        </p>

        {onSettings ? (
          <p className="dop-text">
            Use <strong>Request to Join Another Organization</strong> under Your Organizations below.
          </p>
        ) : (
          <button className="dop-btn" onClick={() => navigate('/admin/settings')}>
            Request to Join Another Organization
          </button>
        )}
      </div>
    </div>
  )
}

export default DisbandedStaffPrompt
