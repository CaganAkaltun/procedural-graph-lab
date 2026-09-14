# Sıfırdan Uygulama Rehberi — PG-Lite

Bilgisayarınızda hiçbir şey kurulu değilken başlayıp, çalışan bir deney düzeneği
ve canlı izleme panosuna kadar gider. Her adımın sonunda **"nasıl anlarım
çalıştığını"** kontrolü var. Claude Code'a vereceğiniz prompt'lar §6'da,
kopyala-yapıştır formatında.

**Toplam süre:** ilk çalışan düzenek ~45 dakika (sahte LLM ile), gerçek model +
gerçek benchmark ~1–2 gün.

---

## Yol haritası

```
0. Ön koşullar (Python, Git, editör)          ~15 dk
1. Projeyi kur, duman testini geç             ~10 dk   <- burada her şey çalışır
2. Dashboard'u aç                             ~2 dk
3. Gerçek modeli bağla (API anahtarı)         ~20 dk
4. Gerçek ortamı bağla (ALFWorld/HotpotQA)    ~2-6 saat
5. Ön kaydı doldur                            ~30 dk
6. Claude Code prompt'ları ile geliştir       (§6)
7. Ana deneyi koş                             ~1-2 gün
8. (Opsiyonel) Pi kodlama izi                 ~1 gün
```

---

## 0. Ön koşullar

### 0.1 Python 3.10+

**macOS**
```bash
# Homebrew yoksa:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 git
```

**Windows** — PowerShell'i yönetici olarak açın:
```powershell
winget install Python.Python.3.12
winget install Git.Git
winget install Microsoft.VisualStudioCode
```
Windows'ta komutları **PowerShell**'de çalıştırın; rehberdeki `python3` yerine
`python`, `source .venv/bin/activate` yerine `.venv\Scripts\Activate.ps1` kullanın.

**Linux (Ubuntu/Debian)**
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

**Kontrol:**
```bash
python3 --version   # 3.10 veya üstü olmalı
git --version
```

### 0.2 Editör ve Claude Code

VS Code kurun (yukarıdaki winget/brew ile veya code.visualstudio.com).
Claude Code'u kurun ve giriş yapın:

```bash
npm install -g @anthropic-ai/claude-code    # Node.js 18+ gerekir
claude                                       # ilk çalıştırmada /login
```

Node.js yoksa: `brew install node` (macOS) / `winget install OpenJS.NodeJS.LTS`
(Windows) / `sudo apt install nodejs npm` (Linux).

> **Not:** Claude Code'u projenin kök dizininde açın. Kod tabanını gördüğü için
> prompt'larınız çok daha isabetli çalışır.

### 0.3 Dizin

```bash
mkdir -p ~/projects && cd ~/projects
```

---

## 1. Projeyi kurun

`pg_lite.zip` dosyasını `~/projects` altına açın:

```bash
cd ~/projects
unzip pg_lite.zip          # ~/projects/pg_lite oluşur
cd pg_lite
```

Sanal ortam (bağımlılık yok ama alışkanlık iyi bir şey; gerçek LLM için gerekecek):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**Duman testi — hiçbir API anahtarı gerekmez:**

```bash
python scripts/smoke_test.py
```

Beklenen: 7 bölüm sırayla geçer ve `SMOKE TEST PASSED` yazar. Çıktıda görmeniz
gerekenler:
- graf doğrulaması hatalı kenarı reddediyor
- `exact` lokalizasyon %25 isabet, `soft` %50 isabet + 0 sert hata
- A2/A4/A5 kolları A0'ı açık ara geçiyor
- evrim: bozuk uzman prior'ı düzeltiliyor, zararlı düzenleme `early_reject`,
  tekrarı `duplicate` olarak eleniyor

**İlk gerçek koşumunuz (hâlâ sahte LLM ile):**

```bash
python scripts/run_ablation.py --arms A0 A1 A2 A3 A4 A5 \
    --episodes 24 --graph graphs/toy_correct.json \
    --out results/demo.json --label "ilk-deneme"

python scripts/run_evolution.py --rounds 4 --train 24 --val 12 \
    --init expert --label "ilk-evrim"
```

> ⚠️ Bu sayılar **bilimsel değildir**. Sahte LLM boru hattını doğrular, model
> davranışını değil. Amaç: gerçek modele para harcamadan önce her şeyin
> bağlandığından emin olmak.

