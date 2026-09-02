# Distribution tooling

- Use only Python's standard library on GitHub-hosted runners.
- Packaging must be deterministic and include only `.py` and `.json` integration files.
- Validation must fail closed on version drift, private URLs, unexpected image names, or
  credential-like content.
- Do not add scripts that mutate Home Assistant or physical HVAC state.

