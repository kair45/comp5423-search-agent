---
name: follow-clues
description: Reconstruct a chain when the question asks about an attribute of an unidentified intermediate person, item, organization or event. Load when the next query depends on an entity that must first be discovered.
---

Write down the requested answer type and the shortest missing link between the known clue and that answer. Start with the rarest independently searchable clue. Search for the relation as well as its endpoints.

Read the passage in context. Accept a bridge only when its words support the relation: sharing a page is insufficient. Retain its evidence ID and the discovered spelling. In the next tool call, pass the bridge entity, the remaining relation and an updated unresolved list. If a source contradicts the bridge, withdraw the candidate and return to the last supported link.

Stop once the last passage supplies the requested attribute and the chain connects it back to the question. Return the attribute at the requested level of detail.