**Git ile sürümleyin** (bundan sonrası için şart — Claude Code'un yaptığı her
değişikliği geri alabilmek istersiniz):

```bash
git init && git add -A && git commit -m "PG-Lite iskelet"
```

---

## 2. Dashboard'u açın

Yeni bir terminal sekmesi açın (koşum terminali ayrı kalsın):

```bash
cd ~/projects/pg_lite
source .venv/bin/activate
python dashboard/server.py           # http://127.0.0.1:8777
```

Tarayıcıda `http://127.0.0.1:8777` adresini açın. Sıfır bağımlılık, sadece
Python standart kütüphanesi. 2 saniyede bir kendini yeniler.

**Panolar:**

| Panel | Ne gösterir | Neye bakacaksınız |
|---|---|---|
| Özet | kol/epizot/token/maliyet, en iyi kol | bütçe takibi |
| Kollar | kol başına ilerleme çubuğu, başarı, adım, token, rehberlik çağrısı, önbellek isabeti, **lokalizasyon isabeti**, guard blok, başarı/1k token | A3'ün rehberlik çağrısı A2'nin %40'ının altına indi mi? |
| Öğrenme eğrisi | kümülatif başarı, epizot bazında | kollar ayrışıyor mu, yoksa gürültü mü? |
| Pareto | token ↔ başarı saçılımı | sol-üstteki kol kazanır |
| Lokalizasyon | exact/typed/semantic/sticky/none dağılımı | **kırmızı (`none`) payı büyükse makalenin sert eşlemesi kırılıyor demektir** |
| Evrim turları | tur kararı, aday vs elde tutulan skor, graf boyutu | kapı gürültüyle mi karar veriyor? |
| Olay akışı | son 40 olay | koşum takılmış mı? |

Koşumlar `runs/*.jsonl` altına append-only yazılır. Koşum çökerse bile dosya
okunabilir kalır; dashboard'u koşum sırasında açıp kapatabilirsiniz.

Farklı port / farklı klasör:
```bash
python dashboard/server.py --port 9000 --runs /başka/yol/runs
```

**Kontrol:** Dashboard'da "ilk-deneme" ve "ilk-evrim" koşumlarını görüyorsanız,
telemetri zinciri tamam.

---

## 3. Gerçek modeli bağlayın

### 3.1 API anahtarı

console.anthropic.com üzerinden bir anahtar alın ve **kodun içine yazmayın**:

```bash
# macOS / Linux
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc && source ~/.zshrc
# Windows PowerShell (kalıcı)
setx ANTHROPIC_API_KEY "sk-ant-..."
```

```bash
pip install anthropic
echo ".venv/" > .gitignore && echo "runs/" >> .gitignore && echo "results/" >> .gitignore
```

### 3.2 `AnthropicLLM.complete()` gövdesini doldurun

`pg/llm.py` içinde hazır bir iskelet ve docstring var. Bunu elle yazmak yerine
§6.1'deki Claude Code prompt'unu kullanın. Doldurulduktan sonra:

```bash
python -c "
from pg.llm import AnthropicLLM
llm = AnthropicLLM()
print(llm.complete('Sadece OK yaz.', role='solver'))
print(llm.tracker.summary())
"
```

**Kontrol:** `OK` gelmeli ve `tracker.summary()` token sayıları göstermeli.
Token muhasebesi **rol bazında** olmalı (`solver_tokens`, `guidance_tokens`,
`refiner_tokens`) — bütün maliyet analiziniz buna dayanıyor.

### 3.3 Bütçe koruması

