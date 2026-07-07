# Security Policy

## Supported Versions

Security fixes are applied to the latest revision of the default branch. Older commits, forks, and locally modified copies are not separately supported.

## Reporting a Vulnerability

Please report suspected vulnerabilities through [GitHub Private Vulnerability Reporting](https://github.com/shinan7/audit-bid-technical-response/security/advisories/new).

Do not disclose vulnerability details in a public Issue, Discussion, pull request, or commit. If private vulnerability reporting is temporarily unavailable, open a public Issue containing only a request for private contact and no technical or sensitive details.

Include the following when it is safe to do so:

- affected file, component, and revision;
- expected security boundary and observed behavior;
- minimal reproduction using synthetic, non-sensitive data;
- impact, prerequisites, and suggested mitigation;
- whether the issue is already public or known to another party.

Never upload real procurement documents, bid documents, generated audit reports, credentials, API keys, personal information, internal paths, or customer data. Redact logs and screenshots before submitting them.

## Security Scope

Reports are especially useful when they concern:

- prompt injection or instructions embedded in untrusted documents;
- unintended file, tool, command, or network access;
- disclosure of source documents, extracted images, reports, or unrelated local data;
- malicious DOCX/ZIP or PDF files causing excessive CPU, memory, disk, or processing time;
- unsafe Microsoft Word automation or exporting the wrong document;
- dependency, parsing, path-handling, or output-permission weaknesses.

Reports about ordinary audit accuracy, unsupported file formats, or procurement-domain disagreements are generally product-quality issues rather than security vulnerabilities unless they cross a security boundary.

## Response and Disclosure

The maintainer aims to acknowledge a complete report within 7 calendar days and provide an initial status within 14 calendar days. These are targets rather than service-level commitments.

Please allow reasonable time for investigation and remediation before public disclosure. The maintainer will coordinate disclosure timing and credit with the reporter when appropriate.

## Safe Research

Use only files and systems you own or are explicitly authorized to test. Keep tests bounded, avoid customer data, and stop before causing service disruption, data loss, or access to unrelated information.
