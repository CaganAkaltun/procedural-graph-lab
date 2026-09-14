# PG-Probe — Nihai Uygulama Planı (uçtan uca)

**Durum:** Bu doküman, önceki üç dokümanın (ilk rapor, katı değerlendirme, hibrit
eleştirisi) hayatta kalan kısımlarını tek bir uygulanabilir plana indirger.
Çelişki hâlinde **bu doküman geçerlidir**.

**Tek cümlelik tez:**
> Prosedürel Graf'ın kazancı grafın *topolojisinden* mi geliyor, yoksa
> "her adımda alana özgü bir hatırlatma enjekte etmek"ten mi? Ve ajan grafı
> gerçekten takip ediyor mu?

Bu, bir replikasyon değil **mekanizma çalışmasıdır**. Bu ayrım plan boyunca
korunmalıdır: makalenin mutlak sayılarını asla tartışmıyoruz, yalnızca kendi
kollarımızı birbirine karşı ölçüyoruz.

---

## 0. Önceki planlardan ne değişti

| Değişiklik | Gerekçe |
|---|---|
| ALFWorld → **τ-bench retail** | kurulum acısı + tavan etkisi; τ-bench'te tavan yok ve politika/sıralama kısıtı var |
| 5 kol → **7 koşul** ama **tek benchmark** | eksik kontroller eklendi, benchmark sayısı azaltıldı |
| Guard'lar, kenar kredisi, popülasyon evrimi, Pi izi | **kesildi** (katı değerlendirme §2) |
| BAI kapısı, FSM alt sistemi, kaskad yönlendirme, DECLARE, BT | **kesildi** (hibrit eleştirisi §4–§6) |
| Süreç madenciliği: *üretici* → **kontrol kolu + ölçüm aracı** | madencilik betimleyicidir, buyurgan nesne üretemez |
| Gerçek API ile 8–10 turlu evrim | **kesildi**; yerine tek seferlik offline refiner (≈$1) + $0 simülasyon |
| Yeni: **uyum (conformance) ölçümü** | makalenin hiç sormadığı soru; sıfır ek epizot |

---

## 1. Dört yanlışlanabilir iddia

Her biri sıfır sonucunda da bilgilendirici. Koşumdan önce `preregistration.md`'ye
yazılıp commit'lenecek.

**İ1 — Topoloji taşıyor mu?** `C4 (gerçek graf) − C3 (karıştırılmış graf) > 0`.
*Sıfır sonucu:* topoloji dekoratif; PG = durum-indeksli hatırlatma metni. Güçlü
negatif bulgu.

**İ2 — Ek LLM çağrısı mı yeterli?** `C4 − C2 (grafsız danışman) > 0` ve
`C4 − C1 (sabit jenerik metin) > 0`.
*Sıfır sonucu:* kazanç "adım başına bir eleştirmen" etkisi.

**İ3 — Rehberlik üretimi gerekli mi?** `C5 (seçici/önbellekli)`, `C4`'ün
rehberlik çağrılarının ≤%40'ıyla, **±5 puan eşdeğerlik marjı** içinde (TOST).
*Doğrulanırsa:* maliyet ekseninde Pareto iyileştirmesi.

**İ4 — LLM refiner, ucuz bir madenciye göre ne katıyor?** `C4 − C6 (madenlenmiş
graf)`.
*C6 ≈ C4:* refiner gereksiz, aynı trace'lerden deterministik olarak $0'a
üretilebiliyor. *C6 ≪ C4:* refiner'ın "günlükte olmayanı icat etme" yeteneği
gerçek ve **ölçülmüş** — bu makalenin lehine bir bulgudur ve yine de yenidir.

**Ek teşhisler (iddia değil, yorumlama anahtarı):**
- **Uyum:** fitness / precision / uyum-başarı korelasyonu.
- **Lokalizasyon isabet oranı** (makalenin hiç vermediği sayı).
- **Kapı güç analizi** (simülasyon, $0, zaten koşuldu).
- **Prompt önbelleği:** rehberlik yerleşiminin gerçek dolar maliyetine etkisi.

---

## 2. Kapsam — içeride / dışarıda

**İÇERİDE:** τ-bench retail (birincil) · HotpotQA 150 görev tek tohum (negatif
kontrol) · tek model · 7 koşul · uyum ölçümü · lokalizasyon telemetrisi ·
önbellek muhasebesi · kapı simülasyonu · eşli istatistik + TOST.