İlk gerçek koşumdan önce küçük bir limit koyun: `run_ablation.py`'ye
`--max-cost` bayrağı ekleyin (§6.2 prompt'u bunu yapar). Böylece bir hata
gecede 200 dolar yakmaz.

---

## 4. Gerçek ortamı bağlayın

Öncelik sırası: **ALFWorld → HotpotQA → τ-bench**. İlk ikisi yeterli.

### 4.1 ALFWorld (yüksek prosedürellik — PG'nin en çok kazandığı yer)

```bash
pip install alfworld
alfworld-download          # oyun verilerini indirir (birkaç GB)
```

Kurulum sorun çıkarırsa: Python 3.10/3.11 kullanın, `textworld` bağımlılığı
bazı sürümlerde 3.12 ile sorunlu olabilir.

Sonra `pg/envs/alfworld.py` yazılacak — §6.3 prompt'u.

### 4.2 HotpotQA (düşük prosedürellik — kontrol grubunun en bilgilendirici olduğu yer)

Canlı web araması **kullanmayın**, tekrar üretilemez. ReAct'in orijinal
kurulumundaki gibi yerel bir Wikipedia arama aracı kullanın:

```bash
pip install datasets rank_bm25
python -c "
from datasets import load_dataset
d = load_dataset('hotpot_qa','distractor',split='validation[:1000]')
d.to_json('data/hotpotqa_1000.jsonl')
print(len(d))
"
```

Distractor ayarında her sorunun kendi paragrafları gelir; arama aracını bu
paragraflar üzerinde BM25 ile kurmak hem ucuz hem deterministiktir.
`pg/envs/hotpotqa.py` — §6.4 prompt'u.

### 4.3 Başlangıç grafları

Her ortam için 7–12 düğümlük bir uzman prior'ı yazın (makalenin graf boyutları
da bu aralıkta) **veya** `--init scratch` ile evrime bırakın. Makalenin en
ilginç bulgusu, sıfırdan evrimin uzman prior'ını yakalayıp geçmesiydi — iki
kolu da koşarsanız bu bulguyu da tekrar etmiş olursunuz.

---

## 5. Ön kaydı doldurun

`preregistration.md` dosyasını **koşumdan önce** doldurun ve commit'leyin:

```bash
git add preregistration.md && git commit -m "ön kayıt: koşum öncesi hipotezler"
git log -1 --format=%cd    # tarih damgası kanıtınız
```

Sunumda "hipotezleri koşumdan önce commit'ledim" diyebilmek, makalenin en zayıf
yanına (istatistiksel karar verme) karşı en güçlü kozunuz.

---

## 6. Claude Code prompt'ları

Her prompt bağımsız çalışır. **Sırayla** verin, her birinden sonra kabul
kriterini kendiniz doğrulayın, sonra commit'leyin. Claude Code'u proje kökünde
açın:

```bash
cd ~/projects/pg_lite && claude
```

> **Genel kural:** Her prompt'un sonunda "değişiklikten sonra
> `python scripts/smoke_test.py` çalıştır ve geçtiğini göster" yazıyor. Bunu
> silmeyin — regresyonu anında yakalar.

---

### 6.0 — Oryantasyon (ilk prompt)

```
Bu depo, arXiv:2609.09153 (Procedural Graphs) makalesinin açık bir yeniden
uygulaması ve üzerine önerilen iyileştirmelerin (PG-Lite) deney altyapısı.
Önce README.md'yi ve pg/ altındaki tüm modülleri oku. Sonra bana şunları
özetle:

1. Kolların (A0-A5) her biri hangi araştırma sorusunu test ediyor?
2. Rehberlik tetikleme politikası (pg/guidance.py::_should_regenerate) hangi
   koşullarda yeniden üretim yapıyor?
3. Bir epizot boyunca veri akışı: hangi fonksiyon hangi sırayla çağrılıyor?
4. Kodda gördüğün, bilimsel sonuçları bozabilecek 3 potansiyel hata veya
   kırılganlık nedir?

Henüz hiçbir dosyayı değiştirme. Sadece analiz et.
```

**Kabul kriteri:** Özet doğruysa Claude Code kod tabanını anlamış demektir;
sonraki prompt'lar çok daha isabetli olur. 4. maddedeki uyarıları not alın.

---

### 6.1 — Gerçek LLM bağlantısı

