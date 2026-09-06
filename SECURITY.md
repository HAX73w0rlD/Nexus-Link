# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by:

1. **Do NOT** open a public issue
2. Send a detailed description to the maintainer via GitHub Issues (mark as private)
3. Include steps to reproduce the issue
4. Wait for acknowledgment and fix

## Security Best Practices

When deploying Nexus-Link:

- **Never commit** your `.env` file with real credentials
- Use environment variables for all secrets
- Restrict `ALLOWED_USER_ID` to trusted users only
- Keep your API keys secret
- Regularly update dependencies
- Use HTTPS for all API endpoints in production
