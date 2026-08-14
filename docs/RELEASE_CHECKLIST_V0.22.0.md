# Release Checklist v0.22.0

## Contract

- [ ] controlled integration passed != real data approved
- [ ] real-data trial review eligible != real-data use authorized
- [ ] Local RAG integration != production runtime activation
- [ ] synthetic/controlled fixtures only; no customer, company, person, or project data
- [ ] no read of `C:\AI_Local_RAG` or `C:\AI_Restricted`
- [ ] no actual credential/token, external API, cloud, private LAN, or HTTP
- [ ] no actual persistent vector DB, filesystem persistence, production registry write,
      runtime activation, or runtime switch
- [ ] external network count = 0; HTTP count = 0; cloud count = 0
- [ ] external API count = 0; credential use count = 0; token use count = 0
- [ ] persistent vector write count = 0; production registry write count = 0
- [ ] real data access count = 0

## Validation

- [ ] `python -m pytest`
- [ ] v0.22 targeted tests and v0.21–v0.10 regressions
- [ ] compatibility/profile integration and HTTP security tests
- [ ] CLI help and `python -m compileall -q src tests`
- [ ] workflow YAML parse and `git diff --check`
- [ ] secret/credential/real-data/URL/IP/absolute-path scan reviewed
- [ ] GitHub Actions Python 3.11 and 3.12 pass
- [ ] Draft PR only; no merge, tag, or Release
