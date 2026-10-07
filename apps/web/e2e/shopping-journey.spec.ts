import { randomUUID } from "node:crypto";

import { expect, test, type Locator, type Page } from "playwright/test";

const API_ORIGIN = "http://127.0.0.1:8000";

async function createProject(page: Page, purpose: string) {
  const title = `E2E ${purpose} ${randomUUID().slice(0, 8)}`;
  await page.goto("/");
  await page.getByLabel("Project name").fill(title);
  await page.getByLabel("What are you looking for?").fill(
    "A cordless vacuum for a small apartment that handles pet hair.",
  );
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  return { title, projectId: page.url().split("/").at(-1)! };
}

async function saveCategory(page: Page, category = "Vacuum") {
  await expect(page.locator("#overview-category")).toBeVisible();
  await page.locator("#overview-category").fill(category);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved revision" })).toBeVisible();
}

async function requirementItem(page: Page, label: string): Promise<Locator> {
  const item = page.locator(
    `.requirement-item:has(input.requirement-label-input[value=${JSON.stringify(label)}])`,
  );
  await expect(item, `requirement label ${JSON.stringify(label)}`).toHaveCount(1);
  return item;
}

async function addAndEditRequirement(page: Page, initial: string, updated: string) {
  await page.locator("#new-requirement-label").fill(initial);
  await page.locator("#new-requirement-detail").fill("For everyday cleaning in a small home.");
  await page.getByRole("button", { name: "Add requirement" }).click();
  const item = page.locator(".requirement-item").last();
  await expect(item.getByLabel("Requirement", { exact: true })).toHaveValue(initial);
  await expect(item).toBeVisible();
  await item.locator("input.requirement-label-input").fill(updated);
  await item.getByRole("button", { name: "Save requirement" }).click();
  const savedItem = await requirementItem(page, updated);
  await expect(savedItem.getByText("Requirement saved.")).toBeVisible();
  return savedItem;
}

async function researchOneManufacturerSource(card: Locator) {
  const sourceTargets = card.locator("details.research-target-controls").filter({
    hasText: "Choose source targets",
  });
  await sourceTargets.locator("summary").click();
  for (const label of [
    "Independent measurements",
    "Professional reviews",
    "Retailer listings",
    "Owner discussions",
  ]) {
    await sourceTargets.getByLabel(label).uncheck();
  }
  await card.getByRole("button", { name: "Research this variant" }).click();
  await expect(card.getByText(/Latest research completed/)).toBeVisible();
  await expect(card.getByRole("button", { name: "Inspect exact quote" })).toBeVisible();
}

