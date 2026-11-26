# Procedure and resource search — QA checklist

**Scope:** Read-only catalog search in Munnin's MCP and HTTP APIs.

## Happy path on the target build

- [ ] **Manual, client discovery:** Connect your MCP client to the target build.
  Call `search_procedure(query="UPDATE_memory")`. Expect `update-memory` with a
  title and description. Pass its name to `read_procedure` and check that it opens.
- [ ] **Manual, HTTP parity:** Call `search_resources(query="between files")` and
  `GET /api/search/resources?query=between%20files` against that same instance
  (use the normal bearer token in hosted mode). Both should return the same one
  row for `copy-lines`, whose **title**, not name, contains that phrase.

## Automated coverage

| Risk | Test |
|---|---|
| One interface matches descriptions, reorders words or results, accepts an empty phrase, or returns different fields | `test_catalog_search_matches_across_mounted_faces` |
| New HTTP routes accept anonymous requests in token mode | `test_catalog_search_matches_across_mounted_faces` |
| A search tool is advertised with no content, or without its read-only hint | `test_content_tools_present_only_with_content`, `test_the_hints_say_what_each_tool_does` |

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
