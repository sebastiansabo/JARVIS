// @ts-check
import { test, expect } from '@playwright/test'

const EMAIL = 'sebastian.sabo@autoworld.ro'
const PASSWORD = 'Molusca25.'
const BASE = '/hr/courses/api'

/**
 * HR Courses Module — Audit Test
 *
 * Validates every feature from the original plan against staging.
 * Each test is independent and reports PASS/FAIL so we know what exists vs what's missing.
 */

// Each test logs in independently — no serial dependency

/** Login once, reuse session across all tests in this file */
test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[name="email"]', EMAIL)
  await page.fill('input[name="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/app/**', { timeout: 15000 })
})

// ──────────────────────────────────────────────
// 1. NAVIGATION & LIST VIEW
// ──────────────────────────────────────────────

test.describe('1. Navigation & Courses List', () => {
  test('1.1 Can navigate to HR → Cursuri tab', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // The Cursuri tab should be visible and active
    const tab = page.getByRole('tab', { name: 'Cursuri' })
    await expect(tab).toBeVisible({ timeout: 10000 })
  })

  test('1.2 Courses table renders with expected columns', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Check for table headers
    const expectedColumns = ['Name', 'Type', 'Company', 'Dates', 'Trainer', 'Participants', 'Budget', 'Status', 'Actions']
    for (const col of expectedColumns) {
      const header = page.locator('th', { hasText: col })
      const isVisible = await header.isVisible().catch(() => false)
      console.log(`  Column "${col}": ${isVisible ? 'PRESENT' : 'MISSING'}`)
    }

    // At minimum, the table should exist
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('1.3 Courses data loads (not empty)', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Check if there are rows in the table or an empty state
    const rows = page.locator('tbody tr')
    const rowCount = await rows.count()
    console.log(`  Courses loaded: ${rowCount} rows`)

    // We inserted dummy data, so there should be rows
    expect(rowCount).toBeGreaterThan(0)
  })
})

// ──────────────────────────────────────────────
// 2. FILTERS
// ──────────────────────────────────────────────