test("desktop Shopping journey reaches researched decisions and revocable reuse", async ({ page }) => {
  await createProject(page, "vacuum decision");
  await saveCategory(page);
  await addAndEditRequirement(page, "Works well on pet hair", "Handles long pet hair");

  await page.getByRole("button", { name: "Ask assistant" }).click();
  const assistant = page.locator("#project-assistant-panel");
  await assistant.getByLabel("Your shopping request").fill(
    "This is a cordless vacuum for pet hair under 500 USD.",
  );
  await assistant.getByRole("button", { name: "Send" }).click();
  await assistant.getByRole("button", { name: "Apply suggestion" }).click();
  await expect(assistant.getByText(/Applied at project revision/)).toBeVisible();
  await expect(await requirementItem(page, "Works well with hair")).toBeVisible();
  await expect(page.locator("#budget-maximum")).toHaveValue("500.00");

  await page.getByRole("link", { name: "Discover", exact: true }).click();
  await page.getByRole("button", { name: "Start discovery" }).click();
  await expect(page.locator(".run-card .run-status")).toHaveText("succeeded");
  await expect(page.locator(".candidate-card").filter({ hasText: "Acme CleanVac AX-4" })).toBeVisible();
  await expect(page.locator(".candidate-card").filter({ hasText: "Breez CleanPet BP-2" })).toBeVisible();

  for (const model of ["Acme CleanVac AX-4", "Breez CleanPet BP-2"]) {
    const candidate = page.locator(".candidate-card").filter({ hasText: model });
    await candidate.getByRole("button", { name: "Normalize product page" }).click();
    await expect(candidate.getByText("Product details were saved.")).toBeVisible();
  }
  await expect(page.locator(".normalized-product-list > li")).toHaveCount(2);

  await page.getByRole("link", { name: "Research", exact: true }).click();
  await expect(page.locator(".research-variant-card")).toHaveCount(2);
  const cleanVac = page.locator(".research-variant-card").filter({ hasText: "CleanVac" });
  const cleanPet = page.locator(".research-variant-card").filter({ hasText: "CleanPet" });
  await researchOneManufacturerSource(cleanVac);
  await researchOneManufacturerSource(cleanPet);

  await page.setViewportSize({ width: 320, height: 820 });
  const inspectQuote = cleanVac.getByRole("button", { name: "Inspect exact quote" }).first();
  await inspectQuote.click();
  const evidenceDialog = page.getByRole("dialog", { name: "Evidence inspection" });
  await expect(evidenceDialog.locator("blockquote")).toContainText(
    "measured 60 minutes runtime in normal mode",
  );
  const closeEvidence = evidenceDialog.getByRole("button", { name: "Close evidence" });
  await expect(closeEvidence).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(evidenceDialog.getByRole("link", { name: "Open source" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(closeEvidence).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(inspectQuote).toBeFocused();

  await page.getByRole("link", { name: "Compare", exact: true }).click();
  const productPicker = page.locator(".comparison-product-picker");
  await productPicker.locator("input[type=checkbox]").nth(0).check();
  await productPicker.locator("input[type=checkbox]").nth(1).check();
  const dimensionForm = page.locator(".comparison-dimension-form");
  await dimensionForm.getByLabel("Type").selectOption("evidence");
  await dimensionForm.getByLabel("Attribute key").fill("runtime");
  await dimensionForm.getByLabel("Display label").fill("Runtime");
  await dimensionForm.getByRole("button", { name: "Add dimension" }).click();
  await page.getByRole("button", { name: "Save comparison" }).click();
  const comparisonTable = page.getByRole("region", { name: "Product comparison table" });
  await expect(comparisonTable).toBeVisible();
  await expect(comparisonTable).toContainText("runtime");
  const citedEvidence = comparisonTable.locator(".assistant-evidence-citation").first();
  await citedEvidence.getByText(/Inspect evidence/).click();
  await expect(citedEvidence.getByRole("link", { name: /Open source/ })).toBeVisible();
  await expect(citedEvidence).toContainText("measured 60 minutes runtime in normal mode.");

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByRole("link", { name: "Discover", exact: true }).click();
  const normalizedProducts = page.locator(".normalized-product-list > li");
  const cleanVacProduct = normalizedProducts.filter({ hasText: "CleanVac" });
  const cleanPetProduct = normalizedProducts.filter({ hasText: "CleanPet" });
  await cleanVacProduct.getByRole("button", { name: "Shortlist" }).click();
  await expect(cleanVacProduct.getByText(/Decision:\s*shortlisted/)).toBeVisible();
  await cleanPetProduct.getByText("Reject this product", { exact: true }).click();
  await cleanPetProduct.getByRole("button", { name: "Save rejection" }).click();
  await expect(cleanPetProduct.getByText(/Decision:\s*rejected/)).toBeVisible();

  await page.reload();
  await expect(page.locator(".normalized-product-list > li").filter({ hasText: "CleanVac" })
    .getByText(/Decision:\s*shortlisted/)).toBeVisible();
  await expect(page.locator(".normalized-product-list > li").filter({ hasText: "CleanPet" })
    .getByText(/Decision:\s*rejected/)).toBeVisible();

  await page.getByRole("link", { name: "Overview", exact: true }).click();
  const preferenceRequirement = await requirementItem(page, "Works well with hair");
  await preferenceRequirement.getByText("Propose as a shopping preference").click();
  await preferenceRequirement.getByRole("button", { name: "Save candidate for review" }).click();
  await expect(preferenceRequirement.getByText("Candidate saved for review in your profile.")).toBeVisible();

  await page.getByRole("link", { name: "Shopping Assistant home" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
  await expect(page.getByRole("heading", { name: "Make room for a better choice." })).toBeVisible();
  await page.getByRole("link", { name: "Shopping Profile" }).click();
  const profileReuse = page.getByRole("checkbox");
  if (!(await profileReuse.isChecked())) await profileReuse.check();
  const candidate = page.locator(".profile-list-item").filter({
    has: page.getByRole("heading", { name: "Works well with hair" }),
  });
  await candidate.getByRole("button", { name: "Accept into profile" }).click();
  const activePreferenceSection = page.locator("section.profile-section").filter({
    has: page.getByRole("heading", { name: "Shopping preferences" }),
  });
  const activePreference = activePreferenceSection.locator(".profile-list-item").filter({
    has: page.getByRole("heading", { name: "Works well with hair" }),
  });
  await expect(activePreference.getByText("active", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Shopping Assistant home" }).click();
  await createProject(page, "preference reuse");
  await saveCategory(page);
  const reuseForProject = page.getByRole("checkbox", {
    name: "Show applicable profile preferences in this project",
  });
  await reuseForProject.click();
  await expect(reuseForProject).toBeChecked({ timeout: 30_000 });
  const suggestion = page.locator(".project-preference-item").filter({ hasText: "Works well with hair" });
  await expect(suggestion).toBeVisible();
  await suggestion.getByRole("button", { name: "Add to requirements" }).click();
  await expect(page.getByText("From Shopping Profile · editable here")).toBeVisible();

  await page.getByRole("link", { name: "Shopping Assistant home" }).click();
  await page.getByRole("link", { name: "Shopping Profile" }).click();
  const preferenceEdit = page.locator("section.profile-section").filter({
    has: page.getByRole("heading", { name: "Shopping preferences" }),
  }).locator(".profile-list-item").filter({
    has: page.getByRole("heading", { name: "Works well with hair" }),
  });
  await preferenceEdit.getByText("Edit preference", { exact: true }).click();
  await preferenceEdit.getByRole("button", { name: "Revoke" }).click();
  await expect(preferenceEdit.getByText("revoked", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Shopping Assistant home" }).click();
  await createProject(page, "revoked preference check");
  await saveCategory(page);
  const futureReuseToggle = page.getByRole("checkbox", {
    name: "Show applicable profile preferences in this project",
  });
  await futureReuseToggle.click();
  await expect(futureReuseToggle).toBeChecked({ timeout: 30_000 });
  await expect(page.getByText("No unapplied profile preferences match this project.")).toBeVisible();
  await expect(page.locator(".project-preference-item")).toHaveCount(0);
});

test("stale requirement edits surface a conflict and preserve the remote version", async ({ page }) => {
  const { projectId } = await createProject(page, "stale edit");
  await page.locator("#new-requirement-label").fill("Initial criterion");
  await page.getByRole("button", { name: "Add requirement" }).click();
  const requirementEditor = page.locator(".requirement-item").last();
  await expect(requirementEditor.getByLabel("Requirement", { exact: true })).toHaveValue("Initial criterion");
  const requirement = await page.request.get(`${API_ORIGIN}/projects/${projectId}`);
  const project = await requirement.json();
  const savedRequirement = project.requirements.find(
    (item: { label: string }) => item.label === "Initial criterion",
  );
  expect(savedRequirement).toBeTruthy();

  const editor = requirementEditor;
  await editor.locator("input.requirement-label-input").fill("My local draft");
  const remoteUpdate = await page.request.patch(
    `${API_ORIGIN}/projects/${projectId}/requirements/${savedRequirement.id}`,
    { data: { expected_version: project.revision, label: "Saved from another edit" } },
  );
  expect(remoteUpdate.ok()).toBe(true);
  await editor.getByRole("button", { name: "Save requirement" }).click();
  await expect(editor.getByText(/This requirement changed in another edit/)).toBeVisible();
  await editor.getByRole("button", { name: "Use latest requirement" }).click();
  await editor.getByRole("button", { name: "Apply requirement draft" }).click();
  await expect(editor.locator("input.requirement-label-input")).toHaveValue("Saved from another edit");
});

test("assistant generation failure reaches a durable terminal state", async ({ page }) => {
  await createProject(page, "generation failure");
  await page.getByRole("button", { name: "Ask assistant" }).click();
  const assistant = page.locator("#project-assistant-panel");
  await assistant.getByLabel("Your shopping request").fill("E2E_TRIGGER_GENERATION_FAILURE");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Assistant suggestions are unavailable until the AI service is configured.")).toBeVisible();
  await expect(assistant.getByRole("button", { name: "Retry as a new message" })).toBeVisible();
});

test("reloading during assistant generation reconnects to the same saved proposal", async ({ page }) => {
  const { projectId } = await createProject(page, "assistant reconnect");
  const marker = `E2E_DELAYED_GENERATION_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const callsBeforeResponse = await page.request.get(`${API_ORIGIN}/__e2e__/intent-call-count`, {
    params: { marker },
  });
  expect((await callsBeforeResponse.json()).count).toBe(0);

  await page.getByRole("button", { name: "Ask assistant" }).click();
  const assistant = page.locator("#project-assistant-panel");
  await assistant.getByLabel("Your shopping request").fill(
    `${marker}: This is a cordless vacuum for pet hair under 500 USD.`,
  );
  const acceptedResponse = page.waitForResponse((response) =>
    response.url() === `${API_ORIGIN}/projects/${projectId}/messages` &&
    response.request().method() === "POST",
  );
  await assistant.getByRole("button", { name: "Send" }).click();
  const accepted = await (await acceptedResponse).json() as { assistant_message_id: string };
  const messageId = accepted.assistant_message_id;
  await expect(assistant.locator(".assistant-pending").last()).toBeVisible();

  const pendingHistoryResponse = await page.request.get(
    `${API_ORIGIN}/projects/${projectId}/messages?limit=100`,
  );
  const pendingHistory = await pendingHistoryResponse.json();
  const pendingMessage = pendingHistory.items.find(
    (message: { id: string }) => message.id === messageId,
  );
  expect(pendingMessage?.status).toBe("generating");
  await expect.poll(async () => {
    const callsWhilePending = await page.request.get(
      `${API_ORIGIN}/__e2e__/intent-call-count`,
      { params: { marker } },
    );
    return (await callsWhilePending.json()).count;
  }, { timeout: 2_000 }).toBe(1);

  await page.reload();
  await expect(page.getByRole("heading", { name: /E2E assistant reconnect/ })).toBeVisible();
  await page.getByRole("button", { name: "Ask assistant" }).click();
  const reconnectedAssistant = page.locator("#project-assistant-panel");
  const savedResponse = reconnectedAssistant.locator(".assistant-message-assistant")
    .filter({ hasText: "I’ve noted the shopping details" });
  await expect(savedResponse).toBeVisible();
  const proposal = savedResponse.getByRole("region", { name: "AI suggestion" });
  await expect(proposal).toBeVisible();
  await expect(proposal.getByRole("button", { name: "Apply suggestion" })).toBeVisible();

  const completedHistoryResponse = await page.request.get(
    `${API_ORIGIN}/projects/${projectId}/messages?limit=100`,
  );
  const completedHistory = await completedHistoryResponse.json();
  const completedMessage = completedHistory.items.find(
    (message: { id: string }) => message.id === messageId,
  );
  expect(completedMessage?.status).toBe("completed");
  expect(completedMessage?.proposal?.status).toBe("pending");
  expect(completedHistory.items.filter(
    (message: { role: string; paired_message_id?: string }) =>
      message.role === "user" && message.paired_message_id === messageId,
  )).toHaveLength(1);
  const callsAfterResponse = await page.request.get(`${API_ORIGIN}/__e2e__/intent-call-count`, {
    params: { marker },
  });
  expect((await callsAfterResponse.json()).count).toBe(1);
});

test("research provider failure is shown as a terminal failed run", async ({ page }) => {
  const { projectId } = await createProject(page, "research failure");
  await saveCategory(page);
  await page.getByRole("link", { name: "Discover", exact: true }).click();
  await page.getByLabel("What would you like to find?").fill("E2E_TRIGGER_RESEARCH_FAILURE");
  await page.getByRole("button", { name: "Start discovery" }).click();
  await expect(page.locator(".run-card .run-status")).toHaveText("failed");
  await expect(page.locator(".run-card")).toContainText("provider auth");
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/discover$`));
});

test("local authentication mode is explicit and opens the real project app", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Make room for a better choice." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toHaveCount(0);
  const projectsResponse = await page.request.get(`${API_ORIGIN}/projects`);
  expect(projectsResponse.status()).toBe(200);
});
