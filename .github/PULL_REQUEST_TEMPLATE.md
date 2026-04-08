## Summary

## Risk Assessment
- [ ] Low risk (UI/tests/docs/config only)
- [ ] Medium risk (API/service/data model changes)
- [ ] High risk (migrations/auth/billing/AI/infra or >500 lines)

## Validation
- [ ] Lint passed
- [ ] Unit/integration tests passed
- [ ] Relevant regression tests passed
- [ ] Preview smoke checks passed

## Reviewer Checklist
### L1 + L2
- [ ] Logic is correct
- [ ] Tenant isolation is preserved
- [ ] Feature flags/entitlements applied where required
- [ ] No secrets or sensitive data exposed
- [ ] Tests cover the change

### L3 (high-risk only)
- [ ] Auth/session handling reviewed
- [ ] Billing/security implications reviewed
- [ ] Migration safety reviewed (if applicable)

## Cross-Browser QA (required before merge)
- [ ] Chrome -- verified in browser
- [ ] Firefox -- verified in browser
- [ ] Edge -- verified in browser
- [ ] Safari -- verified in browser

## Screenshots / Evidence (if UI)