test.describe('2. Filters', () => {
  test('2.1 Type filter dropdown exists and has options', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Find and click the type filter trigger
    const typeFilter = page.locator('button', { hasText: 'All types' })
    const isVisible = await typeFilter.isVisible().catch(() => false)
    console.log(`  Type filter: ${isVisible ? 'PRESENT' : 'MISSING'}`)

    if (isVisible) {
      await typeFilter.click()
      // Check if dropdown items appear
      const items = page.locator('[role="option"]')
      const count = await items.count()
      console.log(`  Type filter options: ${count}`)
      expect(count).toBeGreaterThan(1) // At least "All types" + one real type
      // Close dropdown
      await page.keyboard.press('Escape')
    }
  })

  test('2.2 Status filter dropdown exists and has options', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const statusFilter = page.locator('button', { hasText: 'All statuses' })
    const isVisible = await statusFilter.isVisible().catch(() => false)
    console.log(`  Status filter: ${isVisible ? 'PRESENT' : 'MISSING'}`)

    if (isVisible) {
      await statusFilter.click()
      const items = page.locator('[role="option"]')
      const count = await items.count()
      console.log(`  Status filter options: ${count}`)
      expect(count).toBeGreaterThan(1)
      await page.keyboard.press('Escape')
    }
  })

  test('2.3 Year filter exists (archive feature)', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Check for year or month filter dropdowns
    const yearFilter = page.locator('button, select').filter({ hasText: /year|an|202/i })
    const isVisible = await yearFilter.first().isVisible().catch(() => false)
    console.log(`  Year filter: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })

  test('2.4 Month filter exists (archive feature)', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const monthFilter = page.locator('button, select').filter({ hasText: /month|luna/i })
    const isVisible = await monthFilter.first().isVisible().catch(() => false)
    console.log(`  Month filter: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 3. COURSE CRUD
// ──────────────────────────────────────────────

test.describe('3. Course CRUD', () => {
  test('3.1 Add Course button exists and navigates to form', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const addBtn = page.locator('button', { hasText: /add course/i })
    await expect(addBtn).toBeVisible()

    await addBtn.click()
    await page.waitForURL('**/courses/add**', { timeout: 5000 })
    console.log('  Add Course page loads: YES')
  })

  test('3.2 Course form has all required fields', async ({ page }) => {
    await page.goto('/app/hr/courses/add')
    await page.waitForLoadState('networkidle')

    const fields = {
      'Course Name': page.locator('label', { hasText: /course name/i }),
      'Course Type': page.locator('label', { hasText: /course type/i }),
      'Start Date': page.locator('label', { hasText: /start date/i }),
      'End Date': page.locator('label', { hasText: /end date/i }),
      'Company': page.locator('label', { hasText: /company/i }),
      'Trainer': page.locator('label', { hasText: /trainer/i }),
      'Location': page.locator('label', { hasText: /location/i }),
      'Budget': page.locator('label', { hasText: /budget/i }),
      'Currency': page.locator('label', { hasText: /currency/i }),
      'Description': page.locator('label', { hasText: /description/i }),
    }

    for (const [name, locator] of Object.entries(fields)) {
      const isVisible = await locator.isVisible().catch(() => false)
      console.log(`  Field "${name}": ${isVisible ? 'PRESENT' : 'MISSING'}`)
    }
  })

  test('3.3 Edit course — clicking row navigates to edit form', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    const exists = await firstRow.isVisible().catch(() => false)
    if (!exists) {
      console.log('  No courses to edit — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    console.log('  Edit page loads: YES')

    // Check that form is pre-filled
    const nameInput = page.locator('input').first()
    const value = await nameInput.inputValue()
    console.log(`  Form pre-filled: ${value ? 'YES' : 'NO'}`)
  })

  test('3.4 Delete button visible on courses list', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Look for trash/delete icons in the actions column
    const deleteBtn = page.locator('tbody tr').first().locator('button.text-destructive, button:has(svg.lucide-trash-2)')
    const isVisible = await deleteBtn.isVisible().catch(() => false)
    console.log(`  Delete button on list: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })

  test('3.5 Delete button visible on detail/edit page', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    // Look for delete button on the detail page
    const deleteBtn = page.locator('button', { hasText: /delete/i })
    const isVisible = await deleteBtn.isVisible().catch(() => false)
    console.log(`  Delete button on detail page: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 4. ENROLLMENTS
// ──────────────────────────────────────────────

test.describe('4. Enrollments', () => {
  test('4.1 Employee search visible on course edit page', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const searchInput = page.locator('input[placeholder*="employee" i], input[placeholder*="Search" i]')
    const isVisible = await searchInput.first().isVisible().catch(() => false)
    console.log(`  Employee search input: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })

  test('4.2 Enrollment list shows existing enrollments', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const enrollmentList = page.locator('text=Current Enrollments')
    const isVisible = await enrollmentList.isVisible().catch(() => false)
    console.log(`  Enrollment list: ${isVisible ? 'PRESENT (has enrollments)' : 'MISSING or empty'}`)
  })

  test('4.3 Complete enrollment button exists', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    // Look for the green checkmark complete button
    const completeBtn = page.locator('button.text-green-600, button[title*="Complete" i]')
    const isVisible = await completeBtn.first().isVisible().catch(() => false)
    console.log(`  Complete enrollment button: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 5. DETAIL PAGE TABS (Invoices, Documents, Certifications)
// ──────────────────────────────────────────────

test.describe('5. Detail Page Tabs', () => {
  test('5.1 Invoice tab exists on course detail page', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const invoiceTab = page.locator('button, [role="tab"]').filter({ hasText: /invoice|factur/i })
    const isVisible = await invoiceTab.first().isVisible().catch(() => false)
    console.log(`  Invoice tab: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })

  test('5.2 Documents/DMS tab exists on course detail page', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const docsTab = page.locator('button, [role="tab"]').filter({ hasText: /document|documente|dms/i })
    const isVisible = await docsTab.first().isVisible().catch(() => false)
    console.log(`  Documents tab: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })

  test('5.3 Certifications tab exists on course detail page', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    const firstRow = page.locator('tbody tr').first()
    if (!(await firstRow.isVisible().catch(() => false))) {
      console.log('  No courses — SKIP')
      return
    }

    await firstRow.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const certsTab = page.locator('button, [role="tab"]').filter({ hasText: /certific/i })
    const isVisible = await certsTab.first().isVisible().catch(() => false)
    console.log(`  Certifications tab: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 6. BACKEND API ENDPOINTS
// ──────────────────────────────────────────────

test.describe('6. Backend API Endpoints', () => {
  test('6.1 GET /api/courses returns data', async ({ page }) => {
    const response = await page.request.get(`${BASE}/courses`)
    console.log(`  GET /api/courses: ${response.status()}`)
    expect(response.status()).toBe(200)

    const data = await response.json()
    console.log(`  Courses returned: ${data.courses?.length ?? 'N/A'}, total: ${data.total ?? 'N/A'}`)
  })

  test('6.2 GET /api/course-types returns data', async ({ page }) => {
    const response = await page.request.get(`${BASE}/course-types`)
    console.log(`  GET /api/course-types: ${response.status()}`)
    expect(response.status()).toBe(200)

    const data = await response.json()
    console.log(`  Course types returned: ${Array.isArray(data) ? data.length : 'N/A'}`)
  })

  test('6.3 GET /api/certifications returns data', async ({ page }) => {
    const response = await page.request.get(`${BASE}/certifications`)
    console.log(`  GET /api/certifications: ${response.status()}`)
    expect(response.status()).toBe(200)
  })

  test('6.4 GET /api/certifications/expiring returns data', async ({ page }) => {
    const response = await page.request.get(`${BASE}/certifications/expiring?days=90`)
    console.log(`  GET /api/certifications/expiring: ${response.status()}`)
    expect(response.status()).toBe(200)
  })

  test('6.5 GET /api/courses/:id/invoices returns data', async ({ page }) => {
    // First get a course ID
    const coursesRes = await page.request.get(`${BASE}/courses`)
    const coursesData = await coursesRes.json()

    if (!coursesData.courses?.length) {
      console.log('  No courses — SKIP')
      return
    }

    const courseId = coursesData.courses[0].id
    const response = await page.request.get(`${BASE}/courses/${courseId}/invoices`)
    console.log(`  GET /api/courses/${courseId}/invoices: ${response.status()}`)
    expect(response.status()).toBe(200)
  })

  test('6.6 GET /api/courses/:id/enrollments returns data', async ({ page }) => {
    const coursesRes = await page.request.get(`${BASE}/courses`)
    const coursesData = await coursesRes.json()

    if (!coursesData.courses?.length) {
      console.log('  No courses — SKIP')
      return
    }

    const courseId = coursesData.courses[0].id
    const response = await page.request.get(`${BASE}/courses/${courseId}/enrollments`)
    console.log(`  GET /api/courses/${courseId}/enrollments: ${response.status()}`)
    expect(response.status()).toBe(200)
  })

  test('6.7 GET /profile/api/courses returns data (Profile tab)', async ({ page }) => {
    const response = await page.request.get('/profile/api/courses')
    console.log(`  GET /profile/api/courses: ${response.status()}`)
    // May return 404 if not implemented
    if (response.status() === 200) {
      console.log('  Profile courses endpoint: IMPLEMENTED')
    } else {
      console.log(`  Profile courses endpoint: NOT IMPLEMENTED (${response.status()})`)
    }
  })

  test('6.8 DMS module links support hr_course', async ({ page }) => {
    const coursesRes = await page.request.get(`${BASE}/courses`)
    const coursesData = await coursesRes.json()

    if (!coursesData.courses?.length) {
      console.log('  No courses — SKIP')
      return
    }

    const courseId = coursesData.courses[0].id
    const response = await page.request.get(`/dms/api/dms/module-links/hr_course/${courseId}`)
    console.log(`  DMS module-links for hr_course: ${response.status()}`)
    if (response.status() === 200) {
      console.log('  DMS integration: WORKING')
    } else {
      console.log(`  DMS integration: NOT WORKING (${response.status()})`)
    }
  })
})

// ──────────────────────────────────────────────
// 7. SOFT DELETE & ARCHIVE
// ──────────────────────────────────────────────

test.describe('7. Soft Delete & Archive', () => {
  test('7.1 Courses have deleted_at field (soft delete)', async ({ page }) => {
    const response = await page.request.get(`${BASE}/courses`)
    const data = await response.json()

    if (!data.courses?.length) {
      console.log('  No courses — SKIP')
      return
    }

    const course = data.courses[0]
    const hasDeletedAt = 'deleted_at' in course
    console.log(`  deleted_at field: ${hasDeletedAt ? 'PRESENT' : 'MISSING'}`)
    console.log(`  Course fields: ${Object.keys(course).join(', ')}`)
  })

  test('7.2 Restore endpoint exists', async ({ page }) => {
    // Try to hit restore endpoint (even if it 404s we know it doesn't exist)
    const response = await page.request.post(`${BASE}/courses/99999/restore`)
    console.log(`  POST /api/courses/:id/restore: ${response.status()}`)
    if (response.status() === 404 || response.status() === 200) {
      console.log('  Restore endpoint: EXISTS')
    } else if (response.status() === 405) {
      console.log('  Restore endpoint: NOT IMPLEMENTED (Method Not Allowed)')
    } else {
      console.log(`  Restore endpoint: UNKNOWN (${response.status()})`)
    }
  })

  test('7.3 Year/month filter params supported in API', async ({ page }) => {
    const response = await page.request.get(`${BASE}/courses?year=2025&month=6`)
    console.log(`  GET /api/courses?year=2025&month=6: ${response.status()}`)
    const data = await response.json()
    console.log(`  Year/month filtering: ${response.status() === 200 ? 'ACCEPTED (may not filter)' : 'ERROR'}`)
    console.log(`  Results: ${data.courses?.length ?? 'N/A'}`)
  })
})

// ──────────────────────────────────────────────
// 8. COLUMN MANAGEMENT
// ──────────────────────────────────────────────

test.describe('8. Column Management', () => {
  test('8.1 Column toggle button exists on courses tab', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // ColumnToggle is usually a button with a columns/settings icon
    const colToggle = page.locator('button[title*="column" i], button[aria-label*="column" i], button:has(svg.lucide-columns), button:has(svg.lucide-settings-2)')
    const isVisible = await colToggle.first().isVisible().catch(() => false)
    console.log(`  Column toggle: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 9. CERTIFICATIONS & VALIDITY
// ──────────────────────────────────────────────

test.describe('9. Certifications & Validity', () => {
  test('9.1 Certifications show days_until_expiry', async ({ page }) => {
    const response = await page.request.get(`${BASE}/certifications/expiring?days=365`)
    const data = await response.json()

    if (Array.isArray(data) && data.length > 0) {
      const cert = data[0]
      const hasExpiry = 'days_until_expiry' in cert
      console.log(`  days_until_expiry field: ${hasExpiry ? 'PRESENT' : 'MISSING'}`)
      console.log(`  Cert fields: ${Object.keys(cert).join(', ')}`)
    } else {
      console.log('  No expiring certifications found — SKIP')
    }
  })

  test('9.2 Course types show default_validity_months', async ({ page }) => {
    const response = await page.request.get(`${BASE}/course-types`)
    const data = await response.json()

    if (Array.isArray(data) && data.length > 0) {
      const ct = data[0]
      const hasValidity = 'default_validity_months' in ct
      console.log(`  default_validity_months field: ${hasValidity ? 'PRESENT' : 'MISSING'}`)
      if (hasValidity) {
        console.log(`  Example: ${ct.name} = ${ct.default_validity_months} months`)
      }
    }
  })
})

// ──────────────────────────────────────────────
// 10. PROFILE TAB
// ──────────────────────────────────────────────

test.describe('10. Profile My Courses Tab', () => {
  test('10.1 Profile page has Courses tab', async ({ page }) => {
    await page.goto('/app/profile')
    await page.waitForLoadState('networkidle')

    const coursesTab = page.locator('button, [role="tab"]').filter({ hasText: /course|cursuri/i })
    const isVisible = await coursesTab.first().isVisible().catch(() => false)
    console.log(`  Profile Courses tab: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})

// ──────────────────────────────────────────────
// 11. APPROVAL FLOW
// ──────────────────────────────────────────────

test.describe('11. Approval Flow', () => {
  test('11.1 Submit approval button visible for draft courses', async ({ page }) => {
    await page.goto('/app/hr/courses')
    await page.waitForLoadState('networkidle')

    // Find a draft course by checking status badges
    const draftBadge = page.locator('tbody tr').filter({ hasText: 'Draft' }).first()
    if (!(await draftBadge.isVisible().catch(() => false))) {
      console.log('  No draft courses — SKIP')
      return
    }

    await draftBadge.click()
    await page.waitForURL('**/courses/**/edit**', { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    const approvalBtn = page.locator('button', { hasText: /submit.*approval|aprob/i })
    const isVisible = await approvalBtn.isVisible().catch(() => false)
    console.log(`  Submit for approval button: ${isVisible ? 'PRESENT' : 'MISSING'}`)
  })
})
