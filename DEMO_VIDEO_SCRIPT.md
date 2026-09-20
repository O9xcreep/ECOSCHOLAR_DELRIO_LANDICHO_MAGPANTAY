# EcoScholar: Demo Video Script

**Runtime:** about 10-11 minutes at a relaxed speaking pace
**Cast:** **ADMIN** (host, LGU staff) and **STUDENT** (applicant)
**Placeholders:** replace `[ADMIN NAME]`, `[STUDENT NAME]`, `[LGU NAME]` before recording.

**How to read it:** `[SCREEN]` is what should be showing. *(Italics in brackets)* are actions to perform. Everything else is spoken aloud.

---

## Before you hit record

- **Wake the server.** The backend is on Render and sleeps when idle. Open your backend's `/api/health` URL about a minute before recording. Otherwise the first login can hang, and the app gives up after 15 seconds.
- **Use two separate browser sessions** (a normal window plus an incognito window, or two different browsers). The login session is stored in the browser, so one browser would log one of you out.
- **The student needs a real inbox.** Registration sends a 6-digit email code.
- **Have an LGU join code ready** from the admin's Settings > Team tab.
- **Have the program ready to start.** The admin needs to be able to click "Set Up Scholarship Program" (or "Reset & Start New Program") with a deadline in the future. Students cannot apply until a program is open.
- **Sample documents:** `backend/test_data/ocr_verification/` has one folder per document type. OCR checks the student's name, school and address against the paper, so type details that match the files you upload. Or mismatch one on purpose to show the warnings.
- **Set the applicant limit to 1** if you have other test applicants, so the waitlist appears in the Ranking scene. With a single student in the system, you can only *explain* the waitlist.
- **Do not run** `backend/scripts/seed_demo_applicants.py` against your live database. It wipes all applicants, flags and notifications.
- **OCR takes a few seconds per document** in the review scene. Trim the wait in editing.

---

## Scene 1: Intro (0:00-0:40)

`[SCREEN]` Login page, showing the EcoScholar logo and tagline.

**ADMIN:** Hi everyone, I'm [ADMIN NAME], and today I'm playing the LGU admin.

**STUDENT:** And I'm [STUDENT NAME], and I'll be the student applying for the scholarship.

**ADMIN:** This is EcoScholar, a centralized scholarship allocation system for local government units. Scholarship selection is usually slow and manual. There are paper forms, someone checking every document by hand, and plenty of room for mistakes or fraud. EcoScholar automates the tedious parts, but a person still stays in charge.

**STUDENT:** In the next ten minutes we'll follow the whole journey. The LGU opens a program, I apply, the admin reviews and ranks, and I get my result.

---

## Scene 2: How it's built (0:40-1:30)

`[SCREEN]` A simple diagram slide: **React web app (Vercel)** to **Flask API (Render)** to **MongoDB Atlas**. Two extra boxes hang off the API: **Tesseract OCR** and **XGBoost + Random Forest model**.

**ADMIN:** Quick look under the hood. There's one React web app with two portals, one for students and one for LGU staff. Both talk to a Flask API, and all the data and uploaded documents are stored in MongoDB.

**ADMIN:** Two pieces of automation sit behind the API. Tesseract OCR reads the text on uploaded documents, so we can check they really belong to the applicant. And a machine-learning model decides eligibility and ranks applicants. It's an XGBoost classifier plus a random forest regressor.

**ADMIN:** Everything is scoped per LGU. Each LGU has its own program, its own applicants, its own form and its own staff, and they can't see each other's data.

---

## Scene 3: Admin sets up the program (1:30-3:00)

`[SCREEN]` Admin browser. *(Sign in.)* The top bar shows `[LGU NAME]`. *(Go to Settings > System.)*

**ADMIN:** I'm signed in as the LGU admin, and the top bar shows which LGU I'm managing. Nothing can happen until a program exists, so I start in Settings, System tab.

**ADMIN:** In Scholarship Program Creation I set the Accepted Applicant Limit, which is how many scholarships we can actually give. *(Enter a number.)* I choose Result Visibility, which decides whether students see decisions right away or only after a date I pick. I name the batch, and I set an application deadline. When that deadline passes, applications close automatically.

*(Click **Set Up Scholarship Program**.)*

**ADMIN:** The program is live. Further down, the Form Builder lets me add my own questions and choose which documents students must upload. By default that's the Enrollment Form, Barangay Endorsement, School ID, Grade 12 Grades and Proof of Income, with the 4Ps certificate optional.

**ADMIN:** Two safeguards here. Once a program is open, the form locks, so nobody changes the rules midway. And any custom question I add is for our records only. It can never reach the scoring model.

*(Go to the Team tab.)*

**ADMIN:** Last thing before I hand over. In the Team tab is our LGU Join Code. Students need it to register, and that's how each applicant lands in the right LGU. [STUDENT NAME], I'll send you mine.

*(Optional: flash the Guide tab.)* There's also a Guide tab that walks new staff through all of this.

---

## Scene 4: Student registers (3:00-4:15)

`[SCREEN]` Student browser, on the Login page. *(Click **Create Account**.)*

**STUDENT:** I'm a new student, so I'll create an account. First I enter the join code from my admin. *(Type it and click out of the field.)* It confirms "Joining [LGU NAME]", so I know I've got the right one.

**STUDENT:** Then my name, email and a password. There's a strength meter, and I have to agree to the Data Privacy Act consent, because the system handles personal information. *(Tick the box, click Next.)*

**STUDENT:** Step two is my personal and family details: address, my parents' occupation and education, household income, housing situation, and my siblings. This is the information the eligibility model looks at. It's also saved to my account, so I won't have to type it again on the application.