```
pg/llm.py içindeki AnthropicLLM sınıfını tamamla.

Gereksinimler:
- anthropic SDK kullan, client'ı lazy olarak ilk çağrıda oluştur.
- complete(prompt, role, system, max_tokens) imzası değişmesin.
- temperature=0 (yeniden üretilebilirlik).
- Gerçek token sayımını API yanıtındaki usage.input_tokens ve
  usage.output_tokens alanlarından al; UsageTracker'a rol bazında yaz
  (rough_tokens tahminini kullanma).
- Hata dayanıklılığı: 429 ve 5xx için üstel geri çekilmeli yeniden deneme
  (en fazla 5 deneme, jitter'lı), diğer hatalarda anlamlı bir istisna fırlat.
- İsteğe bağlı basit disk önbelleği: aynı (model, system, prompt) için yanıtı
  .cache/ altında sakla; ortam değişkeni PG_CACHE=0 ile kapatılabilsin.
  Önbellekten gelen yanıtlar UsageTracker'a "cached" olarak ayrı sayılsın,
  maliyete eklenmesin.
- UsageTracker'a fiyatlandırmayı model adına göre ayarlayan bir sınıf metodu ekle.

Sonra scripts/ altına check_llm.py yaz: küçük bir istek atar, yanıtı,
rol bazlı token sayılarını ve tahmini maliyeti yazdırır.

En son: python scripts/smoke_test.py çalıştır (MockLLM yolu bozulmamalı) ve
geçtiğini göster.
```

**Kabul kriteri:** `python scripts/check_llm.py` gerçek yanıt + gerçek token
sayısı basar; smoke test hâlâ geçer.

---

### 6.2 — Bütçe koruması ve devam edilebilirlik

```
Uzun koşumlarda para ve zaman kaybını önlemek için üç şey ekle:

1. scripts/run_ablation.py ve scripts/run_evolution.py'ye --max-cost FLOAT
   bayrağı: her epizottan sonra UsageTracker.cost_usd() kontrol edilsin,
   limit aşılırsa koşum temiz biçimde dursun, telemetriye
   note("budget_exceeded", cost=...) yazılsın ve o ana kadarki sonuçlar
   kaydedilsin.

2. Checkpoint/devam: her kol bittiğinde ara sonuçlar --out dosyasına yazılsın.
   --resume bayrağı verilirse, aynı --out dosyasındaki tamamlanmış kollar
   atlanıp kalanlardan devam edilsin.

3. Epizot düzeyinde hata izolasyonu: bir epizot istisna fırlatırsa tüm koşum
   çökmesin; epizot "failed" olarak işaretlenip telemetriye yazılsın ve
   ortalamalara dahil edilmesin. Kol özetinde n_failed alanı raporlansın.
   Not: düşük skor bir dışlama gerekçesi DEĞİL, sadece altyapı hatası öyle.

Değişiklikten sonra python scripts/smoke_test.py ve
python scripts/run_ablation.py --arms A0 A2 --episodes 6 --max-cost 0.01
çalıştır, ikisinin de beklendiği gibi davrandığını göster.
```

**Kabul kriteri:** `--max-cost 0.01` ile koşum erken ve temiz duruyor; `--resume`
ikinci çalıştırmada tamamlanmış kolu atlıyor.

---

### 6.3 — ALFWorld sarmalayıcısı

```
pg/envs/alfworld.py yaz: pg/runner.py içindeki Env protokolünü uygulayan bir
AlfWorldEnv sınıfı.

- alfworld kütüphanesini kullan, standart "unseen" test bölümünü yükle.
- reset(task_id) görev metnini + ilk gözlemi döndürsün; description özelliği
  görev hedefini içersin.
- actions() ALFWorld'ün admissible_commands listesini döndürsün (dinamik).
- step(action) -> (gözlem, bitti_mi); geçersiz komutlarda ortamın hata
  mesajını olduğu gibi gözlem olarak ver (guard ve hata tetikleyicileri buna
  bakıyor).
- score() başarı için 1.0, aksi hâlde 0.0.
- Görev listesini deterministik almak için bir sınıf metodu ekle:
  AlfWorldEnv.task_ids(n, seed) -> list[str].

Ayrıca graphs/alfworld_pg.json oluştur: ALFWorld'ün prosedürel yapısını
yansıtan 9-12 düğümlük bir uzman prior'ı. Düğümler somut araç adları değil,
semantik prosedürler olsun (ör. Orient, FindReceptacle, Take, Move, Heat/Clean,
PlaceTarget, Verify, Finish). Her kenara condition/guidance/pitfalls yaz ve
en az iki kenara guard ekle (require_before tipinde).

scripts/run_ablation.py içindeki _register_envs() fonksiyonuna "alfworld"
kaydını ekle.

Son olarak: python scripts/run_ablation.py --env alfworld --arms A0 A2
--episodes 3 --provider mock ile dumanı test et ve çıktıyı göster.
```

