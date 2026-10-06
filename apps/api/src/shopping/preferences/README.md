# Shopping preferences

This module owns the local shopping profile, explicit preference candidates,
accepted preferences, applicability and context selection. Project requirements
remain authoritative for a project. A preference is a soft suggestion until the
user applies it as an editable requirement in a project.

## Lifecycle

1. From a project, the user can propose a saved `preference` requirement or a
   rejected-product judgment as a candidate. Both actions capture the source
   project revision, typed value, category scope and rationale. Must-haves and
   constraints cannot be promoted through the requirement action. A rejection
   remains local until the user explicitly creates a candidate from it.
2. The profile shows the candidate and its source. Acceptance is a separate,
   revision-checked action. A stale source is marked stale and must be reviewed
   from the current project before another candidate can be accepted.
3. Accepted preferences are editable soft preferences. The user can revoke or
   reactivate them. Revocation removes them from future suggestions; it does not
   rewrite earlier research snapshots or remove a requirement the user already
   chose to keep in a project.
4. A project must opt in to suggestions. An applicable preference is copied to
   that project's requirements only after the user selects **Add to
   requirements**. The requirement stores the preference ID, revision and scope
   so research and assistant snapshots can explain where it came from.
5. The current project requirement kind determines authority: a profile-origin
   copy stays soft while its kind is `preference`, and becomes hard only if the
   user changes it to `must_have` or `constraint`. Turning off project
   suggestions leaves requirements already copied into that project unchanged.

Preferences are owner-scoped and category-scoped. The profile and each project
have independent reuse switches. At most 20 applicable preferences are returned
to one project at a time; profiles allow at most 100 active preferences and 100
pending candidates. Profile reads prioritize pending candidates before resolved
history so history cannot hide unresolved work. Revocation frees an active slot
while retaining preference rows and provenance references. Monetary intent is
explicit in the preference contract; monetary preferences require a three-letter
currency unit and cannot use the all-categories scope.
Structured monetary values must be decimal strings with a supported ISO currency;
qualitative money preferences still retain a supported currency and category scope.

Revocation and reuse-off stop new profile suggestions and application. An already
applied project copy remains independent local context for that project until the
user edits or removes it; profile changes do not rewrite that copy or historical
run snapshots.

No automatic extraction or acceptance runs. Personal AI memory retrieval,
proposal and retraction controls are unavailable because the checked upstream
contract has no user-scoped memory CRUD/proposal API. This module does not send
shopping data to that service.