*(Click **Create Account**.)*

**STUDENT:** To prove the email is really mine, EcoScholar sends a 6-digit code. *(Enter it, click Verify & Continue.)* And I'm in.

---

## Scene 5: Student applies (4:15-5:45)

`[SCREEN]` Student Dashboard.

**STUDENT:** This is my dashboard. Four tiles show my completion, steps done, documents uploaded and documents still missing, and my status says Not Started. Let me click Start Application.

*(Step 1.)* Step one is already filled in from registration.

*(Step 2.)* Step two is academic: my school, course, year level and GWA.

*(Step 3.)* Step three is requirements. I upload each document as a PDF, JPG or PNG, tick the privacy consent, and submit. *(Click Submit.)*

**STUDENT:** Done. Back on the dashboard, my status is Newly Submitted, I have an application ID, and every document shows as Uploaded.

*(Click Applicant Details.)*

**STUDENT:** Applicant Details shows everything I submitted. I can replace a document or withdraw the application. The Guidelines page has the LGU's rules, and this bell will notify me whenever something changes.

**ADMIN (voice-over):** Behind the scenes, every uploaded file was fingerprinted. If the exact same file, or a slightly edited copy, was submitted by another applicant, or the file's metadata shows an editing tool, it becomes an alert for me. It's never an automatic rejection.

---

## Scene 6: Admin reviews and the model decides (5:45-8:15)

`[SCREEN]` Admin browser, Dashboard.

**ADMIN:** Back on my side, the dashboard gives me the overview: status distribution, approved versus rejected, submissions over time, recent applications, and a history log. This is also where the Duplicate Application Alerts I mentioned show up.

*(Go to Applications.)*

**ADMIN:** The Applications page sorts everything into Needs Attention, Waitlisted and Decided. [STUDENT NAME]'s application is under Newly Submitted. *(Open it.)*

**ADMIN:** I can see everything they submitted and open each document myself. I have two choices. If something is blurry or missing, I use **Request Changes**, write a comment, and the student is notified and can fix it. Nothing is decided yet. Otherwise I click **Start Eligibility**.

*(Click **Start Eligibility** and wait.)*

**ADMIN:** Two things happen here. First, OCR reads every document. Is the applicant's name on it? Does the school match? Is it actually an enrollment form? On the income and grade documents, it compares the number on the paper against what the student typed, and it flags big differences. Those show up as warnings, "worth a look before deciding". They never reject anyone by themselves, because whether a document is genuine is a human judgment.

*(Result appears.)*

**ADMIN:** Second, the model scores the application. I get a score out of 100, an Eligible or Not Eligible status, and a breakdown showing where the applicant is strong or weak: GWA, income need, family size, parents' education and housing.

**ADMIN:** The classifier answers "eligible or not". The regressor produces the priority score we rank with. If someone isn't eligible, they're rejected right away with a plain-English reason. Every action goes into an audit trail, and once a decision is made it's final. When there are many applicants, I can select a batch and run this in bulk.

---

## Scene 7: Ranking and the waitlist (8:15-9:15)

`[SCREEN]` Admin > Ranking.

**ADMIN:** The Ranking page lists every eligible applicant by priority score. The top applicants, as many as my applicant limit, are Approved and sit under "Within Scholarship Slots". Eligible applicants beyond that are Waitlisted.

*(If you have a waitlisted applicant: raise the limit by one.)*

**ADMIN:** Watch what happens when I raise the limit. The next person on the waitlist is promoted automatically and notified. Nobody has to be re-reviewed. *(Or, with a single applicant: "If I raised the limit, the next person on the waitlist would be promoted automatically.")*

**ADMIN:** And I can export the ranking as a PDF for our records.

---

## Scene 8: Student sees the result (9:15-9:50)

`[SCREEN]` Student browser. *(Click the bell, then go to the Dashboard.)*

**STUDENT:** I have a new notification, and my dashboard now shows my result. *(Approved: "Congratulations. Your scholarship application has been approved.")*

**STUDENT:** If I had been waitlisted, it would tell me I met the criteria but the slots were taken, and that I could be promoted automatically if one opens up. If I hadn't been eligible, I'd see a plain explanation of why.

**ADMIN (voice-over):** And if I'd chosen to hold results until a set date, the student would only see "your application has finished review, results will be available once released" until then.

---

## Scene 9: Closing a program and managing the team (9:50-10:40)

`[SCREEN]` Admin > Settings > System, then Team.

**ADMIN:** When a program ends, I export the data and click Reset & Start New Program. Nothing is deleted. Past programs are archived and still count in the reports, and students can apply again in the next one.

*(Go to Team.)*

**ADMIN:** In the Team tab I can invite colleagues and control exactly what each person can do: review applicants, manage team members, or manage the program itself. New LGUs join the platform by applying for admin access, and the platform Super Admin approves them after checking proof of employment.

---

## Scene 10: Wrap-up (10:40-11:20)

`[SCREEN]` Login page, or the logo again.

**ADMIN:** To sum up, EcoScholar takes a scholarship program from opening to results. Students register and apply online, OCR and duplicate checks support the reviewer, the model scores and ranks consistently, and a person makes the final call.

**STUDENT:** And it's built with privacy in mind: email verification, hashed passwords, Data Privacy Act consent, and each LGU's data kept separate. The backend has automated tests that run on every push. *(Optional: "We also load-tested it with Locust.")*

**ADMIN:** Thanks for watching.

**STUDENT:** Thank you!

---

## If you need it shorter (about 7 minutes)

- Cut Scene 2 to one sentence, or drop it.
- Drop Scene 9.
- Skip the "ADMIN (voice-over)" asides in Scenes 5 and 8.
