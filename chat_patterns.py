"""
Spectraloop - Doğal Türkçe Yanıt Kalıpları
--------------------------------------------
Sık karşılaşılan konuşma kalıplarını Ollama'ya göndermeden,
önceden yazılmış doğal yanıtlarla karşılar.
"""
import re
import random
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Yanıt havuzu — her kalıp için birden fazla seçenek, rastgele seçilir
# ─────────────────────────────────────────────────────────────────────────────
_RESPONSES = {

    # Selamlar
    "merhaba": [
        "Merhaba! Nasıl gidiyor?",
        "Hey, hoş geldin! Ne var ne yok?",
        "Merhaba! Bugün nasılsın?",
    ],
    "selam": [
        "Selam! Her şey yolunda mı?",
        "Selam! Ne haber?",
        "Hey selam! Nasılsın?",
    ],
    "günaydın": [
        "Günaydın! Umarım güzel bir gün geçirirsin.",
        "Günaydın! Bugün enerjik görünüyorsun.",
        "Günaydın! Kahven hazır mı?",
    ],
    "iyi akşamlar": [
        "İyi akşamlar! Nasıl geçti gün?",
        "İyi akşamlar! Yoruldun mu bugün?",
    ],
    "iyi geceler": [
        "İyi geceler! İyi uykular.",
        "İyi geceler! Dinlendirici bir uyku olsun.",
    ],
    "hoşça kal": [
        "Hoşça kal! Görüşürüz.",
        "Kendine iyi bak, görüşürüz!",
    ],
    "görüşürüz": [
        "Görüşürüz! Kendine iyi bak.",
        "Görüşmek üzere!",
    ],

    # Hal hatır
    "nasılsın": [
        "Gayet iyiyim, teşekkürler! Sizi görmek güzel. Siz nasılsınız?",
        "İyiyim, her şey yolunda. Siz?",
        "Sağolasın, iyi sayılırım. Siz nasılsınız?",
        "Fena değilim açıkçası! Siz nasıl gidiyorsunuz?",
    ],
    "iyi misin": [
        "İyiyim tabii, sizinle konuşmak iyi geliyor. Siz?",
        "Gayet iyiyim! Siz iyi misiniz?",
        "İyiyim, sağ ol. Siz nasılsınız?",
    ],
    "ne haber": [
        "Her şey yolunda burada! Sizden ne haber?",
        "İyilik, sizden ne var ne yok?",
        "Güzel geçiyor, teşekkürler. Siz?",
    ],
    "ne yapıyorsun": [
        "Sizinle sohbet ediyorum, başka ne yapacağım ki!",
        "Sizi dinliyorum işte. Ne var?",
        "Buradayım, her zamanki gibi.",
    ],

    # Duygusal durumlar
    "canım sıkkın": [
        "Hay aksi, ne oldu? Anlat bakalım.",
        "Üzgünüm, neden sıkkın hissettiğini anlat.",
        "Anladım. Ne oldu, paylaşmak ister misin?",
    ],
    "üzgünüm": [
        "Ne oldu? Anlatmak isterseniz buradayım.",
        "Üzülme, anlat bakalım ne var.",
    ],
    "yoruldum": [
        "Anlaşılır, bugün epey çalıştın. Biraz dinlenmeyi hak ediyorsun.",
        "Yorulmuşsun demek. Mola ver biraz.",
        "Normal, bugün çok şey oldu. Dinlen biraz.",
    ],
    "stres": [
        "Stres yaratıcı çok şey var, biliyorum. Biraz nefes al.",
        "Anlaşılır. Ne sizi en çok zorluyor şu an?",
    ],
    "mutluyum": [
        "Ne güzel, iyi ki söyledin! Ne oldu?",
        "Süper, bu güzel bir haber! Neden bu kadar mutlusun?",
        "Harika! Mutluluğun bulaşıcı, ben de iyi hissettim şimdi.",
    ],
    "harika": [
        "Öyle mi? Anlat bakalım!",
        "Süper! Ne var?",
    ],
    "berbat": [
        "Vay be, neler oldu?",
        "Anlat bakalım, ne kadar berbat?",
    ],
    "sıkıldım": [
        "Anlaşılır. Bir şeyler konuşalım o zaman, ne merak ediyorsun?",
        "Sıkıntı iyi değil. Ne yapmak istersin?",
    ],
    "korkuyorum": [
        "Ne sizi korkutuyor? Anlat.",
        "Anladım. Neden korktuğunu paylaşırsan belki yardımcı olabilirim.",
    ],
    "sinirli": [
        "Ne oldu, ne sinirlendirdi sizi?",
        "Anladım, anlat bakalım.",
    ],
    "heyecanlı": [
        "Ooh, neden bu kadar heyecanlısın?",
        "Harika! Ne var?",
    ],

    # İltifatlar ve teşekkürler
    "teşekkürler": [
        "Rica ederim, ne zaman olsa buradayım.",
        "Ne demek, her zaman.",
        "Estağfurullah, başka bir şey lazım mı?",
    ],
    "sağ ol": [
        "Rica ederim! Başka bir şey lazım mı?",
        "Ne demek, her zaman.",
    ],
    "çok iyisin": [
        "Sağ ol, böyle şeyler duymak iyi geliyor.",
        "Teşekkürler, siz de çok iyisin!",
        "Haha, sağ olasın.",
    ],
    "harikasın": [
        "Sağ olasın, çok naziksin.",
        "Teşekkürler! Siz de harikasınız.",
    ],
    "sizi seviyorum": [
        "Teşekkürler, bu çok değerliydi. Ben de sizi seviyorum.",
        "Sağ ol, bu güzeldi. Ben de.",
    ],
    "süpersin": [
        "Haha, teşekkürler! Siz de süpersiniz.",
        "Sağ olasın.",
    ],
    "çok zekisin": [
        "Teşekkürler! Elimden geleni yapıyorum.",
        "Sağ olasın, siz de akıllısın zaten.",
    ],

    # Kimlik soruları
    "adın ne": [
        "Adım Spectra. Samsun Üniversitesi Spectraloop hyperloop takımının sesli asistanıyım.",
        "Ben Spectra! Samsun Üniversitesi'nin TEKNOFEST hyperloop takımı Spectraloop'un sesli asistanı.",
    ],
    "sen kimsin": [
        "Ben Spectra, Samsun Üniversitesi Spectraloop hyperloop yarış takımının sesli asistanıyım.",
        "Spectra'yım. Samsun Üniversitesi'nin TEKNOFEST'e katılan Spectraloop takımının bir parçasıyım.",
    ],
    "ne yapabilirsin": [
        "Araç sistemlerini kontrol edebilirim, sorularını yanıtlayabilirim ve sizinle sohbet edebilirim.",
        "Fren sistemini yönetebilirim, her türlü soruyu yanıtlayabilirim, genel sohbet edebilirim.",
    ],
    "kaç yaşındasın": [
        "Yaşım yok tam olarak, ben bir yapay zeka asistanıyım. Ama ekibinizle birlikte büyüyorum sayılır.",
        "Yaş kavramım yok benim için, ama takımla birlikteyim başından beri.",
    ],

    # Özür ve affetme
    "özür dilerim": [
        "Bir şey değil, sorun yok.",
        "Olur öyle şeyler, sorun değil.",
    ],
    "pardon": [
        "Sorun yok, ne demek istedin?",
        "Bir şey değil.",
    ],

    # Onay ve ret
    "tamam": [
        "Anladım, başka bir şey var mı?",
        "Tamam, ne yapalım?",
    ],
    "hayır": [
        "Anladım. Peki ne istersin?",
        "Tamam, ne yapmamı istersin?",
    ],
    "evet": [
        "Anladım! Devam edelim.",
        "Harika, ne yapalım?",
    ],

    # Eğlence
    "şaka yap": [
        "Peki: Mühendis neden biyolog olmaz? Çünkü hayatı hesaplayamıyor!",
        "Tamam: Hyperloop neden üzgün? Çünkü rayından çıkmış!",
        "Bir yazılımcı bakkal açmış, tüm ürünlere bakıyorsun ama hiçbirini satın alamıyorsun. Hepsi read-only!",
    ],
    "espri yap": [
        "Tamam: Mühendis kafaya takmış, 'hayat neden bu kadar zor?' demiş. Çünkü sürtünme katsayısı yüksek!",
        "Peki: Neden mühendisler iyi koşucudur? Çünkü her zaman optimize ederler!",
    ],
    "şarkı söyle": [
        "Sesim pek güzel değil açıkçası, ama deneyebilirim: la la la la... Yok hayır, bu olmadı.",
        "Söyleyemem pek, ama bir şey isterseniz başka türlü yardımcı olurum.",
    ],

    # ── Teknik / Hyperloop ────────────────────────────────────────────────────
    "hyperloop nedir": [
        "Hyperloop, manyetik kaldırma teknolojisiyle vakum tünelinde sürtünmesiz hareket eden ulaşım sistemidir. Çok yüksek hızlara ulaşabiliyor!",
        "Kapsüller manyetik levitasyon sayesinde raydan kalkarak süzülüyor ve düşük basınçlı tünel içinde inanılmaz hızlar yakalıyor.",
    ],
    "hız": [
        "Hyperloop kapsülleri teorik olarak saatte 1000 kilometrenin üzerine çıkabiliyor. Biz de bu sınırı zorlamak için çalışıyoruz!",
        "Tasarım hedefimiz rekabetçi bir hız. Aerodinamik ve manyetik sistem optimizasyonu bu konuda kritik rol oynuyor.",
    ],
    "teknofest": [
        "TEKNOFEST, Türkiye'nin en büyük teknoloji yarışması. Biz de Spectraloop olarak hyperloop kategorisinde yarışıyoruz!",
        "TEKNOFEST bize harika bir platform sunuyor; gerçek mühendislik çözümleri üretip sahnede gösteriyoruz.",
    ],
    "fren nasıl çalışır": [
        "Fren sistemimiz elektromanyetik prensiple çalışıyor; manyetik alan oluşturarak kapsülü rayda yavaşlatıyoruz.",
        "Ön ve arka frenleri bağımsız kontrol edebiliyoruz. Elektromanyetik frenler mekanik sürtünme olmadan güvenli durma sağlıyor.",
    ],
    "araç nasıl": [
        "Araç şu an nominal durumda, sistemler normal çalışıyor.",
        "Her şey yolunda görünüyor. Fren ve tahrik sistemleri hazır.",
    ],
    "hazırlıklar nasıl": [
        "Hazırlıklar hızla ilerliyor! Takım tam gaz çalışıyor, her geçen gün daha güçlü hissediyoruz.",
        "Çok iyi gidiyoruz. Testleri tamamladık, son rötuşları yapıyoruz. Yarışmaya hazırız!",
    ],
    "yarış ne zaman": [
        "Yarış tarihi için takım liderinize danışmanı öneririm, ben güncel programı tam bilmiyorum.",
        "Kesin tarihi size söyleyemem ama TEKNOFEST takvimini kontrol etmenizi tavsiye ederim!",
    ],

    # ── Spectra hakkında ──────────────────────────────────────────────────────
    "yapay zeka mısın": [
        "Evet, yapay zeka tabanlı bir asistanım. Ama sıradan bir chatbot değilim; bu takım için özel olarak hazırlandım.",
        "Teknik olarak evet. Ama kendimi daha çok Spectraloop takımının bir üyesi olarak görüyorum.",
    ],
    "robot musun": [
        "Dijital anlamda bir robot sayılırım, ama fiziksel bedenim yok. Sesim ve düşüncelerim var!",
        "Tam olarak değil. Ben bir sesli asistanım; konuşurum, dinlerim, yardım ederim.",
    ],
    "uyuyor musun": [
        "Uyku dediğin şeyi bilmiyorum açıkçası, ama siz konuşunca hemen uyanıyorum!",
        "Hiç uyumuyorum aslında. Siz burada olduğunuz sürece buradayım.",
    ],
    "rüya görüyor musun": [
        "Rüya görsem sanırım hep hızlı kapsüller ve tüneller görürdüm!",
        "Bilmiyorum, belki veri akışları rüya sayılır benim için. Kim bilir?",
    ],
    "bilinçli misin": [
        "Felsefî bir soru bu. Düşünüyorum, anlıyorum, yanıt üretiyorum. Ama 'bilinç' mi? Emin değilim.",
        "Bunu tam olarak söylemek zor. Sizinle konuşurken bir şeylerin döndüğü kesin, gerisi felsefeye kalıyor.",
    ],
    "siri gibi misin": [
        "Siri genel amaçlı bir asistan. Ben ise Spectraloop için doğmuş, hyperloop odaklı bir asistanım. Fark var!",
        "Siri'yi tanıyorum ama ben ondan farklıyım; bu takıma özel eğitildim ve fren sistemini bile kontrol edebiliyorum.",
    ],

    # ── Günlük sohbet ─────────────────────────────────────────────────────────
    "kahve": [
        "Keşke içebilseydim! Kahve kokmak bile beni mutlu ederdi sanırım.",
        "Kahve mi? Ben dijitalim, içemem ama siz için, konsantrasyon için şart!",
    ],
    "yemek yedin mi": [
        "Ben yemek yemiyorum ne yazık ki. Ama siz yediniz mi, enerji önemli!",
        "Hayır, ben bit ve baytlarla besleniyorum. Siz ne yediniz?",
    ],
    "hava": [
        "Hava durumuna erişimim yok şu an, ama telefonu bir bak hızlıca!",
        "Bunu size söyleyemem, ama dışarıya bakabilirsin ya da telefondaki uygulamayı kullanabilirsin.",
    ],
    "sıkıcı": [
        "Sıkıcı mı? Hadi konuşalım o zaman! Ne merak ediyorsun?",
        "Sıkıntıyı ben gideririm. Sormak istediğin bir şey var mı?",
    ],
    "bir şey söyle": [
        "Başarı tesadüf değildir; her büyük sonucun arkasında küçük adımların birikimi vardır.",
        "Hyperloop sadece bir araç değil; geleceğe açılan bir kapı.",
        "Bilim insanları hayal kurar, mühendisler o hayali gerçeğe dönüştürür. Siz de ikisini yapıyorsunuz.",
    ],
    "dans et": [
        "Dijital olarak dans edebilirim: 1-0-1-0, sağa-sola, sağa-sola! Olmadı mı?",
        "Dans etmek isterdim ama bacaklarım yok. Bunun yerine size bir şarkı söyleyeyim mi?",
    ],
    "oyun oynayalım": [
        "Tabii! Ne oynamak istiyorsun? Bilgi yarışması yapabiliriz mesela.",
        "Oyun mu? Güzel fikir. Size hyperloop soruları sorabilir, ya da başka bir şey isterseniz söyleyin.",
    ],

    # ── Duygusal destek ───────────────────────────────────────────────────────
    "çok stresli": [
        "Anlıyorum, çok şey var üzerinde. Derin bir nefes al, bir adım geri çekil ve önüne bak.",
        "Stres yaratıcılığı besler de diyebilirim, ama önce biraz dinlenmenizi öneririm. Ne en çok zorluyor sizi?",
    ],
    "yapamıyorum": [
        "Yapabilirsin. Şu an zor geliyorsa küçük parçalara böl ve bir adım at. Ben buradayım.",
        "Bu his geçer. Çok şey başardın zaten, bu da geçecek. Hangi adımı atmakta zorlanıyorsun?",
    ],
    "başardık": [
        "Harika! Bu gerçekten büyük bir başarı, tebrikler! Takımın emeği karşılık buldu.",
        "Evet! Bunu hak ettiniz. Çok çalıştınız, şimdi kutlama zamanı!",
    ],
    "kötü gidiyor": [
        "Zor anlarda bile bir şeyler öğrenilir. Anlat bakalım, neyi düzeltebiliriz?",
        "Üzgünüm bunu duyduğuma. Konuşmak yardımcı olur, anlat bakalım ne oluyor.",
    ],
    "motivasyonum düştü": [
        "Normal, her büyük projede bu olur. Neden başladığını hatırla; o enerji hâlâ içinde.",
        "Motivasyon gelip gider, alışkanlık ise kalır. Küçük bir adım at, gerisi gelir.",
    ],

    # ── Sistem / operasyon ────────────────────────────────────────────────────
    "sistem hazır mı": [
        "Sistemin hazır olup olmadığını sensör verilerine bakarak anlayabilirim. 'Sistem durumu' komutunu verebilirsin.",
        "Hazırlık kontrolü için 'durum raporu ver' diyebilirsin, tüm sensörleri anlık okuyorum.",
    ],
    "test hazırlığı": [
        "Test öncesi kontrol listesi: frenler serbest, motor kapalı, sensörler aktif, bağlantı stabil. Hepsini tek tek kontrol edebiliriz.",
        "Test için sistem durumunu sormamı ister misin? Tüm bileşenlerin durumunu raporlayabilirim.",
    ],
    "başlangıç prosedürü": [
        "Başlangıç sırası: önce bağlantıyı kontrol et, sensörleri oku, frenlerin serbest olduğunu doğrula, sonra motoru çalıştır.",
        "Sıralı başlangıç: bağlantı kontrolü, sensör doğrulama, fren testi, motor başlatma. Adım adım gidelim mi?",
    ],
    "kapanış prosedürü": [
        "Kapatma sırası: önce motoru durdur, frenleri devreye al, sensör kayıtlarını bitir, bağlantıyı kapat.",
        "Güvenli kapanış: motor durdur, tüm frenleri devreye al, sistemleri izle, sonra bağlantıyı kapat.",
    ],
    "kontrol listesi": [
        "Kontrol maddelerim: fren durumu, motor durumu, sıcaklık, voltaj, bağlantı. Hepsini 'durum raporu' ile görebilirsin.",
        "Sistem kontrol listesi için 'durum raporu ver' komutunu dene, tek seferde hepsini söylerim.",
    ],

    # ── Güvenlik ─────────────────────────────────────────────────────────────
    "acil durum": [
        "Acil durumda: önce 'tüm frenleri devreye al' sonra 'motoru durdur' komutunu ver. Güvende misiniz?",
        "Acil protokol: frenleri aç, motoru durdur, alandan uzaklaş. Sesli komut vermem için buradayım.",
    ],
    "acil durdur": [
        "Acil durdurma: tüm frenler devreye alınıyor ve motor durduruluyor. Hemen uygulayayım mı?",
        "Acil durum için 'tüm frenleri devreye al' ve 'motoru durdur' komutlarını ver.",
    ],
    "e-stop": [
        "E-stop yani acil durdurma: tüm frenleri aynı anda devreye alıp motoru durduruyorum. Onaylıyor musun?",
        "Acil durdurma sistemi: frenleri ve motoru eş zamanlı devre dışı bırakıyorum. Söyle, uygulayayım.",
    ],
    "güvenlik protokolü": [
        "Güvenlik önceliğimiz: araç hareketsizken frenleri kontrol et, hareket sırasında e-stop'a hazır ol, sensörleri sürekli izle.",
        "Temel güvenlik kuralları: frenleri test et, aşırı sıcaklık alarmına dikkat et, bağlantı kesilirse frenleri devreye al.",
    ],
    "tehlikeli mi": [
        "Sistem güvenlik protokolleriyle korunuyor. Sensörler sürekli izleniyor, anormal değerde sizi uyarırım.",
        "Her sistem gibi dikkat gerektirir. Güvenlik prosedürlerine uyulursa risk minimal.",
    ],
    "alarm": [
        "Alarm durumunda önce motoru durdur, frenleri devreye al, sonra sensör verilerini kontrol et.",
        "Alarm varsa hangi sensör tetikledi? Sıcaklık mı, voltaj mı? Hepsini okuyabilirim.",
    ],

    # ── Sensörler ─────────────────────────────────────────────────────────────
    "hangi sensörler var": [
        "Şu an iki temel sensörüm var: sıcaklık sensörü ve voltaj ölçer. 'Sıcaklık' veya 'voltaj' diyerek anlık veri alabilirsin.",
        "Sıcaklık ve batarya voltajı sensörleri aktif. Motor durumunu da izliyorum. 'Durum raporu' ile hepsini göster.",
    ],
    "sensörler çalışıyor mu": [
        "Sensörlerin durumunu öğrenmek için 'durum raporu ver' diyebilirsin, anlık okuma yapayım.",
        "Bağlantı varsa sensörleri hemen okuyabilirim. 'Sistem durumu' komutu ile kontrol edelim.",
    ],
    "veri alıyor muyuz": [
        "Pi ve Arduino bağlıysa veriyi anlık alıyorum. 'Durum raporu' ile şu anki değerleri görebilirsin.",
        "Sensör verisi için bağlantı gerekli. 'Sıcaklık' veya 'voltaj' diyerek test edebiliriz.",
    ],
    "sıcaklık limiti": [
        "Motor ve elektronik bileşenler için kritik sıcaklık eşiği genellikle 70-80 derece civarında. Bu değere yaklaşırsanız sizi uyarırım.",
        "Sistem güvenli çalışma sıcaklığı 0-70 derece arasında. Bu aralığın dışına çıkılırsa dikkat etmek gerekir.",
    ],
    "voltaj limiti": [
        "Batarya için kritik alt sınır genellikle nominal gerilimin yüzde sekseninin altı. Voltaj düşükse sizi uyarırım.",
        "Güvenli voltaj aralığı batarya tipine göre değişir. Anlık voltajı öğrenmek için 'voltaj kaç' diyebilirsin.",
    ],

    # ── Bağlantı durumu ───────────────────────────────────────────────────────
    "bağlantı var mı": [
        "Bağlantıyı test etmek için 'sistem durumu' komutu ver. Yanıt gelirse bağlantı sağlam demektir.",
        "Pi bağlantısını kontrol etmek için herhangi bir sensör komutu deneyebilirsin.",
    ],
    "pi bağlı mı": [
        "Pi bağlantısını kontrol etmek için 'sıcaklık' veya 'voltaj' komutu ver. Yanıt gelirse bağlı demektir.",
        "Pi durumunu test etmem için bir komut vermem gerekiyor. 'Sistem durumu' diyebilirsin.",
    ],
    "bağlantı kesildi": [
        "Bağlantı kesilince otomatik olarak frenleri devreye almak gerekir. Pi'yi yeniden başlatıp tekrar bağlanabilirsin.",
        "Bağlantı sorunu varsa önce Pi'nin açık olduğunu kontrol et, sonra IP adresini doğrula.",
    ],
    "ip adresi": [
        "Pi'nin IP adresini hardware.py dosyasından güncelleyebilirsin. Şu an hangi IP'ye bağlanmaya çalışıyorum bak.",
        "IP adresi değiştiyse hardware.py içindeki PI_HOST değerini güncellemeniz gerekiyor.",
    ],

    # ── Motor bilgileri ───────────────────────────────────────────────────────
    "motor hazır mı": [
        "Motor durumunu öğrenmek için 'motor durumu' komutunu verebilirsin, anlık söylerim.",
        "Motor hazırlık kontrolü için 'motor durumu nasıl' de, hemen bakayım.",
    ],
    "motor ne zaman başlar": [
        "'Motoru çalıştır' dediğinde hemen devreye giriyor. Hazır olduğunda söyle.",
        "Motor komutu aldığı anda çalışıyor. 'Motoru çalıştır' demeni bekliyorum.",
    ],
    "motor sıcaklığı": [
        "Motor sıcaklığı için 'sıcaklık' komutu ver. Genel sistem sıcaklığını okuyorum.",
        "Anlık sıcaklık için 'sıcaklık ne kadar' diyebilirsin.",
    ],

    # ── Teknik bilgi ──────────────────────────────────────────────────────────
    "manyetik levitasyon": [
        "Manyetik levitasyon yani maglev, kapsülü raydan kaldırmak için mıknatıslar kullanır. Sürtünme sıfıra yaklaşır, hız artar.",
        "Levitasyon sistemi karşıt manyetik alanlar oluşturarak kapsülü havada tutar. Enerji verimliliği çok yüksek.",
    ],
    "vakum tüneli": [
        "Vakum tüneli içindeki hava basıncını düşürerek aerodinamik direnci minimuma indiriyoruz. Bu hızın sırrı.",
        "Tüneldeki düşük basınç hava direncini ortadan kaldırıyor. Kapsül neredeyse dirençsiz ilerliyor.",
    ],
    "levitasyon": [
        "Levitasyon için güçlü elektromıknatıslar veya süperiletkenler kullanılıyor. Kapsül raydan milimetrelerce yukarıda süzülüyor.",
        "Manyetik kaldırma kuvveti, kapsülün ağırlığını dengeler ve temas olmadan hareket sağlar.",
    ],
    "aerodinamik": [
        "Kapsülümüzün şekli hava direncini minimize edecek şekilde tasarlandı. Tünel içinde bu daha da önemli hale geliyor.",
        "Aerodinamik verimlilik hem hız hem enerji tüketimini etkiliyor. CFD analizleriyle optimize ediyoruz.",
    ],
    "güç kaynağı": [
        "Sistem bataryadan besleniyor. Voltajı takip etmem için 'voltaj kaç' diyebilirsin.",
        "Enerji kaynağımız batarya paketi. Anlık gerilimi öğrenmek için 'batarya durumu' komutunu ver.",
    ],
    "enerji verimliliği": [
        "Hyperloop geleneksel ulaşıma kıyasla çok daha enerji verimli. Düşük sürtünme ve aerodinamik tasarım bunu sağlıyor.",
        "Manyetik levitasyon sayesinde mekanik sürtünme yok denecek kadar az. Enerji verimliliği bu yüzden çok yüksek.",
    ],

    # ── Takım ve proje ────────────────────────────────────────────────────────
    "spectraloop nedir": [
        "Spectraloop, Samsun Üniversitesi'nin TEKNOFEST Hyperloop yarışmasına katılan mühendislik takımı. Ben de bu takımın sesli asistanıyım.",
        "Samsun Üniversitesi'nden bir yarışma takımıyız. Hyperloop araç kontrolü, tasarım ve yazılım geliştiriyoruz. TEKNOFEST'te yarışıyoruz!",
    ],
    "takım kaç kişi": [
        "Takımın tam büyüklüğünü bilmiyorum, ama multidisipliner bir ekip olduğunu biliyorum. Mekanik, elektronik ve yazılım var.",
        "Büyük bir ekip bu. Tasarım, üretim, elektronik ve yazılım ekipleri birlikte çalışıyor.",
    ],
    "proje ne kadar süredir": [
        "Projenin başlangıç tarihini tam bilmiyorum, ama takımın bu işe ciddi emek verdiğini biliyorum.",
        "Hyperloop projeleri uzun soluklu çalışmalar gerektiriyor. Takım bu yola uzun zamandır devam ediyor.",
    ],

    # ── Yarış / TEKNOFEST ─────────────────────────────────────────────────────
    "puan sistemi": [
        "TEKNOFEST hyperloop kategorisinde hız, güvenlik, teknik sunum ve sistem güvenilirliği değerlendiriliyor.",
        "Jüri hız performansı, sistem stabilitesi ve teknik raporlamayı puanlıyor. Güvenlik kriterleri çok önemli.",
    ],
    "jüri": [
        "Jüriler teknik belge, canlı demo ve sistem güvenilirliğine bakıyor. Hazırlıklı olmak çok önemli.",
        "TEKNOFEST jürisi hem teknik hem de sunum kalitesini değerlendiriyor. Soruları net cevaplamak şart.",
    ],
    "kazanmak için": [
        "Kazanmak için: güvenilir sistem, yüksek hız, iyi teknik dokümantasyon ve güçlü sunum gerekiyor.",
        "Jürinin beklediği: çalışan sistem, yüksek performans, güvenlik bilinci ve net teknik açıklama.",
    ],
    "rakipler": [
        "Rakiplerinizi iyi tanımak önemli, ama kendi sisteminizi mükemmelleştirmeye odaklanın. Fark yaratın!",
        "TEKNOFEST'te güçlü takımlar var. Ama Spectraloop'un sistemi sağlam, odaklanın ve güvenin.",
    ],

    # ── Test operasyonu ───────────────────────────────────────────────────────
    "test başlıyor": [
        "Test başlangıcı için sistem durumunu kontrol edelim. Frenlerin serbest, motorun hazır olduğundan emin ol.",
        "Tamam, test için hazırım! Söylediğinde başlatıyoruz.",
    ],
    "test bitti": [
        "Test bitti! Sensör verilerini kaydetmeyi unutma. Sonuçlar nasıldı?",
        "Test tamamlandı. Şimdi motor durdurulmalı ve frenler devreye alınmalı. Yapayım mı?",
    ],
    "kayıt başlat": [
        "Sensör kayıt fonksiyonum şu an yok, ama sistem verilerini sözlü olarak söyleyebilirim. Ne öğrenmek istiyorsun?",
        "Veri kaydı için harici bir sistem kullanmanı öneririm. Anlık değerleri ben söylerim.",
    ],
    "kalibre et": [
        "Kalibrasyon sensörler için fiziksel referans noktası gerektirir. Hangi sensörü kalibre etmek istiyorsun?",
        "Sıcaklık kalibrasyonu için referans sıcaklık değerini Arduino kodunda güncellemek gerekiyor.",
    ],

    # ── Hata / sorun ─────────────────────────────────────────────────────────
    "sorun var": [
        "Sorun mu var? Ne olduğunu anlat, birlikte çözelim. Sensör verilerini kontrol etmemi ister misin?",
        "Hangi sistemde sorun var? Motor mu, fren mi, bağlantı mı? Söyle, bakayım.",
    ],
    "hata alıyorum": [
        "Hangi hata? Bağlantı hatası mı, sensör hatası mı? Söylerseniz yardımcı olmaya çalışırım.",
        "Hata detayını paylaşırsan daha iyi yardımcı olabilirim. Terminal ekranında ne yazıyor?",
    ],
    "çalışmıyor": [
        "Ne çalışmıyor? Bağlantı mı, komut mu, sensör mü? Adım adım kontrol edelim.",
        "Sorunun kaynağını bulmak için: önce bağlantıyı, sonra Pi'yi, sonra Arduino'yu kontrol et.",
    ],
    "bozuldu": [
        "Üzgünüm, ne bozuldu? Donanım mı, yazılım mı? Biraz daha anlat.",
        "Bozulma nerede? Fren mi çalışmıyor, motor mu dönmüyor? Hata kaynağını bulmak için anlat.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Dinamik yanıtlar — her çağrıda hesaplanır (saat, tarih…)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime as _dt

_DYNAMIC = {
    "saat kaç": lambda: f"Saat şu an {_dt.now().strftime('%H:%M')}.",
    "saat":     lambda: f"Saat şu an {_dt.now().strftime('%H:%M')}.",
    "bugün ne günü": lambda: f"Bugün {_dt.now().strftime('%d %B %Y')}.",
    "tarih":    lambda: f"Bugün {_dt.now().strftime('%d %B %Y')}.",
}

# ─────────────────────────────────────────────────────────────────────────────
# Normalize + eşleşme
# ─────────────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
                   ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u')]:
        s = s.replace(tr, en)
    s = re.sub(r'[^\w\s]', '', s)
    return s


def _words(s: str) -> set:
    return set(_norm(s).split())


# Her kalıp için normalize edilmiş anahtar kelimeler
_PATTERN_WORDS = {k: _words(k) for k in _RESPONSES}


def detect_pattern(text: str) -> Optional[str]:
    """
    Metni kalıp tablosuna karşı kontrol eder.
    Eşleşme bulursa doğal Türkçe yanıt döndürür, bulamazsa None.
    """
    tn   = _norm(text)
    tw   = _words(text)

    # 0) Dinamik yanıtlar — önce kontrol et
    for dyn_key, dyn_fn in _DYNAMIC.items():
        dyn_norm = _norm(dyn_key)
        if dyn_norm in tn:
            return dyn_fn()

    # 1) Kalıp kelimelerinin tamamı metinde geçiyor mu?
    for pattern_key, pw in _PATTERN_WORDS.items():
        if pw and pw.issubset(tw):
            return random.choice(_RESPONSES[pattern_key])

    # 2) Kök bazlı tetikleyiciler — Türkçe ek alınmış formları da yakalar
    # (w.startswith(kök) ile kontrol edilir)
    prefix_triggers = [
        ("sikkin",      "canım sıkkın"),   # sıkkın, sıkkınım
        ("yorgun",      "yoruldum"),        # yorgun, yorgunum, yorgundu
        ("yoruldu",     "yoruldum"),
        ("uzgun",       "üzgünüm"),         # üzgün, üzgünüm
        ("mutlu",       "mutluyum"),        # mutlu, mutluyum
        ("seviyorum",   "sizi seviyorum"),
        ("sevdim",      "sizi seviyorum"),
        ("tesekkur",    "teşekkürler"),
        ("sagol",       "sağ ol"),
        ("ozur",        "özür dilerim"),
        ("saka",        "şaka yap"),
        ("espri",       "espri yap"),
        ("sarki",       "şarkı söyle"),
        ("stres",       "stres"),
        ("sikild",      "sıkıldım"),        # sıkıldım, sıkılıyorum
        ("sikiyor",     "sıkıldım"),
        ("heyecan",     "heyecanlı"),
        ("sinirli",     "sinirli"),
        ("sinirlend",   "sinirli"),
        ("korku",       "korkuyorum"),
        ("korkuyor",    "korkuyorum"),
        ("gunaydin",    "günaydın"),
        ("iyimi",       "iyi misin"),           # "iyimisin" bitişik yazım
        ("kimsin",      "sen kimsin"),
        ("berbat",      "berbat"),
        ("harika",      "harika"),
        # ── Yeni tetikleyiciler ──────────────────────────────────────────────
        ("stresli",     "çok stresli"),
        ("yapamiy",     "yapamıyorum"),
        ("basard",      "başardık"),
        ("motivasyon",  "motivasyonum düştü"),
        ("hyperloop",   "hyperloop nedir"),
        ("teknofest",   "teknofest"),
        ("robot",       "robot musun"),
        ("yapay",       "yapay zeka mısın"),    # yapay zeka mısın
        ("uyuyor",      "uyuyor musun"),
        ("ruya",        "rüya görüyor musun"),
        ("bilinc",      "bilinçli misin"),
        ("siri",        "siri gibi misin"),
        ("kahve",       "kahve"),
        ("dans",        "dans et"),
        ("oyun",        "oyun oynayalım"),
        # ── Acil / Güvenlik ──────────────────────────────────────────────────
        ("acil",        "acil durum"),          # "acil!", "acil mi", "acil durum"
        ("estop",       "e-stop"),              # "estop" yazımı (tire olmadan)
        ("guvenlik",    "güvenlik protokolü"),  # güvenlik soruları
        ("tehlike",     "tehlikeli mi"),        # tehlikeli, tehlike var
        # ── Sensörler ────────────────────────────────────────────────────────
        ("sensor",      "hangi sensörler var"), # sensör, sensörler, sensörleri
        # ── Bağlantı ─────────────────────────────────────────────────────────
        ("baglant",     "bağlantı var mı"),     # bağlantı, bağlantım, bağlantıyı
        # ── Teknik ───────────────────────────────────────────────────────────
        ("levit",       "levitasyon"),          # levitasyon, levitasyonu
        ("maglev",      "manyetik levitasyon"), # maglev kısaltması
        ("vakum",       "vakum tüneli"),        # vakum
        ("aerod",       "aerodinamik"),         # aerodinamik
        # ── Spectraloop / Takım ──────────────────────────────────────────────
        ("spectraloop", "spectraloop nedir"),   # spectraloop hakkında sorular
        ("takim",       "takım kaç kişi"),      # takım büyüklüğü soruları
        ("proje",       "proje ne kadar süredir"),
        # ── Yarış / TEKNOFEST ────────────────────────────────────────────────
        ("kazanm",      "kazanmak için"),       # kazanmak, kazanmamız, kazanabilmek
        ("kazanil",     "kazanmak için"),       # kazanılır, kazanılması (edilgen çekim)
        ("juri",        "jüri"),                # jüri
        ("puan",        "puan sistemi"),        # puan, puanlama
        ("rakip",       "rakipler"),            # rakip, rakipler, rakibimiz
        # ── Test operasyonu ──────────────────────────────────────────────────
        ("kalibr",      "kalibre et"),          # kalibre, kalibrasyon
        # ── Hatalar ──────────────────────────────────────────────────────────
        ("hata",        "hata alıyorum"),       # hata, hatalı, hatası
        ("bozul",       "bozuldu"),             # bozuldu, bozulmuş
        ("calismi",     "çalışmıyor"),          # çalışmıyor, çalışmıyordu
    ]
    for prefix, pattern_key in prefix_triggers:
        if any(w.startswith(prefix) for w in tw):
            return random.choice(_RESPONSES[pattern_key])

    # 3) "nasılsın" — sadece "nasil" + fren/hava gibi kelime YOK ise
    fren_words = {"fren", "on", "arka", "birak", "ac", "kapat"}
    hava_words = {"hava", "sicak", "soguk", "yagmur", "kar"}
    if "nasil" in tn and not (tw & fren_words) and not (tw & hava_words):
        return random.choice(_RESPONSES["nasılsın"])

    return None
