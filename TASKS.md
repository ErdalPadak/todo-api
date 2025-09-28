# TASKS (küçük, net)
- [ ] 1) /tasks listesinde hatalı kayıtları **atla & logla** (500 atma).
      Kabul: smoke_e2e PASS; /tasks?limit=50 200 OK; logda atlanan id'ler görünsün.
- [ ] 2) **DELETE /tasks/{id}** ekle (200/204).
      Kabul: silinen id GET ile 404; metrics güncellenir; smoke_e2e PASS.
- [ ] 3) GitHub Actions (Windows runner) ile **scripts/smoke_e2e.ps1** çalışsın.
      Kabul: PR'da smoke PASS değilse merge bloklanır.