**Kabul kriteri:** 3 epizotluk sahte koşum hatasız tamamlanıyor; dashboard'da
ALFWorld koşumu görünüyor.

---

### 6.4 — HotpotQA sarmalayıcısı

```
pg/envs/hotpotqa.py yaz: Env protokolünü uygulayan HotpotQAEnv.

- data/hotpotqa_1000.jsonl dosyasını oku (distractor ayarı).
- Araçlar: search(query), lookup(keyword), finish(answer). search, o soruya ait
  paragraflar üzerinde BM25 ile çalışsın (rank_bm25); canlı web KULLANMA.
- step() ReAct formatındaki argümanı ayrıştırsın; ayrıştırma hatasında
  "Error: could not parse action" gözlemi dönsün (parse hatası metriği için).
- score(): önce katı Exact Match, ayrıca kelime düzeyinde F1 hesapla ve
  info sözlüğünde döndür. LLM-judge opsiyonel olsun (--judge bayrağı).
- Deterministik alt küme seçimi: HotpotQAEnv.task_ids(n, seed).

graphs/hotpotqa_pg.json oluştur: makaledeki 9 düğümlük grafa benzer bir prior
(Start, FirstHopRetrieve, ScanIndex, BridgeExtract, SecondHopRetrieve, Verify,
Finish). Kenarlara condition/guidance/pitfalls yaz.

_register_envs()'e "hotpotqa" kaydını ekle ve 3 epizotluk mock koşumla test et.
```

**Kabul kriteri:** Mock koşum çalışıyor; `score()` EM ve F1 birlikte raporluyor.

---

### 6.5 — Lokalizasyon telemetrisi ve doğruluk denetimi

```
Rapordaki I3 fikri için lokalizasyonu ölçülebilir hâle getir:

1. pg/localize.py'de her locate() çağrısını isteğe bağlı bir RunLogger'a
   yazdır: (adım, son_eylem, seçilen_düğüm, aşama, skor). Aşırı log olmasın
   diye örnekleme oranı parametresi koy (varsayılan 1.0).

2. scripts/audit_localization.py yaz: bir koşumun JSONL'ini okur, rastgele
   N=50 lokalizasyon kararını seçer ve her biri için (son eylem + gözlem +
   seçilen düğüm + graftaki alternatif düğümler) içeren bir denetim dosyası
   üretir. İki mod olsun: (a) manuel denetim için markdown çıktısı,
   (b) --judge ile bir LLM'e "bu lokalizasyon doğru mu?" diye sorup
   doğruluk oranı hesaplama.

3. Dashboard'a lokalizasyon panelinde "denetlenmiş doğruluk" satırı ekle
   (audit dosyası varsa göster).

Neden önemli: makale lokalizasyon isabet oranını hiç raporlamıyor, ama eşleme
başarısız olunca sistem tüm grafa düşüyor ve makalenin kendi Tablo 3'ü bunun
zararlı olabildiğini gösteriyor.

smoke_test'i çalıştır ve geçtiğini göster.
```

**Kabul kriteri:** `audit_localization.py` okunabilir bir markdown denetim
dosyası üretiyor.

---

### 6.6 — Dashboard geliştirmeleri

```
dashboard/ altındaki panoya şunları ekle (stdlib dışı bağımlılık EKLEME,
CDN kullanma — çevrimdışı çalışmalı):

1. Kol karşılaştırma paneli: seçilen iki kol arasında eşli bootstrap farkı,
   %95 güven aralığı ve McNemar p-değeri. Hesaplamayı sunucu tarafında
   pg/stats.py'yi kullanarak yap, /api/compare?a=A2&b=A1 uç noktası olarak sun.

2. Bütçe göstergesi: --max-cost verilmişse, harcanan/limit oranını bir çubuk
   olarak göster; %80'i geçince turuncu, %100'de kırmızı.

3. Canlı ETA: son 10 epizotun ortalama süresinden kalan süreyi tahmin et.

4. Tetikleme dağılımı paneli: guidance stats içindeki triggers sözlüğünü
   (node_changed / error_observed / ambiguous_branch / stale / cached) yığılmış
   çubuk olarak göster. Seçici rehberliğin neden tetiklendiğini görmek,
   I2'nin ana kanıtı.

5. Koşumları silme/arşivleme düğmesi (runs/archive/ altına taşısın).

Sunucuyu çalıştırıp uç noktaların doğru JSON döndürdüğünü curl ile göster.
```

