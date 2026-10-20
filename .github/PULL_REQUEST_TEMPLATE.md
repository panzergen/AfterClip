## What this changes

<!-- A short description of the change and the problem it solves. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would change existing behaviour)
- [ ] Documentation only
- [ ] Build, CI or packaging only

## Checklist

- [ ] The change is covered by tests, and new behaviour has a test that fails without it
- [ ] `python -m pytest -q` passes
- [ ] `python -m pytest -m ui -q` passes
- [ ] `python -m ruff check src tests packaging` passes
- [ ] `python -m ruff format --check src tests packaging` passes
- [ ] Documentation under `docs/` is updated for any user-visible behaviour change
- [ ] No API keys, transcripts, private media or personal paths are included

## Privacy and network behaviour

- [ ] This change does not send data to any cloud provider
- [ ] If it does, it goes through `app/infrastructure/cloud_policy.py` and the
      existing consent gate is respected

<!--
Anything a reviewer should know: trade-offs, alternatives you considered,
follow-up work, or areas you are unsure about.
-->
