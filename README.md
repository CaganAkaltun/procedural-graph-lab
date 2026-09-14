# PG-Lite — Procedural Graph yeniden uygulaması + iyileştirme iskeleti

arXiv:2609.09153 ("Procedural Graphs: Self-Evolving Execution Structures for LLM Agents")
makalesinin açık, çalışır bir yeniden uygulaması ve eşlik eden raporda önerilen
iyileştirmelerin (PG-Lite) deney altyapısı.

Makalenin kodu yayınlanmadığı için bu iskelet sıfırdan yazıldı. Bağımlılık yok
(saf Python 3.10+ stdlib); sahte LLM ile uçtan uca duman testi geçiyor.

```bash
python scripts/smoke_test.py       # API anahtarı gerekmez, her şeyi doğrular

python scripts/run_ablation.py --arms A0 A1 A2 A3 A4 A5 \
       --episodes 60 --graph graphs/toy_correct.json \
       --out results/demo.json --label "ilk-deneme"

python scripts/run_evolution.py --rounds 4 --train 24 --val 12 --init expert

python dashboard/server.py         # http://127.0.0.1:8777 — canlı izleme
```

Sıfırdan kurulum (Python kurulumundan Claude Code prompt'larına kadar):
**`KURULUM_VE_UYGULAMA_REHBERI.md`**.

**Güncel durum ve sıradaki adımlar için:** **`PROGRESS.md`** — plana göre ne
tamamlandı, plandan sapmalar (ör. LLM sağlayıcısı Gemini), ve devam eden/yeni
bir ajanın önce okuması gereken notlar orada tutuluyor.

## Neden bu iskelet?

| Rapordaki fikir | Nerede uygulandı |
|---|---|
| **I1** Grafsız danışman kontrolü | `pg/guidance.py` → `mode="advisor"` (kol **A1**) |
| **I2** Seçici + önbellekli rehberlik | `pg/guidance.py` → `GuidanceConfig.selective` (kol **A3**) |
| **I3** SoftMatch lokalizasyon | `pg/localize.py` → `mode="soft"` kaskadı (kol **A4**) |
| **I4** Guard-PG (sert ön-koşullar) | `pg/graph.py::Edge.guard` + `pg/runner.py::_check_guards` (kol **A5**) |
| **I5** Kenar-düzeyi kredi ataması | `pg/graph.py::credit_report`, refiner prompt'una eklenir |
| **I6** Sağlam doğrulama kapısı | `pg/stats.py::sequential_gate`, `pg/evolve.py` (CRN + eşli bootstrap) |
| Pi harness entegrasyonu | `pi-extension/pg-pi.ts` |
| Canlı izleme | `pg/telemetry.py` + `dashboard/` (bağımlılıksız) |

## Kollar

| Kol | Yapılandırma | Ne test eder |
|---|---|---|
| A0 | rehberlik yok | alt sınır (Vanilla ReAct) |
| A1 | grafsız danışman, her adım | **kazanç graftan mı, ek LLM çağrısından mı?** |
| A2 | PG alt-graf + üretici, her adım | makalenin yöntemi (replikasyon) |
| A3 | A2 + seçici/önbellekli | maliyet düşürme |
| A4 | A3 + SoftMatch lokalizasyon | lokalizasyon sağlamlığı |
| A5 | A4 + guard'lar | yumuşak vs sert kısıt |
| FULL_RAW / FULL_GEN | Tablo 3'ün diğer satırları | kapsam ablasyonu |

Tüm kollar **aynı görev listesinde** koşar → eşli bootstrap ve McNemar geçerli.

## Dizin yapısı

```
pg/graph.py      ProceduralGraph, Edge.guard, ΔG uygulama, yapısal doğrulama,
                 döngü onarımı, yerel/tam serileştirme, kenar kredi raporu
pg/localize.py   Match(): exact → typed → semantic → sticky kaskadı + telemetri
pg/guidance.py   rehberlik modları, seçici tetikleme, önbellek, istatistik
pg/llm.py        LLM arayüzü, rol bazlı token/maliyet muhasebesi, MockLLM
pg/runner.py     ReAct döngüsü, guard uygulaması, epizot/kol koşumu
pg/refiner.py    refiner prompt'u, ΔG ayrıştırma, ret belleği (imza eşleme)
pg/evolve.py     Algoritma 1 + iki aşamalı sağlam kapı, retained/last ayrımı
pg/stats.py      eşli bootstrap, McNemar, Holm-Bonferroni, sequential_gate
pg/telemetry.py  JSONL koşum günlüğü (dashboard'un veri kaynağı)
dashboard/       stdlib HTTP sunucusu + tek sayfalık canlı pano
pg/envs/toy.py   sıralama kısıtlı oyuncak ortam + bozuk/doğru uzman grafları
graphs/          örnek graflar (toy + Pi için kodlama grafı)
pi-extension/    Pi coding agent uzantısı (TypeScript)
```

## Gerçek deneye geçiş — üç adım

**1) LLM'i bağlayın.** `pg/llm.py` içindeki `AnthropicLLM.complete()` gövdesini
doldurun (docstring'de örnek var). `temperature=0` tutun ve her çağrıda
`self.tracker.record(role, prompt, text)` çağırın — rol bazlı token ayrımı
Pareto analizinin temeli.

**2) Ortam sarmalayıcısı yazın.** `pg/runner.py::Env` protokolünün üç metodunu
uygulayın:

