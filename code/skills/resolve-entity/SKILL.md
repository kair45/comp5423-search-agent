---
name: resolve-entity
description: Separate competing people, works, places or institutions when several candidates have similar names or match only part of the clues. Load when the search state shows conflicting identities, dates or roles.
---

List the competing candidates and pick one constraint with different predicted values, preferably a dated event, affiliation, or distinctive role from the question. Query that constraint with the candidate spelling; inspect the original words around the match.

Mark each candidate supported, contradicted or unknown for that constraint. A missing mention is unknown. Keep the supporting or conflicting evidence ID in the next tool call; remove a candidate only on a direct contradiction. Do not merge biographies just because the names match.

If two candidates survive, search a second independent attribute. Stop when the surviving identity also supports the attribute requested in the question. Preserve significant counterevidence in the state.
