#!/usr/bin/env python3
"""Bursa dershane + özel eğitim kurumları — MEB tablosu + el seçimi.

Kaynak: MEB özel öğretim kurumu listesi (eniyidershaneler.com / okuldershane.com yansıması).
Telefon ve adres resmi kayıt formatındadır.

  python3 BursaApp/dershane_fetch.py              # JSON üret → data/meb_dershaneler_bursa.json
  python3 BursaApp/dershane_fetch.py --geocode     # koordinat eksiklerini Nominatim ile doldur
  python3 BursaApp/dershane_fetch.py --merge       # schools.json ile birleştir (schools_fetch öncesi)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
MEB_PATH = os.path.join(DATA, "meb_dershaneler_bursa.json")
OZEL_PATH = os.path.join(DATA, "ozel_egitim_curated.json")
GEOCODE_CACHE = os.path.join(DATA, "dershane_geocode.json")
SCHOOLS_PATH = os.path.join(DATA, "schools.json")
NOMINATIM = "https://nominatim.openstreetmap.org/search"

ILCELER = (
    "Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl",
    "Mustafakemalpaşa", "İznik", "Kestel", "Gürsu", "Orhangazi", "Karacabey",
    "Yenişehir", "Orhaneli", "Büyükorhan", "Harmancık", "Keles",
)
ILCE_NORM = {x.lower().replace("i", "ı"): x for x in ILCELER}

# MEB Bursa dershane tablosu (2026 listesi — alfabetik, ayrım yok)
MEB_TABLE: list[tuple[str, str, str, str]] = [
    ("ÖZEL VERİMLİ İLGİLİ PROFESYONEL (VİP) PRATİK DERSHANESİ", "OSMANGAZİ", "ORHANBEY MAH. TAŞKAPI CAD. NO: 19 İÇ KAPI NO: 101 OSMANGAZİ / BURSA", "5334359713"),
    ("ÖZEL SETBAŞI FİNAL DERSHANESİ", "YILDIRIM", "KARAAĞAÇ MAH. NAMAZGAH CAD. NO: 24 İÇ KAPI NO: 3 YILDIRIM / BURSA (DİĞER İÇ KAPILAR: 4-5)", "2243283900"),
    ("ÖZEL KAREKÖK AKADEMİ MATEMATİK DERSHANESİ", "YILDIRIM", "ERİKLİ MAH. EFLAK CAD. ADANUR APT. SİTESİ A BLOK NO: 1-3 İÇ KAPI NO: 4 YILDIRIM / BURSA", "2243412493"),
    ("ÖZEL BURSA YÖNTEM DERSHANESİ", "NİLÜFER", "KONAK MAH. YILDIRIM CAD. 22 NOLU BB. SİTESİ NO: 119B NİLÜFER / BURSA", "5550550816"),
    ("ÖZEL BURSA SEMBOL ARTI DERSHANESİ", "OSMANGAZİ", "DOĞANBEY MAH. DOĞANBEY ÇIKMAZI SK. BERK 2 PLAZA SİTESİ NO: 3 İÇ KAPI NO: 14 OSMANGAZİ / BURSA", "2242222257"),
    ("ÖZEL BURSA FEN BİLİMLERİ DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. NO: 182 İÇ KAPI NO: 6 NİLÜFER / BURSA", "2242212290"),
    ("ÖZEL BURSA BİLİM DERSHANESİ", "OSMANGAZİ", "ORHANBEY MAH. RESSAM ŞEFİK BURSALI CAD. NO: 34 İÇ KAPI NO: 1 OSMANGAZİ / BURSA", "2242231007"),
    ("ÖZEL NİLÜFER AKADEMİ DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. ARIKANLAR İŞ MERKEZİ SİTESİ ARIKANLAR İŞ MERKEZİ BLOK NO: 160 İÇ KAPI NO: 2 NİLÜFER / BURSA (DİĞER İÇ KAPILAR: 3-4-5)", "2244524046"),
    ("ÖZEL ÇEKİRGE KÜPKÖK DERSHANESİ", "OSMANGAZİ", "DİKKALDIRIM MAH. ZÜBEYDE HANIM CAD. NO: 15 İÇ KAPI NO: 1 OSMANGAZİ / BURSA", "2242333232"),
    ("ÖZEL ESEN DERSHANESİ", "NİLÜFER", "ÇAMLICA MAH. LEFKOŞE CAD. NO: 254A NİLÜFER / BURSA", "5354160836"),
    ("ÖZEL BİLGİ DERSHANESİ", "NİLÜFER", "ESENTEPE MAH. OKUL CAD. NO: 6 İÇ KAPI NO: 1 NİLÜFER / BURSA", "2244513200"),
    ("ÖZEL NİLÜFER TAŞ MEKTEP DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. İZMİR YOLU CAD. NO: 107 NİLÜFER / BURSA", "5397957566"),
    ("ÖZEL İNEGÖL AÇI DERSHANESİ", "İNEGÖL", "KEMALPAŞA MAH. İSMAİL EFENDİ CAD. NO: 9 İÇ KAPI NO: 1 İNEGÖL / BURSA", "2247130712"),
    ("ÖZEL YENİŞEHİR LİDER DERSHANESİ", "YENİŞEHİR", "KURTULUŞ MAH. ATATÜRK CAD. NO: 78 İÇ KAPI NO: 1 YENİŞEHİR / BURSA (DİĞER İÇ KAPILAR: 2)", "2247120776"),
    ("ÖZEL FOMARA FARKLI KALİTE MODERN DERSHANESİ", "OSMANGAZİ", "AKTARHÜSSAM MAH. 1.BÖLÜNTÜ SK. NO: 2 OSMANGAZİ / BURSA", "2244521122"),
    ("ÖZEL ALTIPARMAK SINAV DERSHANESİ", "OSMANGAZİ", "KURUÇEŞME MAH. 2.OTEL SK. İZZET ULUCA İŞHANI SİTESİ B BLOK NO: 4A OSMANGAZİ / BURSA", "2242255570"),
    ("ÖZEL NİTELİKLİ EĞİTİMİN ODAK NOKTASI DERSHANESİ", "NİLÜFER", "ESENTEPE MAH. FATİH SULTAN MEHMET BUL. NO: 92A NİLÜFER / BURSA", "2242461516"),
    ("ÖZEL BURSA ELİT DERSHANESİ", "NİLÜFER", "ESENTEPE MAH. GÜRLER CAD. NO: 2/1 İÇ KAPI NO: 1 NİLÜFER / BURSA (DİĞER İÇ KAPILAR: 2-3-4-5)", "5454464770"),
    ("ÖZEL İNEGÖL KÜLTÜR DERSHANESİ", "İNEGÖL", "SİNANBEY MAH. NURİ DOĞRUL CAD. NO: 15 İÇ KAPI NO: 1 İNEGÖL / BURSA", "2247130505"),
    ("ÖZEL MODÜL MOD BEŞ DERSHANESİ", "NİLÜFER", "KONAK MAH. LEFKOŞE CAD. 7 NOLU BĞMZ BLOK NO: 10G NİLÜFER / BURSA", "2244520010"),
    ("ÖZEL BİR AKIN DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. TUNA CAD. AKSEL APT. SİTESİ NO: 161F NİLÜFER / BURSA", "5536335504"),
    ("ÖZEL PUSULA ÖĞRENCİ DERSHANESİ", "KARACABEY", "EMİRSULTAN MAH. 185. SK. MELİHA AĞRAŞ SİTESİ NO: 33 İÇ KAPI NO: 5 KARACABEY / BURSA", "2246600066"),
    ("ÖZEL YILDIRIM UZMAN KARİYER DERSHANESİ", "YILDIRIM", "DEĞİRMENÖNÜ MAH. ANKARAYOLU CAD. NO: 818A YILDIRIM / BURSA", "2248880999"),
    ("ÖZEL BEŞEVLER FARKLI KALİTELİ MODERN DERSHANESİ", "NİLÜFER", "BARIŞ MAH. DEFNE SK. NO: 28 İÇ KAPI NO: 4 NİLÜFER / BURSA", "2244521122"),
    ("ÖZEL İLK BAŞKENT DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. BÜRO BLOK NO: 174 İÇ KAPI NO: 4 NİLÜFER / BURSA", "5058251819"),
    ("ÖZEL GÜRSU ALTINKÜRE DERSHANESİ", "GÜRSU", "KURTULUŞ MAH. ERGUVAN SK. NO: 16 İÇ KAPI NO: 1 GÜRSU / BURSA", "5498401213"),
    ("ÖZEL BURSA FİZİKİ ARENA DERSHANESİ", "NİLÜFER", "ÜÇEVLER MAH. BAYRAKTEPE SK. NO: 17 İÇ KAPI NO: 1 NİLÜFER / BURSA", "2245029223"),
    ("ÖZEL NET DERSHANESİ", "İNEGÖL", "KEMALPAŞA MAH. ADNAN MENDERES BUL. NO: 28 İÇ KAPI NO: 1 İNEGÖL / BURSA", "2247112000"),
    ("ÖZEL YILDIRIM BEYOĞLU DERSHANESİ", "YILDIRIM", "DUAÇINARI MAH. 6.PINAR SK. NO: 6-8 YILDIRIM / BURSA", "5548751139"),
    ("ÖZEL BURSA BİREYSEL BAŞARI DERSHANESİ", "OSMANGAZİ", "KÜKÜRTLÜ MAH. 2.ÜSTÜN SK. B BLOK NO: 8A OSMANGAZİ / BURSA", "5358139460"),
    ("ÖZEL NİLÜFER ÜÇGEN DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. İZMİR YOLU CAD. NO: 115 İÇ KAPI NO: 1 NİLÜFER / BURSA", "5363572500"),
    ("ÖZEL ETKİN KLAS DERSHANESİ", "İNEGÖL", "OSMANİYE MAH. ZÜMRÜT SK. NO: 2 İÇ KAPI NO: 13 İNEGÖL / BURSA", "5058021389"),
    ("ÖZEL BURSA BEŞEVLER KÜLTÜR DERSHANESİ", "NİLÜFER", "KONAK MAH. BEŞEVLER CAD. KÜLTÜR ÖZEL EĞİTİM VE DERSHANECİLİK A.Ş. BLOK NO: 70 İÇ KAPI NO: 28 NİLÜFER / BURSA", "2244511112"),
    ("ÖZEL BURSA TÜRK DİLİ EDEBİYATI ARENA DERSHANESİ", "NİLÜFER", "ÜÇEVLER MAH. RİTİM SK. NO: 12A NİLÜFER / BURSA", "5072159992"),
    ("ÖZEL BURSA KARE DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. NO: 200B İÇ KAPI NO: 3 NİLÜFER / BURSA", "2242422999"),
    ("ÖZEL BURSA VARLIK DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. CAN(110) SK. NO: 2/1 İÇ KAPI NO: 5 NİLÜFER / BURSA", "5056972575"),
    ("ÖZEL BURSA ARENA MATEMATİK DERSHANESİ", "NİLÜFER", "ÜÇEVLER MAH. RİTİM SK. NO: 12 İÇ KAPI NO: 4 NİLÜFER / BURSA", "5072159992"),
    ("ÖZEL OFİS MATEMATİK DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. AVCI SK. B BLOK NO: 2-6BB NİLÜFER / BURSA", "5366531433"),
    ("ÖZEL VENÜS KAMPÜS TÜRK DİLİ VE EDEBİYATI DERSHANESİ", "OSMANGAZİ", "BAĞLARBAŞI MAH. 3.BARIŞ SK. B BLOK NO: 5A OSMANGAZİ / BURSA", "2242426868"),
    ("ÖZEL BURSA OPTİMUM DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. İZMİR YOLU CAD. NO: 116 İÇ KAPI NO: 3 NİLÜFER / BURSA", "2242474050"),
    ("ÖZEL İNEGÖL FİNAL FİZİK DERSHANESİ", "İNEGÖL", "SÜLEYMANİYE MAH. İSTİKLAL CAD. NO: 90 İÇ KAPI NO: 1 İNEGÖL / BURSA", "2247121000"),
    ("ÖZEL KAĞAN ER DERSHANESİ", "NİLÜFER", "BARIŞ MAH. DEFNE(140) SK. KAYA İŞ MERKEZİ BLOK NO: 12B NİLÜFER / BURSA", "5324789170"),
    ("ÖZEL NİLÜFER FARKLI KALİTELİ MODERN DERSHANESİ", "NİLÜFER", "FETHİYE MAH. ALEV(240) SK. CORNER PLUS İŞ MERKEZİ BLOK NO: 10 NİLÜFER / BURSA", "2244521122"),
    ("ÖZEL YENİŞEHİR DERSHANESİ", "YENİŞEHİR", "KURTULUŞ MAH. YÜZBAŞI İSMAİL HAKKI BEY BUL. ERTAT PRESTİJ EVLERİ E BLOK NO: 18E YENİŞEHİR / BURSA", "5549278008"),
    ("ÖZEL ENKA MATEMATİK DERSHANESİ", "NİLÜFER", "19 MAYIS MAH. MEŞELİ(350) SK. NO: 9 NİLÜFER / BURSA", "5366531433"),
    ("ÖZEL NİLÜFER UZMAN KARİYER DERECE DERSHANESİ", "NİLÜFER", "KONAK MAH. İZMİR YOLU CAD. DERSANE-1 SİTESİ NO: 91/1A1 NİLÜFER / BURSA", "5324635604"),
    ("ÖZEL SAYISAL MODÜL DERSHANESİ", "NİLÜFER", "BARIŞ MAH. FATİH SULTAN MEHMET BUL. AS DENİZ APT. NO: 1 NİLÜFER / BURSA", "2244526688"),
    ("ÖZEL KARACABEY DOĞRU CEVAP DERSHANESİ", "KARACABEY", "TABAKLAR MAH. 83. SK. DERSHANE SİTESİ NO: 3 KARACABEY / BURSA", "2246132020"),
    ("ÖZEL BEŞEVLER UZMAN KARİYER DERECE DERSHANESİ", "NİLÜFER", "KONAK MAH. İZMİR YOLU CAD. DERSANE-2 SİTESİ NO: 91/1A2 NİLÜFER / BURSA", "5324635604"),
    ("ÖZEL ÖZLÜCE MURAT DERSHANESİ", "NİLÜFER", "ALTINŞEHİR MAH. 163.(280) SK. A BLOK NO: 11A NİLÜFER / BURSA", "5550661683"),
    ("ÖZEL DEHA DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. KAYA(130) SK. NO: 3A NİLÜFER / BURSA", "5055893048"),
    ("ÖZEL DETAY HOCA DERSHANESİ", "NİLÜFER", "BALAT MAH. SIHHİYE CAD. 42.BAĞIMSIZ SİTESİ NO: 2B NİLÜFER / BURSA", "5368195996"),
    ("ÖZEL ORHANGAZİ ÇİZGİ FİZİK DERSHANESİ", "ORHANGAZİ", "ARAPZADE MAH. ORHANBEY CAD. NO: 92 ORHANGAZİ / BURSA", "5353082123"),
    ("ÖZEL KÖŞEGEN DERSHANESİ", "OSMANGAZİ", "KÜPLÜPINAR MAH. AYBER CAD. NO: 20 OSMANGAZİ / BURSA", "5359323315"),
    ("ÖZEL ORHANGAZİ ÇÖZÜM DERSHANESİ", "ORHANGAZİ", "CAMİİKEBİR MAH. ORHANBEY CAD. NO: 28 ORHANGAZİ / BURSA", "2245721010"),
    ("ÖZEL FORA DERSHANESİ", "NİLÜFER", "KARAMAN MAH. İZMİR YOLU CAD. NO: 84 NİLÜFER / BURSA", "5062774827"),
    ("ÖZEL ERTUĞRULKENT MATEMATİK DERSHANESİ", "NİLÜFER", "19 MAYIS MAH. SEVGİ CAD. NO: 5 NİLÜFER / BURSA", "5412979890"),
    ("ÖZEL YILDIRIM ALTINKÜRE DERSHANESİ", "YILDIRIM", "DEĞİRMENLİKIZIK MAH. 2.DALYAN SK. NO: 2 YILDIRIM / BURSA", "5330478739"),
    ("ÖZEL Pİ EKSEN DERSHANESİ", "NİLÜFER", "KONAK MAH. YASEMİN(120) SK. NO: 9 NİLÜFER / BURSA", "2244515573"),
    ("ÖZEL BURSA KÜLTÜR DERSHANESİ", "OSMANGAZİ", "KÜKÜRTLÜ MAH. MUDANYA CAD. TELEKOM LOJMANI NO: 99B OSMANGAZİ / BURSA", "2242332627"),
    ("ÖZEL YENİ NESİL DERSHANESİ", "OSMANGAZİ", "HAMİTLER MAH. ABDÜLHAMİD HAN CAD. NO: 12A OSMANGAZİ / BURSA", "5396901739"),
    ("ÖZEL MAVİ MEGA DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. YILDIRIM CAD. NO: 337 NİLÜFER / BURSA", "5325409987"),
    ("ÖZEL BOĞAZİÇİ OSMANGAZİ DERSHANESİ", "OSMANGAZİ", "HOCAALİZADE MAH. KONAKARDI SK. C BLOK NO: 4C OSMANGAZİ / BURSA", "5342920927"),
    ("ÖZEL MODERN DERSHANESİ", "YILDIRIM", "HACİVAT MAH. ANKARAYOLU CAD. NO: 507B YILDIRIM / BURSA", "5071373614"),
    ("ÖZEL ROTA BİREYSEL DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. İMECE SK. NO: 1 NİLÜFER / BURSA", "2244416377"),
    ("ÖZEL BURSA ATÖLYE DERSHANESİ", "MUDANYA", "ÇAĞRIŞAN MAH. KOCAÇINAR SK. NO: 10/B MUDANYA / BURSA", "2245493176"),
    ("ÖZEL BOĞAZİÇİ AS DERSHANESİ", "OSMANGAZİ", "HOCAALİZADE MAH. KONAKARDI SK. A BLOK NO: 4A OSMANGAZİ / BURSA", "5342920927"),
    ("ÖZEL İZNİK BÜYÜK DERSHANESİ", "İZNİK", "SELÇUK MAH. ATATÜRK CAD. ÖZPAŞ BLOK NO: 65 İZNİK / BURSA", "2247574242"),
    ("ÖZEL SERHAN EYLEMER DERSHANESİ", "MUDANYA", "BADEMLİ MAH. DOĞU SK. NO: 6 MUDANYA / BURSA", "2245490309"),
    ("ÖZEL BOĞAZİÇİ GRUP DERSHANESİ", "OSMANGAZİ", "HOCAALİZADE MAH. KONAKARDI SK. B BLOK NO: 4B OSMANGAZİ / BURSA", "5342920927"),
    ("ÖZEL OKUR DERSHANESİ", "NİLÜFER", "KONAK MAH. ÇAĞ SK. KONAK APT. BLOK NO: 5A NİLÜFER / BURSA", "5308805395"),
    ("ÖZEL GEZEGEN DERSHANESİ", "NİLÜFER", "KONAK MAH. YILDIRIM CAD. NO: 117 NİLÜFER / BURSA", "5433085040"),
    ("ÖZEL DEMİR BİLGİ DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. YILDIRIM(130) CAD. B BLOK NO: 254BA NİLÜFER / BURSA", "2245021868"),
    ("ÖZEL İNEGÖL MATEMATİK EVİM DERSHANESİ", "İNEGÖL", "SÜLEYMANİYE MAH. MİMAR SİNAN CAD. B BLOK NO: 78BA İNEGÖL / BURSA", "2247114747"),
    ("ÖZEL İNEGÖL FİNAL MATEMATİK DERSHANESİ", "İNEGÖL", "SÜLEYMANİYE MAH. İSTİKLAL CAD. NO: 90B İNEGÖL / BURSA", "2247121000"),
    ("ÖZEL KONAK FİZİK DERSHANESİ", "NİLÜFER", "KONAK MAH. BEŞEVLER CAD. NO: 93/1C NİLÜFER / BURSA", "2244529596"),
    ("ÖZEL ÖZLÜ FENOMEN DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. AVCI SK. C BLOK NO: 2-6CB NİLÜFER / BURSA", "2244512078"),
    ("ÖZEL KONAK KİMYA DERSHANESİ", "NİLÜFER", "KONAK MAH. BEŞEVLER CAD. NO: 93/1A NİLÜFER / BURSA", "2244529596"),
    ("ÖZEL VENÜS KAMPÜS KİMYA DERSHANESİ", "OSMANGAZİ", "BAĞLARBAŞI MAH. ŞHT.ER ALİ KIZILKAYA SK. NO: 3 OSMANGAZİ / BURSA", "2242426868"),
    ("ÖZEL KALİTEM DERSHANESİ", "İNEGÖL", "OSMANİYE MAH. ÇAĞLAR SK. NO: 4/6 İNEGÖL / BURSA", "2247116601"),
    ("ÖZEL BAŞARIDA SON NOKTA DERSHANESİ", "OSMANGAZİ", "AHMETPAŞA MAH. 298. SK. FOMARA İŞ MERKEZİ NO: 1 OSMANGAZİ / BURSA", "2242231661"),
    ("ÖZEL EĞİTMEN KARE DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. NO: 200B/B NİLÜFER / BURSA", "2242422999"),
    ("ÖZEL ULUDAĞ DERSHANESİ", "YILDIRIM", "KAZIM KARABEKİR MAH. 2.VATAN CAD. B BLOK NO: 232/1B YILDIRIM / BURSA", "2242453005"),
    ("ÖZEL HÜRRİYET BATIKENT DERSHANESİ", "OSMANGAZİ", "HÜRRİYET MAH. 8.UĞUR SK. NO: 16 OSMANGAZİ / BURSA", "2242492232"),
    ("ÖZEL ORHANGAZİ ÇİZGİ DERSHANESİ", "ORHANGAZİ", "ARAPZADE MAH. BAHÇELİ EVLER SK. NO: 1A ORHANGAZİ / BURSA", "5312828761"),
    ("ÖZEL BEŞEVLER KÜLTÜR DERSHANESİ", "NİLÜFER", "KONAK MAH. YASEMİN(120) SK. KÜLTÜR ÖZEL EĞİTİM BLOK NO: 4 NİLÜFER / BURSA", "2242497980"),
    ("ÖZEL BİLGİ BAŞARI MATEMATİK DERSHANESİ", "NİLÜFER", "KONAK MAH. MERKEZ(120) SK. NO: 33-35 NİLÜFER / BURSA", "2244535380"),
    ("ÖZEL İZNİK UĞUR DERSHANESİ", "İZNİK", "MUSTAFA KEMAL PAŞA MAH. ATATÜRK CAD. NO: 101 İZNİK / BURSA", "2247578101"),
    ("ÖZEL İNEGÖL KALİTE DERSHANESİ", "İNEGÖL", "KEMALPAŞA MAH. ADNAN MENDERES BUL. NO: 8 İNEGÖL / BURSA", "2247151117"),
    ("ÖZEL BURSA UZMAN KARİYER DERSHANESİ", "OSMANGAZİ", "ALACAMESCİT MAH. OKÇULAR SK. OKÇULAR ÇARŞISI NO: 3 OSMANGAZİ / BURSA", "2242209584"),
    ("ÖZEL ORHANGAZİ BİLİM DERSHANESİ", "ORHANGAZİ", "CAMİİKEBİR MAH. TOZKOPARAN CAD. NO: 10 ORHANGAZİ / BURSA", "2245731200"),
    ("ÖZEL BİREY DERSHANESİ", "YILDIRIM", "ERİKLİ MAH. EĞRİYOL SK. NO: 1 YILDIRIM / BURSA", "2243718687"),
    ("ÖZEL BİLGE DERSHANESİ", "KESTEL", "KALE MAH. BURSA CADDESİ NO: 6 KESTEL / BURSA", "5325562337"),
    ("ÖZEL BURSA ÇÖZÜM DERSHANESİ", "OSMANGAZİ", "BAĞLARBAŞI MAH. 1.SEDİR SK. B1 BLOK NO: 1-3 OSMANGAZİ / BURSA", "2242494970"),
    ("ÖZEL BURSA MATEMATİK DERSHANESİ", "NİLÜFER", "19 MAYIS MAH. KUŞKONMAZ SK. K BLOK NO: 1K NİLÜFER / BURSA", "5374512467"),
    ("ÖZEL YAVUZ ERŞAT KABUKCU DERSHANESİ", "NİLÜFER", "BARIŞ MAH. DEFNE(140) SK. GÜRSES İŞ MERKEZİ NO: 32 NİLÜFER / BURSA", "2249994099"),
    ("ÖZEL ALTIPARMAK DERSHANESİ", "OSMANGAZİ", "İNTİZAM MAH. ALTIPARMAK CAD. NO: 52 OSMANGAZİ / BURSA", "2242212776"),
    ("ÖZEL ETKİN GRUP DERSHANESİ", "İNEGÖL", "OSMANİYE MAH. ALTAY CAD. NO: 16 İNEGÖL / BURSA", "2247150687"),
    ("ÖZEL KAVRAM DERSHANESİ", "İNEGÖL", "KEMALPAŞA MAH. YEŞİL ÇAYIR CAD. B BLOK NO: 77B İNEGÖL / BURSA", "2242402240"),
    ("ÖZEL KÜPKÖK DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. YILDIRIM CAD. NO: 330 NİLÜFER / BURSA", "2244431531"),
    ("ÖZEL FREKANS DERSHANESİ", "NİLÜFER", "KONAK MAH. YILDIRIM CAD. NO: 152B NİLÜFER / BURSA", "2244517714"),
    ("ÖZEL ETKİN GRUP KARACABEY DERSHANESİ", "KARACABEY", "ABDULLAHPAŞA MAH. FARUK KATIRCI SK. NO: 7 KARACABEY / BURSA", "2246600090"),
    ("ÖZEL ÖZLÜCE FİNAL DERSHANESİ", "NİLÜFER", "19 MAYIS MAH. KUŞKONMAZ SK. NO: 13 NİLÜFER / BURSA", "2244131018"),
    ("ÖZEL YENİŞEHİR KALİTE DERSHANESİ", "YENİŞEHİR", "YENİGÜN MAH. SERAP SK. FİRDES MUTAF SİTESİ B BLOK NO: 3/1A YENİŞEHİR / BURSA", "2247723335"),
    ("ÖZEL BURSA UĞUR DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. İZMİR YOLU CAD. NO: 126 NİLÜFER / BURSA", "2242492400"),
    ("ÖZEL KONAK DERSHANESİ", "NİLÜFER", "KONAK MAH. YALI SK. NO: 13A NİLÜFER / BURSA", "2244529596"),
    ("ÖZEL OSMANGAZİ KAVRAM DERSHANESİ", "OSMANGAZİ", "AKPINAR MAH. 367. SK. NO: 3 OSMANGAZİ / BURSA", "2242256349"),
    ("ÖZEL BİLGİTEPE DERSHANESİ", "NİLÜFER", "KONAK MAH. 1.AKÇAY SK. NO: 16 NİLÜFER / BURSA", "5321323307"),
    ("ÖZEL BİLGİ DÜNYASI DERSHANESİ", "MUDANYA", "HALİTPAŞA MAH. ŞEHİT ÖMER HALİSDEMİR CAD. BİREL 2 B BLOK NO: 9A MUDANYA / BURSA", "5359469972"),
    ("ÖZEL GÜZEL DERSHANESİ", "OSMANGAZİ", "AKPINAR MAH. ŞHT.MÜMİN MUTLU SK. A BLOK NO: 2 OSMANGAZİ / BURSA", "2244521122"),
    ("ÖZEL KAZANIM DERSHANESİ", "OSMANGAZİ", "AKPINAR MAH. ŞHT.MÜMİN MUTLU SK. A BLOK NO: 2 OSMANGAZİ / BURSA", "2244521122"),
    ("ÖZEL ŞENTÜRK DERSHANESİ", "MUSTAFAKEMALPAŞA", "HAMZABEY MAH. SOKULLU SK. NO: 17 MUSTAFAKEMALPAŞA / BURSA", "5052955527"),
    ("ÖZEL FARKLI KALİTELİ MODERN DERSHANESİ", "NİLÜFER", "BEŞEVLER MAH. YILDIRIM(130) CAD. A BLOK NO: 286A NİLÜFER / BURSA", "2244522888"),
    ("ÖZEL ONUR ÇELİK DERSHANESİ", "MUDANYA", "HALİTPAŞA MAH. GÜR SK. ORKUN SİTESİ A BLOK NO: 3 MUDANYA / BURSA", "2245430838"),
    ("ÖZEL BURSA YEDİİKLİM DERSHANESİ", "OSMANGAZİ", "ALACAMESCİT MAH. ÇANCILAR CAD. NO: 21 OSMANGAZİ / BURSA", "2242239684"),
    ("ÖZEL BURSA FİNAL DERSHANESİ", "OSMANGAZİ", "AKTARHÜSSAM MAH. 1.DEĞİRMEN SK. ELİT İŞ MERKEZİ NO: 4 OSMANGAZİ / BURSA", "2242230808"),
    ("ÖZEL ARZU TANER DERSHANESİ", "NİLÜFER", "ÜÇEVLER MAH. BURÇAK(220) SK. NO: 4B NİLÜFER / BURSA", "2244437314"),
    ("ÖZEL BİREYSEL DERSHANESİ", "OSMANGAZİ", "AKPINAR MAH. ŞHT.MÜMİN MUTLU SK. A BLOK NO: 2 OSMANGAZİ / BURSA", "2244521122"),
    ("ÖZEL SERKAN KARE DERSHANESİ", "NİLÜFER", "KONAK MAH. YILDIRIM CAD. ŞEKER APT. NO: 91B NİLÜFER / BURSA", "5397957566"),
    ("ÖZEL BEŞEVLER BEYAZ DERSHANESİ", "NİLÜFER", "KONAK MAH. İZMİR YOLU CAD. NO: 85 NİLÜFER / BURSA", "2244535595"),
    ("ÖZEL AKGÜN DERSHANESİ", "NİLÜFER", "BARIŞ MAH. İZMİR YOLU CAD. NO: 182 NİLÜFER / BURSA", "2244512825"),
    ("ÖZEL FİNAL DERSHANESİ", "NİLÜFER", "İHSANİYE MAH. ALAGEYİK(110) SK. GÜVEN APT. NO: 1/2 NİLÜFER / BURSA", "2242497979"),
    ("ÖZEL OSMANGAZİ ONADIM DERSHANESİ", "OSMANGAZİ", "DOĞANBEY MAH. DOĞANBEY CAD. ÖRTAŞ İŞHANI NO: 7 OSMANGAZİ / BURSA", "2242256401"),
    ("ÖZEL ONADIM DERSHANESİ", "NİLÜFER", "FETHİYE MAH. GAZİ(240) SK. OFİS B BLOK NO: 9B1 NİLÜFER / BURSA", "2242434353"),
    ("ÖZEL 19 MAYIS DERSHANESİ", "NİLÜFER", "19 MAYIS MAH. UĞUR MUMCU BUL. NO: 130 NİLÜFER / BURSA", "2244130202"),
]


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:88] or "dershane"


def norm_ilce(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    low = t.lower().replace("i", "ı")
    for key, val in ILCE_NORM.items():
        if key == low or key in low or low in key:
            return val
    return t.title()


def norm_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 10:
        return "0" + d
    if len(d) == 11 and d.startswith("0"):
        return d
    return (raw or "").strip()[:40]


def display_title(meb_title: str) -> str:
    t = (meb_title or "").strip()
    if t.upper().startswith("ÖZEL "):
        t = t[5:].strip()
    return t.title() if t.isupper() else t


def meb_rows_to_json() -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for title, ilce_raw, address, phone in MEB_TABLE:
        slug = slugify(title)
        base = slug
        i = 2
        while slug in seen:
            slug = f"{base}-{i}"
            i += 1
        seen.add(slug)
        ilce = norm_ilce(ilce_raw)
        ph = norm_phone(phone)
        nice = display_title(title)
        out.append(
            {
                "slug": slug,
                "title": nice,
                "subcategory": "dershane",
                "price_band": "Özel",
                "ilce": ilce,
                "address": address.strip(),
                "phone": ph,
                "web": "",
                "hours_text": "08:00 – 21:00",
                "blurb": f"Dershane · {ilce} · MEB kayıtlı",
                "tags": ["dershane", "lgs", "yks", "meb"],
                "featured": False,
                "source": "meb",
                "extra": {"meb_title": title, "programs": ["LGS", "YKS", "TYT-AYT"]},
            }
        )
    return out


def load_ozel_egitim() -> list[dict]:
    if os.path.isfile(OZEL_PATH):
        return json.loads(open(OZEL_PATH, encoding="utf-8").read())
    return []


def load_geocode_cache() -> dict:
    if os.path.isfile(GEOCODE_CACHE):
        return json.loads(open(GEOCODE_CACHE, encoding="utf-8").read())
    return {}


def save_geocode_cache(cache: dict) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(GEOCODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_rows(rows: list[dict], *, limit: int = 200) -> int:
    cache = load_geocode_cache()
    filled = 0
    for r in rows:
        if r.get("lat") not in (None, "") and r.get("lng") not in (None, ""):
            continue
        if filled >= limit:
            break
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        q = f"{addr}, Bursa, Türkiye"
        if q in cache:
            hit = cache[q]
        else:
            url = NOMINATIM + "?" + urllib.parse.urlencode(
                {"q": q, "format": "json", "limit": 1, "countrycodes": "tr"}
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode())
                hit = data[0] if data else None
            except Exception:
                hit = None
            cache[q] = hit
            save_geocode_cache(cache)
            time.sleep(1.05)
        if hit:
            r["lat"] = float(hit["lat"])
            r["lng"] = float(hit["lon"])
            filled += 1
    return filled


def merge_into_schools(extra_rows: list[dict]) -> int:
    if not os.path.isfile(SCHOOLS_PATH):
        return 0
    schools = json.loads(open(SCHOOLS_PATH, encoding="utf-8").read())
    by_slug = {r["slug"]: r for r in schools}
    by_phone_title: dict[tuple[str, str], dict] = {}
    for r in schools:
        key = (re.sub(r"\D", "", r.get("phone") or ""), (r.get("title") or "").lower()[:24])
        if key[0]:
            by_phone_title[key] = r
    added = 0
    for row in extra_rows:
        slug = row["slug"]
        if slug in by_slug:
            base = by_slug[slug]
            for k, v in row.items():
                if v not in (None, "", [], {}):
                    base[k] = v
            continue
        dup = by_phone_title.get(
            (re.sub(r"\D", "", row.get("phone") or ""), (row.get("title") or "").lower()[:24])
        )
        if dup and row.get("phone"):
            for k, v in row.items():
                if k == "slug":
                    continue
                if v not in (None, "", [], {}):
                    dup[k] = v
            if row.get("subcategory") == "dershane":
                dup["subcategory"] = "dershane"
            continue
        by_slug[slug] = row
        added += 1
    merged = list(by_slug.values())
    merged.sort(key=lambda r: (0 if r.get("subcategory") == "dershane" else 1, r.get("title") or ""))
    with open(SCHOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return added


def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    rows = meb_rows_to_json()
    rows.extend(load_ozel_egitim())
    if "--geocode" in sys.argv:
        n = geocode_rows(rows, limit=250 if "--all" in sys.argv else 80)
        print(f"Geocode: {n} koordinat dolduruldu", flush=True)
    with open(MEB_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Yazıldı: {MEB_PATH} ({len(rows)} kayıt)", flush=True)
    if "--merge" in sys.argv:
        added = merge_into_schools(rows)
        print(f"schools.json birleşti · yeni {added} kayıt", flush=True)


if __name__ == "__main__":
    main()
