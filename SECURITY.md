# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

Chimera is pre-1.0. Security fixes are applied to the latest release.

## Reporting a Vulnerability

**Do not open a public issue.** Instead, email:

**security@totalwindup.com**

You will receive a response within 48 hours. Please include:

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential mitigations you've identified

We follow a coordinated disclosure process:

1. Acknowledge receipt within 48 hours
2. Confirm the vulnerability and assess severity within 5 business days
3. Develop and test a fix
4. Release the fix and publish an advisory
5. Credit the reporter (unless they request anonymity)

## Scope

- The Chimera deliberation engine, API server, CLI, MCP server, and web UI
- The `chimera.yaml` configuration format
- The Chimera REST API and OpenAI-compatible endpoint

### Out of Scope

- Model provider security (DeepSeek, OpenRouter, Z.AI, Anthropic, etc.)
- LiteLLM security issues (report to [BerriAI/litellm](https://github.com/BerriAI/litellm))
- Credential exposure from user misconfiguration (keys in committed `chimera.yaml`)