**Kabul kriteri:** `/api/compare?a=A2&b=A1` doğru istatistikleri döndürüyor;
sayfa çevrimdışı açılıyor.

---

### 6.7 — Sonuç raporu üreticisi

```
scripts/make_report.py yaz: bir veya birden fazla results/*.json dosyasını
okuyup makale/sunum kalitesinde bir markdown raporu üretsin:

- Kol tablosu: başarı (±%95 GA), adım, token (çözücü/rehberlik ayrı),
  rehberlik çağrısı, önbellek isabeti, lokalizasyon isabeti, guard blokları,
  başarı/1k token, $ maliyet.
- Planlı karşılaştırmalar tablosu: eşli bootstrap farkı + GA + McNemar p +
  Holm-Bonferroni sonucu.
- Pareto grafiği: matplotlib YOK; saf SVG üret ve markdown'a göm.
- Ön kayıttaki hipotezleri (preregistration.md'den okusun) tek tek listeleyip
  "doğrulandı / doğrulanmadı / belirsiz" etiketi bassın.
- Tohumlar arası varyans: aynı kolun farklı tohumlardaki sonuçlarını birleştirip
  standart sapmayı raporlasın.

Sahte verilerle çalıştırıp örnek çıktıyı göster.
```

**Kabul kriteri:** Üretilen markdown doğrudan sunuma/rapora yapıştırılabilir.

---

### 6.8 — (Opsiyonel) Pi kodlama izi

```
pi-extension/pg-pi.ts dosyasını oku. Pi coding agent (pi.dev) için bu uzantıyı
çalışır hâle getir:

1. pi-extension/ altında minimal bir package.json + tsconfig.json oluştur,
   @earendil-works/pi-coding-agent'ı peer dependency olarak ekle.
2. pi-extension/README.md yaz: kurulum, ortam değişkenleri (PG_GRAPH,
   PG_MODE, PG_SELECTIVE, PG_GUARDS, PG_LOG, PG_HOPS), /pg-stats ve
   /pg-reload komutları.
3. scripts/pi_trace_to_episodes.py yaz: PG_LOG'daki JSONL izini okuyup
   pg/refiner.py'nin beklediği EpisodeResult listesine dönüştürsün. Böylece
   kodlama oturumlarından offline evrim döngüsü beslenebilir.
4. Küçük bir test süiti kur: 5 basit bug-fix görevi içeren bir test reposu
   oluştur (her görev için deterministik bir test komutu), PG açık/kapalı
   koşup guard tetiklenmelerini ve lokalizasyon aşamalarını raporla.

Önemli: Pi'de sadece dört araç var (read/write/edit/bash), bu yüzden düğüm
sözlüğü semantik prosedürlerden oluşmalı ve lokalizasyon zorunlu olarak
semantik. graphs/coding_pg.json içindeki cues alanlarını buna göre gözden geçir.
```

**Kabul kriteri:** `pi` oturumunda `/pg-stats` çalışıyor, `PG_LOG` dosyası
doluyor, guard en az bir kez tetikleniyor.

---

## 7. Ana deneyi koşun

### 7.1 Pilot (her zaman önce bu)

```bash
python scripts/run_ablation.py --env alfworld --arms A0 A1 A2 A3 A4 \
    --episodes 10 --provider anthropic --max-cost 3 --label "pilot-alfworld"
```

Pilotta kontrol edin:
- Dashboard'da lokalizasyon isabet oranı ne? %70'in altındaysa SoftMatch
  hipoteziniz (I3) zaten güçlü destek buluyor demektir.
- A3'ün rehberlik çağrısı A2'nin kaçta kaçı? Hedef ≤ %40.
- Epizot başına maliyet × planlanan epizot = toplam bütçe tahmininiz tutuyor mu?

### 7.2 Tam koşum

```bash
for SEED in 1 2 3; do
  python scripts/run_ablation.py --env alfworld --arms A0 A1 A2 A3 A4 A5 \
      --episodes 134 --seed $SEED --provider anthropic --max-cost 40 \
      --out results/alfworld_s$SEED.json --label "alfworld-seed$SEED"
done

for SEED in 1 2 3; do
  python scripts/run_ablation.py --env hotpotqa --arms A0 A1 A2 A3 A4 \
      --episodes 300 --seed $SEED --provider anthropic --max-cost 40 \
      --out results/hotpot_s$SEED.json --label "hotpot-seed$SEED"
done

python scripts/make_report.py results/*.json --out results/RAPOR.md
```

