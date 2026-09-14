# Ön Kayıt (Preregistration) — PG-Lite deneyi

Bu dosya koşumlardan **önce** doldurulur ve sonrasında değiştirilmez. Amaç:
sonuçlara bakarak hipotez seçmeyi (HARKing) ve kol/metrik gezinmesini önlemek.
Sunumda "ön kayıt yaptım" demek, makalenin en zayıf noktasına (istatistiksel
karar verme) karşı sizin en güçlü kozunuzdur.

---

## 1. Araştırma soruları

**RQ1.** Prosedürel Graf'ın kazancının ne kadarı graftan, ne kadarı adım başına
eklenen ikinci LLM çağrısından geliyor?

**RQ2.** Rehberlik seçici olarak tetiklenip önbelleklenirse performans korunur mu?

**RQ3.** Lokalizasyon birebir eşleme yerine yumuşak eşleme ile yapılırsa isabet
oranı ve görev başarısı nasıl değişir?

**RQ4.** (opsiyonel) Kenar koşullarından türetilen sert guard'lar, yumuşak
rehberliğin yakalayamadığı ön-koşul ihlallerini engeller mi ve bunun bedeli nedir?

## 2. Hipotezler (yönlü, koşumdan önce sabit)

| Kod | Hipotez | Yanlışlama ölçütü |
|---|---|---|
| H1 | A2 − A1 > 0 | Eşli bootstrap %95 GA'sı 0'ı içermiyor ve fark ≥ 3 puan |
| H2 | A3 − A2 ≥ −1 puan **ve** A3 rehberlik çağrısı ≤ 0.4 × A2 | İki koşul birlikte sağlanmalı |
| H3 | A4 − A3 > 0, özellikle lokalizasyon isabet oranının düşük olduğu benchmark'ta | GA 0'ı içermiyor |
| H4 | A5 ihlal sayısını ≥ %50 azaltır, yanlış-blok oranı ≤ %3 | Her iki koşul |
| H5 | Kazanç (A2 − A0) ile görev prosedürelliği arasında ρ > 0.5 | Spearman |

**Sıfır hipotezi ilginç sonucu:** H1 reddedilemezse (A2 ≈ A1), bu makalenin ana
iddiasına dair güçlü bir negatif bulgudur ve aynı değerde raporlanır. Bu
cümleyi burada yazıyorum ki sonradan "aslında amacımız başkaydı" denmesin.

## 3. Kollar (sabit, sonradan eklenmez)

A0 vanilla ReAct · A1 grafsız danışman · A2 PG replikasyonu ·
A3 PG + seçici/önbellekli · A4 A3 + SoftMatch · A5 (opsiyonel) A4 + guard.

Ek kol eklenirse **keşifsel** olarak etiketlenir ve doğrulayıcı analize girmez.

## 4. Veri ve tekrar

- Benchmark 1: ALFWorld, standart unseen test bölümü (n = ____)
- Benchmark 2: HotpotQA, sabit tohumlu ____ örneklik alt küme
- Benchmark 3 (ops.): τ-bench retail (n = ____)
- Model: ____________ (çözücü ve rehberlik aynı model), temperature = 0
- Tohum sayısı: 3 (görev sırası + ortam tohumu). Tüm kollar **aynı** tohumları
  ve **aynı** görev listesini kullanır (common random numbers).

## 5. Birincil ve ikincil metrikler

**Birincil:** görev başarısı (benchmark'ın resmî metriği).
**Eş-birincil (maliyet):** toplam token ve rehberlik LLM çağrısı sayısı.
**İkincil:** adım sayısı, başarı/1k token, $ maliyet, gecikme.
**Tanı (keşifsel):** lokalizasyon isabet/geri-düşme oranı, önbellek isabeti,
kenar kullanımı, tekrar oranı, parse hatası oranı, guard tetikleme/yanlış-blok.

Birincil metrik koşum sırasında değiştirilmez.

## 6. İstatistiksel analiz planı

- Planlı karşılaştırmalar (4 adet): A1−A0, A2−A1, A3−A2, A4−A3.
- İkili sonuçlar: McNemar; sürekli skorlar: 10.000 yeniden örneklemeli eşli
  bootstrap, %95 GA.
- Çoklu karşılaştırma düzeltmesi: Holm–Bonferroni, α = 0.05.
- Etki büyüklüğü: mutlak puan farkı (+ oranlar için Cohen's h).
- Tüm p-değerleri ve GA'lar, anlamlı olsun olmasın raporlanır.

## 7. Durdurma ve dışlama kuralları

- Koşum bütçesi: toplam ____ USD. Bütçe dolarsa tamamlanan tohumlar raporlanır,
  yarım kalan tohum **atılmaz**, eksik olarak işaretlenir.
- Bir epizot yalnızca altyapı hatası (API 5xx, zaman aşımı) nedeniyle dışlanır;
  dışlanan epizot sayısı kol bazında raporlanır. Düşük skor dışlama gerekçesi değildir.
- Hiçbir kol, sonuçlara bakıldıktan sonra yeniden koşulmaz. Yeniden koşum
  gerekirse tüm kollar birlikte yeniden koşulur.

## 8. Beyan edilen sapmalar

Koşum sırasında plandan sapma olursa buraya tarih ve gerekçeyle eklenir:

| Tarih | Sapma | Gerekçe |
|---|---|---|
|  |  |  |

---

Doldurma tarihi: ____________  ·  İmza/sorumlu: ____________