**DIŞARIDA (bir daha açılmayacak):** guard'lar · kenar kredisi · popülasyon
evrimi · BAI kapısı · FSM alt sistemi · kaskad yönlendirme · DECLARE/LTL ·
Behavior Tree · Pi/kodlama izi · ALFWorld · GDPval · EnterpriseArena ·
7 baseline'ın yeniden uygulanması · gerçek API ile çok turlu evrim ·
dashboard'a yeni özellik.

> Bu listeye bir şey geri girmek isterse: hangi iddiayı test ettiğini ve kaç
> dolara mal olduğunu yazmadan girmesin.

---

## 3. Sistem tasarımı

### 3.1 Graf kaynakları (dördü de aynı trace havuzundan türer)

| Graf | Nasıl üretilir | Maliyet | Rolü |
|---|---|---|---|
| `G_expert` | τ-bench retail **politika dokümanından** elle yazılır, 10–14 düğüm | 1 saat insan | başlangıç prior'ı |
| `G_llm` | `G_expert` + bootstrap trace'leri → **tek seferlik** offline refiner çağrısı (makalenin Mode 2'si) | ~$1 | **ana PG koşulu (C4)** |
| `G_mined` | aynı bootstrap trace'lerinin **başarılı** olanlarından `mine_graph()` | **$0** | kontrol (C6) |
| `G_shuf` | `G_llm`'in `shuffle_topology()` ile yeniden bağlanmış hâli | **$0** | kontrol (C3) |

Kritik nokta: `G_llm`, `G_mined` ve `G_shuf` **aynı girdiden** türer. Bu,
karşılaştırmayı adil kılan şeydir.

### 3.2 Yedi koşul

| Kod | Rehberlik kaynağı | Adım başına LLM çağrısı | Test ettiği |
|---|---|---|---|
| **C0** | yok | 0 | taban |
| **C1** | sabit jenerik metin (token-eşlenmiş) | **0** | "herhangi bir hatırlatma" etkisi |
| **C2** | trajektori danışmanı, graf yok | 1 | ek çağrının katkısı |
| **C3** | `G_shuf` alt-graf, üretici | 1 | **topolojinin katkısı** |
| **C4** | `G_llm` alt-graf, üretici (makalenin yöntemi) | 1 | tam sistem |
| **C5** | `G_llm`, seçici + önbellekli | ~0.3 | maliyet ekseni |
| **C6** | `G_mined` alt-graf, üretici | 1 | refiner vs madenci |

C1'in token bütçesi C2/C4'ün ortalama rehberlik uzunluğuna eşitlenir — pilotta
ölçülür, sonra sabitlenir.

### 3.3 Kod durumu

**Hazır (test edildi):** `pg/graph.py` · `pg/localize.py` · `pg/guidance.py` ·
`pg/runner.py` · `pg/refiner.py` · `pg/evolve.py` · `pg/stats.py` ·
`pg/telemetry.py` · `dashboard/` · `scripts/gate_power_analysis.py` ·
**`pg/conformance.py` (yeni)** · **`pg/controls.py` (yeni)**.

**Yazılacak:** `pg/envs/taubench.py` · `pg/envs/hotpotqa.py` ·
`pg/llm.py::AnthropicLLM` (önbellek metrikleriyle) · `pg/guidance.py` içine
`mode="fixed"` (C1) · `scripts/build_graphs.py` · `scripts/make_report.py`
(TOST dahil) · `--seed` ve `--max-cost` bayrakları.

Yaklaşık **6–8 gün** yeni kod. Yeni kütüphane bağımlılığı: yalnızca `anthropic`
ve τ-bench'in kendi paketi. **pm4py yok** — uyum ölçümü bağımlılıksız yazıldı.

---

## 4. Faz planı

### Faz 0 — Hazırlık (2–3 gün)

1. `KURULUM_VE_UYGULAMA_REHBERI.md` §0–§2'yi uygula (Python, venv, iskelet,
   duman testi, dashboard). ALFWorld adımlarını **atla**.
2. τ-bench'i kur, retail alanının 115 görevini listele, deterministik
   `task_ids(n, seed)` fonksiyonunu doğrula.
3. `AnthropicLLM`'i bağla (Prompt P1). `check_llm.py` gerçek token + **önbellek
   token** sayılarını basmalı.