```python
class AlfWorldEnv:
    description: str            # görev metni
    def reset(self, task_id) -> str: ...
    def actions(self) -> list[str]: ...
    def step(self, action) -> tuple[str, bool]: ...   # (gözlem, bitti mi)
    def score(self) -> float: ...
```
Sonra `scripts/run_ablation.py::_register_envs()` içine kaydedin.

**3) Grafı verin.** Ya `graphs/*.json` içinde elle yazın (uzman prior'ı), ya da
`ProceduralGraph.skeleton()` ile başlayıp `pg/evolve.py::evolve()` çalıştırın
(makalenin Mode 5'i). Kenar formatı:

```json
{"source": "Extract", "target": "Verify", "relation": "LEADS_TO",
 "condition": "bir aday cevap çıkarıldı",
 "guidance": "Cevabı kanıtla karşılaştırarak doğrula.",
 "pitfalls": "Doğrulanmamış cevabı asla gönderme.",
 "guard": {"kind": "require_before", "tool": "Submit", "requires": ["Verify"]}}
```

## Dashboard

```bash
python dashboard/server.py                       # http://127.0.0.1:8777
python dashboard/server.py --port 9000 --runs /yol/runs
```

Sıfır bağımlılık (sadece Python stdlib), çevrimdışı çalışır, 2 sn'de bir
yenilenir. `runs/*.jsonl` dosyalarını okur; koşum sırasında açıp kapatabilirsiniz.

Panolar: özet KPI'lar · kol tablosu (ilerleme, başarı, token, rehberlik çağrısı,
önbellek isabeti, **lokalizasyon isabeti**, guard blokları, başarı/1k token) ·
kümülatif öğrenme eğrisi · **maliyet–performans Pareto** · lokalizasyon aşama
dağılımı (exact/typed/semantic/sticky/none) · evrim turları ve kapı kararları ·
canlı olay akışı.

Kendi kodunuzdan telemetri yazmak için:

```python
from pg.telemetry import RunLogger
logger = RunLogger("runs", label="deneyim")
logger.run_start({"model": "..."} )
run_arm(..., logger=logger, arm_id="A4")
logger.run_end()
```

## Guard DSL

| kind | alanlar | anlamı |
|---|---|---|
| `require_before` | `tool`, `requires[]`, (Pi'de `pattern`) | araç yalnızca listedeki düğümler ziyaret edildikten sonra çalışabilir |
| `forbid_repeat` | `tool` | araç arka arkaya iki kez çalışamaz |
| `forbid_pattern` (Pi) | `tool`, `pattern`, `reason` | komut regex'e uyarsa blokla |

Guard tetiklendiğinde araç çalıştırılmaz; ajana onarım mesajı gözlem olarak
döner. `EpisodeResult.guard_blocks` ve `false_blocks` sayaçlarını raporlayın —
aşırı kısıtlamanın maliyetini göstermek, katkının dürüstlüğü açısından şart.

## Pi uzantısı

```bash
cp pi-extension/pg-pi.ts ~/.pi/agent/extensions/
export PG_GRAPH=$PWD/graphs/coding_pg.json PG_SELECTIVE=1 PG_GUARDS=1
pi          # oturum içinde /pg-stats ve /pg-reload komutları
```

Kanca eşlemesi: `context` (her LLM çağrısından önce rehberlik enjeksiyonu),
`tool_call` (guard'lar — bloklayabilir), `tool_execution_end` + `turn_end`
(trajektori logları), `session_shutdown` (telemetri dökümü). Loglar
`PG_LOG` yolundaki JSONL dosyasına yazılır ve doğrudan `pg/refiner.py`'ye
beslenebilir.

## Duman testinin gösterdiği (örnek çıktı)

```
A0 vanilla ReAct            success=0.050  tokens= 45770  guid_calls=  0
A1 graph-free advisor       success=0.050  tokens=108000  guid_calls=294
A2 PG (paper replication)   success=0.750  tokens=174225  guid_calls=322
A4 PG-Lite (soft+selective) success=0.750  tokens=165046  guid_calls=305
A5 PG-Lite + guards         success=0.850  tokens=188079  blocks=17

A2 - A1: diff=+0.700 CI[+0.583,+0.817]  boot_p=0.0000   (graf gerçekten katkı yapıyor)
A5 - A4: diff=+0.100 CI[+0.033,+0.183]  boot_p=0.0040   (guard'lar ek katkı)

Evrim (bozuk uzman prior'ından): 0.083 → 0.750;
  round 3 zararlı düzenleme → early_reject; round 4 aynı düzenleme → duplicate
```

Bu sayılar **sahte LLM** iledir; yalnızca boru hattının doğru çalıştığını
gösterir, bilimsel bir iddia taşımaz.

## Lisans / atıf

İskelet MIT. Fikirlerin kaynağı: Lu, Chen, Wu, Arık — *Procedural Graphs:
Self-Evolving Execution Structures for LLM Agents*, arXiv:2609.09153 (2026).

## Kontrol grafları ve uyum ölçümü (nihai plan)

```python
from pg.controls import shuffle_topology, mine_graph
from pg.conformance import check, compliance_vs_outcome

g_shuf  = shuffle_topology(g_llm, seed=1)        # C3 kontrolü: topoloji bozuk, metin aynı
g_mined = mine_graph(successful_action_seqs)     # C6 kontrolü: betimleyici madenci, $0

print(compliance_vs_outcome(g_llm, action_seqs, scores, localizer))
# -> fitness / precision / uyum-başarı farkı: "ajan grafı gerçekten takip ediyor mu?"
```

Uçtan uca plan: **`UYGULAMA_PLANI_FINAL.md`** (koşullar C0–C6, fazlar,
Claude Code prompt'ları, istatistik, bütçe, kill kriterleri).