> `--seed` bayrağı henüz yoksa 6.2 prompt'una ekletin: tohum, görev sırasını ve
> ortam tohumunu belirlemeli, **tüm kollar aynı tohumu** kullanmalı (common
> random numbers) — eşli istatistiğin geçerliliği buna bağlı.

### 7.3 Evrim koşumu

```bash
python scripts/run_evolution.py --env alfworld --init scratch \
    --rounds 8 --train 60 --val 30 --arm A4 \
    --provider anthropic --max-cost 60 --label "alfworld-evolution-scratch"
```

Sonra evrilen grafı test kümesinde koşun ve **aramada görülen en iyi turu değil,
dönen grafı** raporlayın (makalenin dürüstçe yaptığı şey):

```bash
python scripts/run_ablation.py --env alfworld --arms A4 \
    --graph results/evolution_graph.json --episodes 134 \
    --provider anthropic --label "alfworld-evolved-test"
```

---

## 8. Sorun giderme

| Belirti | Olası neden | Çözüm |
|---|---|---|
| `ModuleNotFoundError: pg` | script'i yanlış dizinden çalıştırdınız | proje kökünden çalıştırın; script'ler `sys.path`'e kökü ekliyor |
| Dashboard boş | `runs/` altında dosya yok veya yanlış klasör | `--runs` yolunu kontrol edin; bir koşum başlatın |
| Dashboard'da koşum "çalışıyor" kalıyor | koşum çöktü veya SIGPIPE ile öldü (`| head` kullanmayın) | koşum terminalindeki hataya bakın |
| Lokalizasyon isabeti %0 | düğüm kimlikleri araç adlarıyla eşleşmiyor | `--arms A4` (soft) kullanın; `cues` alanlarını doldurun |
| Tüm kollar aynı sonucu veriyor | rehberlik prompt'a ulaşmıyor | `runs/*.jsonl` içinde `guidance_calls > 0` mı? solver prompt'unu bir kez yazdırın |
| Maliyet beklenenin çok üstünde | rehberlik her adımda üretiliyor | A3/A4 kollarını kullanın; `triggers` dağılımına bakın |
| API 429 | hız limiti | 6.1'deki geri çekilmeli yeniden deneme; eşzamanlılığı düşürün |
| Guard'lar başarıyı düşürüyor | aşırı kısıtlama | `false_blocks` sayacına bakın; guard'ı ayrı kolda tutun, ana iddiaya bağlamayın |

---

## 9. Bitirme kontrol listesi

- [ ] `smoke_test.py` geçiyor
- [ ] Dashboard canlı koşumu gösteriyor
- [ ] `check_llm.py` gerçek token sayısı basıyor
- [ ] En az bir gerçek ortam bağlı (ALFWorld veya HotpotQA)
- [ ] `preregistration.md` doldurulmuş ve **koşumdan önce** commit'lenmiş
- [ ] Pilot koşum tamam, bütçe tahmini doğrulandı
- [ ] 3 tohumlu tam koşum tamam
- [ ] Lokalizasyon isabet oranı raporlandı (makalenin raporlamadığı sayı)
- [ ] A1 (grafsız danışman) sonucu raporlandı (makalenin koşmadığı kol)
- [ ] A3'ün rehberlik çağrısı tasarrufu raporlandı
- [ ] `make_report.py` çıktısı hazır
- [ ] Sunum slaytları (ana rapordaki 16 slaytlık iskelet)

---

## 10. Günlük iş akışı özeti

```bash
# Terminal 1 — dashboard (açık kalsın)
cd ~/projects/pg_lite && source .venv/bin/activate && python dashboard/server.py

# Terminal 2 — koşumlar
cd ~/projects/pg_lite && source .venv/bin/activate
python scripts/run_ablation.py --env alfworld --arms A0 A2 A3 --episodes 20 \
    --provider anthropic --max-cost 5 --label "günlük-test"

# Terminal 3 — geliştirme
cd ~/projects/pg_lite && claude
```

Her anlamlı değişiklikten sonra:
```bash
git add -A && git commit -m "ne değişti"
```