4. `G_expert`'i elle yaz: τ-bench retail politika dokümanını oku, 10–14 düğümlük
   bir prosedür grafı çıkar (`graphs/taubench_expert.json`).

**Çıkış kriteri:** `python scripts/run_ablation.py --env taubench --arms C0 C4
--episodes 3` hatasız koşuyor ve dashboard'da görünüyor.

### Faz 1 — Bootstrap ve graf üretimi (2 gün)

1. **Bootstrap koşumu:** C0 (rehberlik yok) ile 40 eğitim görevi koş. Bu,
   üç grafın da girdisi olan trace havuzudur. (~$5–8)
2. `scripts/build_graphs.py` çalıştır:
   - `G_llm` = tek seferlik refiner (`G_expert` + trace'ler) → yapısal doğrulama
   - `G_mined` = `mine_graph(başarılı trace'ler)`
   - `G_shuf` = `shuffle_topology(G_llm, seed=1)` → geçerlilik kontrolü
3. Dördünün de istatistiklerini raporla (düğüm/kenar/derece dağılımı). Kenar
   sayıları kabaca benzer olmalı; `G_mined` çok şişerse `min_freq` yükselt.

**Çıkış kriteri:** dört graf `validate()` geçiyor ve kenar sayıları 2× içinde.

> **Dikkat:** `G_mined` yalnızca gözlenen davranışı içerir. Bu bir kusur değil,
> C6'nın **tanımıdır**. Raporda böyle yazın.

### Faz 2 — Pilot ve bütçe kapısı (2 gün)

20 görevlik sabit alt kümede **yedi koşulu da** koş.

Pilotta ölçülecek ve karar verilecekler:

| Ölçüm | Karar |
|---|---|
| Epizot başına gerçek dolar | toplam bütçeyi hesapla → **1 mi 2 mi tohum?** |
| Lokalizasyon isabet oranı | <%50 ise bu **manşet bulgu** olur, raporun yapısı değişir |
| C4 − C0 farkı | <3 puan ise etki küçük demektir: ya n artır ya benchmark değiştir (karar ver, sürükleme) |
| C2/C4 ortalama rehberlik uzunluğu | C1'in sabit metin bütçesini buna eşitle ve **dondur** |
| Önbellek isabeti | rehberlik yerleşimi prompt önek önbelleğini kırıyor mu? |

**Kill kriteri:** pilotta hiçbir koşul C0'dan ≥3 puan ayrışmıyorsa, tam koşuma
para harcamayın. Bunun yerine uyum ölçümü + kapı simülasyonu + lokalizasyon
telemetrisini bir **analiz notu** olarak yazın. Bu da geçerli bir çıktıdır.

### Faz 3 — Ana koşum (3–5 gün, çoğu gözetimsiz)

```bash
for SEED in 1 2; do
  python scripts/run_ablation.py --env taubench \
      --arms C0 C1 C2 C3 C4 C5 C6 --episodes 115 --seed $SEED \
      --provider anthropic --max-cost 60 --resume \
      --out results/tau_s$SEED.json --label "tau-seed$SEED"
done

# negatif kontrol: PG'nin işe yaramadığı bilinen rejim
python scripts/run_ablation.py --env hotpotqa \
    --arms C0 C2 C3 C4 --episodes 150 --seed 1 \
    --provider anthropic --max-cost 15 --out results/hotpot.json
```

Tüm koşullar **aynı görev listesini ve aynı tohumu** kullanır (ortak rastgele
sayılar). Bu, eşli istatistiğin geçerlilik şartıdır.

### Faz 4 — Analiz ve yazım (4–5 gün)

1. `scripts/make_report.py` → kol tablosu, eşli karşılaştırmalar, Holm
   düzeltmesi, TOST, SVG Pareto.
2. **Uyum analizi:** her rehberlikli kol için `compliance_vs_outcome()`.
   Yorumlama anahtarı:
   - yüksek uyum + yüksek başarı → graf gerçekten yönlendiriyor
   - **düşük uyum + yüksek başarı → kazanç topolojiden gelemez** (İ1'i destekler)
   - yüksek uyum + düşük başarı → graf takip ediliyor ama yanlış
3. Kapı güç analizi çıktısını rapora ekle (zaten hazır).
4. Sunum: ana rapordaki 16 slaytlık iskeleti bu sonuçlarla güncelle.

---

## 5. Claude Code prompt'ları (güncel, 7 adet)

Her birinden sonra kabul kriterini doğrula ve commit'le. Eskisi olan §6
listesindeki 6.3 (ALFWorld), 6.5, 6.6, 6.8'i **kullanma**.

### P1 — Gerçek LLM + önbellek muhasebesi
```
pg/llm.py içindeki AnthropicLLM sınıfını tamamla.

- anthropic SDK, lazy client, temperature=0, imza değişmesin.
- Gerçek token sayımını API yanıtındaki usage alanından al:
  input_tokens, output_tokens VE cache_creation_input_tokens,
  cache_read_input_tokens. UsageTracker'a rol bazında ve önbellek
  türü bazında ayrı ayrı yaz; maliyeti önbellek fiyatlandırmasıyla hesapla.
- 429/5xx için jitter'lı üstel geri çekilme (max 5 deneme).
- Prompt yapısını iki modda destekle: guidance bloğu prompt'un SONUNDA
  (önek önbelleği korunur) veya BAŞINDA (önek kırılır). Bir bayrakla seçilsin;
  hangisinin gerçek maliyeti düşürdüğünü ölçeceğiz.

scripts/check_llm.py yaz: iki modu da dener, rol bazlı token, önbellek
isabeti ve tahmini maliyeti yazdırır.

Sonra python scripts/smoke_test.py çalıştır ve geçtiğini göster.
```
**Kabul:** `check_llm.py` iki yerleşim için farklı önbellek isabeti raporluyor.

### P2 — τ-bench sarmalayıcısı
```
pg/envs/taubench.py yaz: pg/runner.py'deki Env protokolünü uygulayan
TauBenchEnv (retail alanı).

- tau-bench paketini kullan; kullanıcı simülatörü için ayrı ve DAHA UCUZ bir
  model kullanılabilsin (parametre olarak).
- reset(task_id) -> ilk gözlem; description özelliği görev + politika özeti.
- actions() mevcut araç adlarını döndürsün.
- step(action) -> (gözlem, bitti_mi); araç hatalarını ham metin olarak ver.
- score() Pass@1 (final veritabanı durumu hedefle eşleşiyor mu) -> 1.0/0.0.
- TauBenchEnv.task_ids(n, seed) deterministik alt küme.
- Kullanıcı simülatörünün token'ları UsageTracker'a "user_sim" rolüyle
  ayrı yazılsın (maliyet analizinde ajan maliyetinden ayırmamız şart).

scripts/run_ablation.py::_register_envs()'e kaydet, 3 epizotluk mock koşumla
test et.
```
**Kabul:** 3 epizot hatasız; `user_sim` token'ları ayrı raporlanıyor.

### P3 — C1 sabit rehberlik modu + kol kayıtları
```
pg/guidance.py'ye mode="fixed" ekle: grafa da LLM'e de bakmadan, sabit bir
metni her adımda enjekte eder. Metin bir dosyadan okunsun
(graphs/fixed_guidance.txt) ve token uzunluğu yapılandırılabilir olsun.

ARMS sözlüğünü yeniden düzenle: C0..C6 kodlarıyla, plandaki tanımlara birebir
uyacak şekilde (C0 none, C1 fixed, C2 advisor, C3/C4/C6 subgraph_gen farklı
graflarla, C5 subgraph_gen+selective). Graf dosyası kol tanımının parçası olsun,
CLI'da --graph tek tek verilmesin.

Eski A0-A5 kodlarını geriye dönük uyumluluk için alias olarak bırak.
smoke_test'i güncelle ve geçtiğini göster.
```
**Kabul:** `--arms C0 C1 C2 C3 C4 C5 C6` tek komutla, her kol doğru grafla koşuyor.

### P4 — Tohum, bütçe, devam
```
Üç şey ekle:
1. --seed: görev sırasını ve ortam tohumunu belirler; TÜM kollar aynı tohumu
   kullanır (ortak rastgele sayılar). Tohum sonuç dosyasına yazılsın.
2. --max-cost: her epizottan sonra kontrol, aşılırsa temiz dur, telemetriye
   note("budget_exceeded") yaz, kısmi sonuçları kaydet.
3. --resume: --out dosyasındaki tamamlanmış kolları atla.
Ayrıca epizot düzeyinde hata izolasyonu: altyapı hatası olan epizot "failed"
işaretlenip ortalamaya dahil edilmesin, n_failed raporlansın. Düşük skor
dışlama gerekçesi değildir.

python scripts/run_ablation.py --arms C0 C4 --episodes 6 --max-cost 0.01
ile test et.
```
**Kabul:** bütçe aşımında temiz duruş; `--resume` tamamlanmış kolu atlıyor.

### P5 — Graf üretim boru hattı
```
scripts/build_graphs.py yaz. Girdi: bootstrap koşumunun results dosyası +
graphs/taubench_expert.json. Çıktı dört graf dosyası:

- G_llm    : pg/refiner.py::propose_edits ile TEK seferlik düzenleme,
             ProceduralGraph.apply_edits + validate; başarısızsa yeniden dene
             (max 3) ve nedenini logla.
- G_mined  : pg/controls.py::mine_graph(başarılı trace'ler). min_freq'i,
             kenar sayısı G_llm'inkinin 2 katını aşmayacak şekilde otomatik ayarla.
- G_shuf   : pg/controls.py::shuffle_topology(G_llm, seed). Geçerli değilse
             farklı tohumla yeniden dene.
- Dördünün karşılaştırmalı istatistik tablosunu (düğüm, kenar, ortalama çıkış
  derecesi, öznitelik doluluk oranı) markdown olarak yazdır.

Oyuncak ortamla uçtan uca test et.
```
**Kabul:** dört graf üretiliyor, hepsi `validate()` geçiyor, tablo basılıyor.

### P6 — Uyum analizi raporu
```
scripts/analyze_conformance.py yaz. Bir veya birden çok results dosyasını
okur ve her rehberlikli kol için pg/conformance.py kullanarak raporlar:
fitness, precision, F1, ortalama uyum, yüksek-uyum vs düşük-uyum başarı farkı,
en sık ihlal edilen geçişler, hiç ziyaret edilmemiş kenarlar.

Ayrıca çapraz tablo: her kol × (kendi grafı, G_llm) uyumu. Yani karıştırılmış
graf kolunun trace'lerinin GERÇEK grafa uyumunu da ölç — ajan karıştırılmış
rehberlik altında bile doğru prosedürü mü izliyor?

Markdown çıktı ver. Oyuncak veriyle test et.
```
**Kabul:** çapraz uyum tablosu üretiliyor ve okunabilir.

### P7 — Sonuç raporu + TOST
```
scripts/make_report.py yaz:
- Kol tablosu: başarı (%95 GA), adım, ajan token / rehberlik token /
  kullanıcı-sim token ayrı, önbellek isabeti, rehberlik çağrısı,
  lokalizasyon isabeti, başarı/1k token, $ maliyet.
- Planlı karşılaştırmalar: C4-C3, C4-C2, C4-C1, C4-C6 için eşli bootstrap +
  McNemar + Holm-Bonferroni.
- C5-C4 için TOST eşdeğerlik testi, marj ±5 puan.
- Tohumlar arası varyans (ortalama ± sd).
- preregistration.md'deki iddiaları okuyup "doğrulandı/doğrulanmadı/belirsiz"
  etiketi bas.
- Saf SVG Pareto grafiği (matplotlib YOK), markdown'a gömülü.
Sahte veriyle çalıştırıp örnek çıktıyı göster.
```
**Kabul:** çıktı doğrudan rapora/sunuma yapıştırılabilir.

---

## 6. İstatistik planı

- **Birim:** görev. Tüm koşullar aynı görev listesinde → **eşli** analiz.
- **İkili sonuçlar:** McNemar. **Sürekli:** 10.000 yeniden örneklemeli eşli
  bootstrap, %95 GA.
- **Planlı karşılaştırmalar (4):** C4−C3, C4−C2, C4−C1, C4−C6 →
  Holm-Bonferroni, α=0.05.
- **Eşdeğerlik (İ3):** C5 vs C4, **TOST**, marj ±5 puan. (Önceki plandaki
  "±1 puan" hedefi n=115'te yanlışlanamazdı — düzeltildi.)
- **Güç:** n=115 eşli ikili, taban oran ~0.65, uyuşmayan çift oranı ~%25 →
  %80 güçte ayırt edilebilir minimum fark yaklaşık **10–12 puan**. Bundan küçük
  farklar "belirsiz" olarak raporlanır, "yok" değil. Bu sayıyı ön kayda yazın.
- İki tohum **güç artırmaz**, varyans raporlamak içindir. Açıkça böyle yazın.

---

## 7. Bütçe ve kill kriterleri

**Maliyet formülü (pilotta doldurulacak):**
```
toplam ≈ 7 koşul × 115 görev × tohum × (ajan_token + rehberlik_token + usersim_token)
```
τ-bench'in kullanıcı simülatörü maliyetin yaklaşık yarısını alır — bunu
küçültmek için simülatörü en ucuz modelde çalıştırın ve **tüm koşullarda aynı
tutun**.

**Hedef:** 1 tohum için $40–60, 2 tohum için $80–110. Bootstrap + pilot ~$15.
HotpotQA negatif kontrolü ~$10.
**Sert tavan:** `--max-cost` ile kol başına, ve toplamda $150.

**Kill kriterleri (önceden kararlaştırılmış):**
1. Pilotta hiçbir koşul C0'dan ≥3 puan ayrışmıyor → tam koşumu iptal et,
   analiz notuna dön.
2. τ-bench kurulumu 3 günü aşıyor → BFCL v3 multi-turn'e geç (kullanıcı
   simülatörü yok, daha ucuz), ama graf boyutunun şişebileceğini not et.
3. Bütçenin %60'ı harcandığında ana koşum bitmemişse → 2. tohumu iptal et,
   tek tohumla raporla.

---

## 8. Teslim edilecekler

- [ ] `results/RAPOR.md` — kol tablosu, karşılaştırmalar, TOST, Pareto
- [ ] `results/uyum_analizi.md` — fitness/precision/uyum-başarı ilişkisi
- [ ] `results/gate_power_analysis.txt` — **hazır**
- [ ] `graphs/` — dört graf + üretim günlüğü
- [ ] `preregistration.md` — koşum öncesi commit'lenmiş, tarih damgalı
- [ ] `runs/*.jsonl` — ham telemetri
- [ ] Sunum: 16 slayt (ana rapordaki iskelet, yeni sonuçlarla)
- [ ] Depo: temiz README, `smoke_test` geçiyor, tek komutla yeniden koşulabilir

---

## 9. Karar ağacı (sonuçlar geldiğinde ne anlatacaksınız)

```
C4 − C3 büyük (topoloji taşıyor)
├── uyum yüksek  → "PG gerçekten yönlendiriyor; mekanizma doğrulandı.
│                   Ayrıca C5 ile %40 maliyete indirilebiliyor."
└── uyum düşük   → "Topoloji fark yaratıyor ama ajan grafı izlemiyor —
                    etki dolaylı; ilginç ve açıklanması gereken bir anomali."

C4 − C3 ≈ 0 (topoloji taşımıyor)
├── C4 − C1 büyük → "Kazanç, durum-duyarlı hatırlatmadan geliyor; graf
│                    yapısı gereksiz. PG basitleştirilebilir."
└── C4 − C1 ≈ 0  → "Kazanç, herhangi bir adım-başı hatırlatmadan geliyor.
                     PG'nin tüm mekanizması sorgulanmalı." (en güçlü bulgu)

C6 ≈ C4 → "LLM refiner'ın yerini $0'lık bir madenci alabiliyor."
C6 ≪ C4 → "Refiner, günlükte olmayan adımları icat edebiliyor; bu
           yeteneği ilk kez izole ettik." (makale lehine, yine de yeni)
```

Her yaprak yayınlanabilir. Plan, sonucun hangi yöne çıkacağına bağlı olmadan
değer üretecek şekilde kuruldu — iyi bir deneyin tek gerçek testi budur.

---

## 10. Takvim özeti

| Hafta | İş | Çıktı |
|---|---|---|
| 0 | Kurulum, LLM bağlantısı, τ-bench, `G_expert` | 3 epizotluk koşum yeşil |
| 1 | P1–P5 prompt'ları, bootstrap, graf üretimi, pilot | dört graf + pilot sayıları + bütçe kararı |
| 2 | Ana koşum (gözetimsiz), P6–P7 | ham sonuçlar |
| 3 | Analiz, uyum, yazım, slaytlar | rapor + sunum |

Toplam: **3–4 hafta yarı zamanlı**, **$100–150**, **6–8 gün yeni kod**.
