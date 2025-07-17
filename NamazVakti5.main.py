import network
import usocket
import time
import ujson
import ntptime
import machine
import re
import gc
import errno
import os

# --- Sabitler ve Global Ayarlar ---
CONFIG_FILE = "config.json"
AP_MODE_SSID = "NamazVaktiSetup"
NTP_SERVER = "pool.ntp.org"

# Varsayılan yapılandırma ayarları
DEFAULT_CONFIG = {
    "ssid": "Bilal",
    "password": "12345678",
    "rss_url": "http://namazvakti.com/DailyRSS.php?cityID=16741",
    "timezone_offset": 3 # Türkiye için varsayılan GMT+3
}

# RSS ve NTP güncelleme aralıkları (sabit olarak tanımlandı, kolayca değiştirilebilir)
RSS_UPDATE_INTERVAL_SECONDS = 21600 # 6 saat
NTP_UPDATE_INTERVAL_SECONDS = 21600 # 6 saat

# --- OLED Ekran Ayarları ve Fonksiyonları ---
WIDTH = 128
HEIGHT = 64
oled = None # Global oled değişkenini varsayılan olarak None yapıyoruz

class FallbackMockOLED:
    """OLED kütüphanesi veya donanım hatası durumunda kullanılan sahte OLED sınıfı."""
    def fill(self, color):
        pass
    def text(self, text, x, y):
        pass
    def show(self):
        pass
    def clear_line(self, line): # Yeni eklenen metod
        pass

def init_oled():
    """OLED ekranı başlatır ve global 'oled' değişkenini ayarlar."""
    global oled
    try:
        from machine import Pin, I2C
        from ssd1306 import SSD1306_I2C

        print("I2C Pinleri Tanımlanıyor (SCL:22, SDA:21)...")
        scl_pin = Pin(22)
        sda_pin = Pin(21)

        print("I2C arabirimi başlatılıyor (freq=400000)...")
        i2c = I2C(scl=scl_pin, sda=sda_pin, freq=400000)
        
        print("I2C cihazları taranıyor...")
        devices = i2c.scan()
        if devices:
            print("I2C cihazları bulundu: %s" % [hex(d) for d in devices])
        else:
            print("HATA: I2C üzerinde hiçbir cihaz bulunamadı (Pinler: SDA=21, SCL=22).")
            print("Lütfen OLED bağlantılarınızı (SDA, SCL, VCC, GND) ve pin numaralarını kontrol edin.")
            raise RuntimeError("I2C cihazı bulunamadı. Bağlantıları kontrol edin.")

        oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)
        oled.fill(0)
        oled.show()
        print("OLED ekran başarıyla başlatıldı ve temizlendi.")

        # OLED sınıfına clear_line metodunu ekle
        def _clear_line(self, line):
            self.rect(0, line * 8, WIDTH, 8, 0, True) # Satırı tamamen siyah ile doldur
        
        SSD1306_I2C.clear_line = _clear_line 

    except ImportError as e:
        print("HATA: 'ssd1306' kütüphanesi bulunamadı veya içe aktarma hatası.")
        print("Lütfen https://github.com/micropython/micropython-lib/tree/master/micropython/drivers/display/ssd1306 adresinden indirin ve cihazınıza yükleyin.")
        print("Detay: %s" % e)
        oled = FallbackMockOLED()
        print("OLED kütüphanesi bulunamadığı için geçici Mock OLED kullanılıyor.")
    except SyntaxError as e:
        print("KRİTİK HATA: OLED başlatılırken bir sözdizimi hatası oluştu: %s" % e)
        print("Bu, MicroPython firmware'inizin çok eski olduğunu ve Python sentaksını desteklemediğini gösterir.")
        print("Lütfen ESP32 MicroPython firmware'inizi güncelleyin.")
        oled = FallbackMockOLED()
        print("OLED başlatma hatası nedeniyle geçici Mock OLED kullanılıyor.")
    except RuntimeError as e:
        print("HATA: OLED donanım hatası: %s" % e)
        print("OLED ekranı ESP32'ye doğru pinlere (SDA=21, SCL=22) ve doğru şekilde bağlı olduğundan emin olun.")
        oled = FallbackMockOLED()
        print("Donanım hatası nedeniyle geçici Mock OLED kullanılıyor.")
    except Exception as e:
        print("HATA: OLED başlatılırken beklenmeyen bir genel sorun oluştu: %s" % e)
        print("Lütfen pin bağlantılarınızı ve kütüphane kurulumunuzu kontrol edin.")
        oled = FallbackMockOLED()
        print("OLED başlatma hatası nedeniyle geçici Mock OLED kullanılıyor.")

# OLED'i global olarak başlat
init_oled()

def display_message(message, line, clear_screen=False, show_now=True):
    """
    OLED ekrana mesaj yazdırır.
    clear_screen: True ise tüm ekranı temizler.
    show_now: True ise mesajı hemen gösterir, False ise daha sonra manuel show() çağrısı beklenir.
    """
    if oled is None:
        return
    try:
        if clear_screen:
            oled.fill(0)
        else:
            if hasattr(oled, 'clear_line'):
                oled.clear_line(line)
            else:
                oled.text(' ' * (WIDTH // 8), 0, line * 8) 
        
        max_chars = WIDTH // 8
        display_text = message[:max_chars]
        oled.text(display_text, 0, line * 8)
        if show_now:
            oled.show()
    except Exception as e:
        print("Ekran güncelleme hatası (display_message): %s (Mesaj: '%s', Satır: %d)" % (e, message, line))

def reset():
    print("Cihaz yeniden başlatılıyor...")
    display_message("Yeniden baslatiliyor...", 7, clear_screen=True)
    time.sleep(2)
    machine.reset()

def convert_turkish_chars(text):
    """Türkçe karakterleri İngilizce eşdeğerlerine dönüştürür."""
    text = text.replace("Ç", "C").replace("ç", "c")
    text = text.replace("Ğ", "G").replace("ğ", "g")
    text = text.replace("İ", "I").replace("ı", "i")
    text = text.replace("Ö", "O").replace("ö", "o")
    text = text.replace("Ş", "S").replace("ş", "s")
    text = text.replace("Ü", "U").replace("ü", "u")
    text = text.replace("â", "a")
    return text

def unquote_plus_custom(s):
    """URL kodlu stringleri çözer (sadece '+' ve '%XX' için)."""
    s = s.replace('+', ' ')
    parts = s.split('%')
    if len(parts) == 1:
        return s
    
    decoded_s = parts[0]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                char_code = int(part[:2], 16)
                decoded_s += chr(char_code) + part[2:]
            except ValueError:
                decoded_s += '%' + part
        else:
            decoded_s += '%' + part
    return decoded_s

# --- NTP Zaman Senkronizasyonu ---
def set_time_from_ntp(timezone_offset):
    """NTP sunucusundan zamanı senkronize eder ve RTC'ye kaydeder."""
    try:
        display_message("Zaman Ayarlaniyor...", 0, clear_screen=True, show_now=True)
        print("NTP sunucusundan zaman alınıyor: %s" % NTP_SERVER)
        ntptime.host = NTP_SERVER
        ntptime.settime()
        
        rtc = machine.RTC()
        
        current_utc_time_tuple = time.gmtime(time.time())
        current_epoch_utc = time.mktime(current_utc_time_tuple)
        
        local_epoch = current_epoch_utc + timezone_offset * 3600 # timezone_offset kullanılıyor
        
        local_time_tuple = time.localtime(local_epoch)
        rtc.datetime((local_time_tuple[0], local_time_tuple[1], local_time_tuple[2],
                      local_time_tuple[6],
                      local_time_tuple[3], local_time_tuple[4], local_time_tuple[5], 0))
        
        print("NTP ile zaman ayarlandı. Mevcut zaman: %s" % str(time.localtime()))
        display_message("Zaman: %02d:%02d" % (time.localtime()[3], time.localtime()[4]), 0, show_now=True)
        return True
    except OSError as e:
        if e.args[0] == errno.ETIMEDOUT:
            print("NTP zaman aşımı hatası: %s" % e)
            display_message("NTP Zamani Doldu!", 4, show_now=True)
        elif e.args[0] == -2: # Bu genellikle "address not available" veya "host not found" hatasıdır
            print("NTP sunucusuna bağlanılamadı/ulaşılamadı: %s" % e)
            display_message("NTP Sunucu Hata!", 4, show_now=True)
        else:
            print("NTP senkronizasyon hatası: %s - %s" % (type(e).__name__, e.args[0]))
            display_message("NTP Hatasi: %s" % e.args[0], 4, show_now=True)
        time.sleep(2)
        return False
    except Exception as e:
        print("NTP senkronizasyon hatası (genel): %s - %s" % (type(e).__name__, e))
        display_message("NTP Hata! %s" % type(e).__name__, 4, show_now=True)
        time.sleep(2)
        return False

# --- RSS Verisi Çekme ve İşleme ile İlgili Fonksiyonlar ve Sabitler ---
MONTH_ABBREVIATIONS = {
    "Ocak": "Oca", "Şubat": "Şub", "Mart": "Mar", "Nisan": "Nis",
    "Mayıs": "May", "Haziran": "Haz", "Temmuz": "Tem", "Ağustos": "Ağu",
    "Eylül": "Eyl", "Ekim": "Eki", "Kasım": "Kas", "Aralık": "Ara"
}

DAY_ABBREVIATIONS = {
    "Pazartesi": "Pzt", "Salı": "Sal", "Çarşamba": "Car", "Perşembe": "Per", 
    "Cuma": "Cum", "Cumartesi": "Cmt", "Pazar": "Paz"
}

def unescape_html_entities(text):
    """HTML varlıklarını (örn: &lt;) gerçek karakterlere dönüştürür."""
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&apos;", "'")
    text = text.replace("&nbsp;", " ")
    return text

def format_date_for_display(date_string):
    """RSS'ten gelen tarih stringini OLED'e uygun kısaltılmış formata çevirir."""
    parts = date_string.replace(',', '').split(' ')
    if len(parts) >= 4:
        day = parts[0]
        month_full = parts[1]
        year_full = parts[2]
        day_of_week_full = parts[3]

        month_abbr = MONTH_ABBREVIATIONS.get(month_full, month_full[:3])
        month_abbr = convert_turkish_chars(month_abbr)

        year_abbr = year_full[-2:]

        day_of_week_abbr = DAY_ABBREVIATIONS.get(day_of_week_full, day_of_week_full[:3])
        day_of_week_abbr = convert_turkish_chars(day_of_week_abbr)

        formatted = "%s %s %s %s" % (day, month_abbr, year_abbr, day_of_week_abbr)
        return formatted[:WIDTH // 8]
    return convert_turkish_chars(date_string)[:WIDTH // 8]

def get_namaz_vakitleri(rss_url):
    """Belirtilen RSS URL'sinden namaz vakitlerini çeker ve ayrıştırır."""
    display_message("Veri Cekiliyor...", 0, clear_screen=True, show_now=True)
    print("RSS verisi çekiliyor: %s" % rss_url)
    
    display_date_time = "Tarih Yok"
    vakitler_map = {}

    try:
        import urequests
        response = urequests.get(rss_url, timeout=15)
        if response.status_code == 200:
            rss_content = response.text
            response.close()
            gc.collect()

            item_and_title_and_description_match = re.search(r"<item>.*?<title>(.*?)</title>.*?<description>([\s\S]*?)</description>.*?</item>", rss_content)
            
            if item_and_title_and_description_match:
                full_title_string = item_and_title_and_description_match.group(1).strip()
                display_date_time = format_date_for_display(full_title_string)
                raw_description_text = item_and_title_and_description_match.group(2)
                
                decoded_text = unescape_html_entities(raw_description_text)
                cleaned_text = re.sub(r'<br\s*/?>|<p>|&lt;br\s*/?&gt;', '', decoded_text).strip()
                cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                
                print("Temizlenmiş Description: '%s'" % cleaned_text)

                if not cleaned_text:
                    print("Hata: Temizlenmiş description metni boş.")
                    display_message("Bos Desc. Hatasi", 2, show_now=True)
                    return False, []

                # --- Padding (Boşluk Doldurma) Fonksiyonu ---
                def custom_ljust(s, width, fillchar=' '):
                    if len(s) >= width:
                        return s
                    return s + (fillchar * (width - len(s)))
                # --- Padding Fonksiyonu Sonu ---

                parts = cleaned_text.split(' ')
                
                # Olası vakit adları ve bunların eşleştirme için küçük harfli/dönüştürülmüş halleri
                # ve ekranda gösterilecek orijinal halleri
                namaz_vakitleri_mapping = {
                    "imsak": "İmsâk",
                    "gunes": "Güneş",
                    "ogle": "Öğle",
                    "ikindi": "İkindi",
                    "aksam": "Akşam",
                    "yatsi": "Yatsı"
                }
                
                i = 0
                while i < len(parts):
                    # Kelimeyi küçük harfe çevir ve Türkçe karakterleri dönüştürerek kontrol et
                    normalized_part = convert_turkish_chars(parts[i]).lower()
                    
                    found_original_vakit_name = None
                    for key_name, display_name in namaz_vakitleri_mapping.items():
                        if normalized_part == key_name:
                            found_original_vakit_name = display_name
                            break
                    
                    if found_original_vakit_name:
                        # Vakit adı bulundu, şimdi saati bulmaya çalış
                        # "İmsâk : 03:17" veya "Güneş 05:34" formatlarını desteklemek için
                        saat = None
                        if i + 1 < len(parts):
                            if parts[i+1] == ":" and i + 2 < len(parts): # "Vakit : HH:MM"
                                potential_saat = parts[i+2]
                                if len(potential_saat) == 5 and potential_saat[2] == ':' and potential_saat[:2].isdigit() and potential_saat[3:].isdigit():
                                    saat = potential_saat
                                    i += 3 # Vakit, :, Saat geçti
                                else:
                                    i += 1 # : veya saat uygun değil, bir sonraki kelimeye geç
                            else: # "Vakit HH:MM"
                                potential_saat = parts[i+1]
                                if len(potential_saat) == 5 and potential_saat[2] == ':' and potential_saat[:2].isdigit() and potential_saat[3:].isdigit():
                                    saat = potential_saat
                                    i += 2 # Vakit, Saat geçti
                                else:
                                    i += 1 # Saat uygun değil, bir sonraki kelimeye geç
                        else: # Vakit adından sonra başka kelime yok
                            i += 1

                        if saat:
                            vakitler_map[found_original_vakit_name] = saat
                            continue # Saati bulduk, bir sonraki kelimeye devam et
                    
                    i += 1 # Eğer vakit adı veya saat bulunamazsa bir sonraki kelimeye geç

                found_vakitler_display = []
                found_vakitler_for_calc = []
                ordered_vakit_names = ["İmsâk", "Güneş", "Öğle", "İkindi", "Akşam", "Yatsı"]
                
                target_name_width = 7
                
                for name in ordered_vakit_names:
                    if name in vakitler_map:
                        display_saat_str = vakitler_map[name]
                        
                        converted_name = convert_turkish_chars(name)
                        padded_name = custom_ljust(converted_name, target_name_width)
                        
                        formatted_vakit = "%s: %s" % (padded_name, display_saat_str)
                        found_vakitler_display.append(formatted_vakit)
                        
                        found_vakitler_for_calc.append((name, display_saat_str))
                        
                if found_vakitler_display:
                    display_message(display_date_time, 0, clear_screen=True, show_now=False)
                    
                    y_start_line = 1 
                    for i, vakit in enumerate(found_vakitler_display):
                        target_line = y_start_line + i
                        if target_line < HEIGHT // 8:
                            display_message(vakit, target_line, clear_screen=False, show_now=False)
                        else:
                            break
                    oled.show()
                    return True, found_vakitler_for_calc
                else:
                    print("Hata: Hiçbir namaz vakti bulunamadı (String işleme sonrası).")
                    display_message("Vakitler bulunamadi.", 2, show_now=True)
                    return False, []
            else:
                print("Hata: RSS 'item' etiketi veya içindeki 'title' ve 'description' bulunamadı.")
                display_message("RSS Yapisi Hata.", 2, show_now=True)
                return False, []
        else:
            print("HTTP Hatası: %d" % response.status_code)
            display_message("HTTP Hata: %d" % response.status_code, 2, show_now=True)
            return False, []
    except ImportError:
        print("urequests kütüphanesi bulunamadı. Lütfen yükleyin.")
        display_message("Urequests Eksik!", 2, show_now=True)
        return False, []
    except OSError as e:
        if e.args[0] == errno.ETIMEDOUT:
            print("Veri çekme sırasında zaman aşımı hatası: %s" % e)
            display_message("Cekme Zaman Asti!", 2, show_now=True)
        return False, []
    except Exception as e:
        print("Veri çekme sırasında genel hata oluştu: %s - %s" % (type(e).__name__, e))
        display_message("Cekme Hatasi: %s" % type(e).__name__, 2, show_now=True)
        return False, []

# --- Kalan Süre Hesaplama ve Gösterme ---
def calculate_and_display_next_prayer_time(vakitler_for_calc):
    """Bir sonraki namaz vaktine kalan süreyi hesaplar ve ekranda gösterir."""
    rtc_datetime = machine.RTC().datetime()
    current_year, current_month, current_day, _, current_hour, current_minute, current_second, _ = rtc_datetime
    
    current_time_in_seconds = time.mktime((current_year, current_month, current_day, current_hour, current_minute, current_second, 0, 0))

    prayer_times_today_in_seconds = []
    for name, time_str in vakitler_for_calc:
        try:
            h, m = map(int, time_str.split(':'))
            prayer_seconds = time.mktime((current_year, current_month, current_day, h, m, 0, 0, 0))
            prayer_times_today_in_seconds.append((name, prayer_seconds))
        except ValueError as e:
            print("Vakit parse hatası '%s': %s" % (time_str, e))
            continue

    if not prayer_times_today_in_seconds:
        display_message("Vakitler gecersiz!", 7, show_now=True)
        return

    next_prayer_info = None
    min_time_diff = float('inf')

    for name, prayer_sec in prayer_times_today_in_seconds:
        time_diff = prayer_sec - current_time_in_seconds
        if time_diff > 0:
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                next_prayer_info = (name, min_time_diff)

    if next_prayer_info is None:
        # Eğer bu gün için bir sonraki vakit yoksa, yarınki ilk vakti (İmsak'ı) hedefle
        if prayer_times_today_in_seconds:
            # Bugünden 24 saat sonrası için zaman tuple'ını hesapla
            next_day_time_tuple = time.localtime(current_time_in_seconds + 24 * 3600)
            next_day_year, next_day_month, next_day_day = next_day_time_tuple[0], next_day_time_tuple[1], next_day_time_tuple[2]
            
            # İlk vakit (İmsak) genellikle dizinin ilk elemanıdır
            if vakitler_for_calc:
                imsak_name, imsak_time_str = vakitler_for_calc[0]
                try:
                    imsak_hour, imsak_minute = map(int, imsak_time_str.split(':'))
                    # Yarınki İmsak vaktinin epoch saniye cinsinden değeri
                    next_day_imsak_seconds = time.mktime((next_day_year, next_day_month, next_day_day, imsak_hour, imsak_minute, 0, 0, 0))
                    
                    # Şimdiki zaman ile yarınki İmsak arasındaki fark
                    time_diff_seconds = next_day_imsak_seconds - current_time_in_seconds
                    next_prayer_info = (imsak_name, time_diff_seconds)
                except ValueError as e:
                    print("Yarınki İmsâk vakti parse hatası: %s" % e)
                    display_message("Yarin Imsak Hatasi", 7, show_now=True)
                    return

    if next_prayer_info:
        next_prayer_name, time_diff_seconds = next_prayer_info
        
        # Eğer hesaplanan süre negatifse (geçmiş bir vakitse), 0 yap
        if time_diff_seconds < 0:
            time_diff_seconds = 0

        days = time_diff_seconds // (24 * 3600)
        remaining_seconds_after_days = time_diff_seconds % (24 * 3600)
        hours = remaining_seconds_after_days // 3600
        minutes = (remaining_seconds_after_days % 3600) // 60

        display_str = "S:%s" % convert_turkish_chars(next_prayer_name)
        
        if days > 0:
            remaining_time_format = "%dg %02d:%02d" % (days, hours, minutes)
        else:
            # Sadece saat:dakika formatı
            remaining_time_format = "%02d:%02d" % (hours, minutes)
            
        display_str += " K:%s" % remaining_time_format # "K:" den önce boşluk eklendi
        
        display_message(display_str, 7, clear_screen=False, show_now=True)
    else:
        display_message("Sonraki Vakit Bulunamadi", 7, clear_screen=False, show_now=True)

# --- Yapılandırma Yükleme/Kaydetme Fonksiyonları ---
def load_config():
    """Yapılandırma dosyasını yükler, yoksa veya bozuksa varsayılanları döndürür."""
    try:
        with open(CONFIG_FILE, "r") as f:
            config = ujson.load(f)
            # Yeni eklenen varsayılanları da kontrol et
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            print("Yapılandırma yüklendi: %s" % config)
            return config, True
    except OSError as e:
        if e.args[0] == errno.ENOENT:
            print("Yapılandırma dosyası '%s' bulunamadı. Varsayılan ayarlar kullanılıyor." % CONFIG_FILE)
        else:
            print("Yapılandırma dosyası okunurken OSError oluştu: %s - %s. Varsayılan ayarlar kullanılıyor." % (type(e).__name__, e))
        return DEFAULT_CONFIG.copy(), False
    except ValueError as e:
        print("Yapılandırma dosyası bozuk (ValueError): %s. Varsayılan ayarlar kullanılıyor." % e)
        try:
            os.remove(CONFIG_FILE)
            print("Bozuk yapılandırma dosyası silindi.")
        except OSError as e_del:
            print("Bozuk yapılandırma dosyası silinirken hata oluştu: %s" % e_del)
        return DEFAULT_CONFIG.copy(), False
    except Exception as e:
        print("Yapılandırma yüklenirken beklenmeyen bir hata oluştu: %s - %s. Varsayılan ayarlar kullanılıyor." % (type(e).__name__, e))
        return DEFAULT_CONFIG.copy(), False

def save_config(config):
    """Yapılandırma dosyasını kaydeder."""
    try:
        try:
            fs_stat = os.statvfs('/')
            block_size = fs_stat[0]
            free_blocks = fs_stat[3]
            total_size_kb = (fs_stat[2] * block_size) / 1024
            free_size_kb = (free_blocks * block_size) / 1024
            print(f"Dosya sistemi durumu: Toplam {total_size_kb:.2f}KB, Boş {free_size_kb:.2f}KB")
            if free_size_kb < 10:
                print("UYARI: Dosya sisteminde çok az boş alan var. Bu yazma hatalarına neden olabilir.")
        except Exception as fs_e:
            print(f"Dosya sistemi durumu alınırken hata: {fs_e}")

        with open(CONFIG_FILE, "w") as f:
            ujson.dump(config, f)
        print("Yapılandırma başarıyla kaydedildi: %s" % config)
        return True
    except OSError as e:
        print("HATA: Yapılandırma kaydedilemedi (OSError). Hata kodu: %s" % e.args[0])
        if e.args[0] == errno.EACCES:
            print("Erişim reddedildi hatası. Dosya sistemi sadece okunur olabilir veya izin sorunları var.")
        elif e.args[0] == errno.ENOSPC:
            print("Disk alanı yok hatası. Cihazda yer kalmamış olabilir.")
        elif e.args[0] == errno.EROFS:
            print("Salt okunur dosya sistemi hatası. MicroPython flash'ı salt okunur olarak bağlamış olabilir.")
        else:
            print(f"Bilinmeyen OSError: {e}")
        display_message("Ayarlar Kaydedilemedi!", 6, show_now=True)
        return False
    except Exception as e:
        print("HATA: Yapılandırma kaydedilirken beklenmeyen bir hata oluştu: %s - %s" % (type(e).__name__, e))
        display_message("Ayarlar Kaydedilemedi!", 6, show_now=True)
        return False

# --- Web Sunucusu Fonksiyonları (AP Modu) ---
def start_ap_mode_and_web_server(ap_mode_duration_seconds=300):
    """
    AP modunu başlatır ve yapılandırma için basit bir web sunucusu çalıştırır.
    ap_mode_duration_seconds: AP modunun açık kalacağı süre (saniye).
    """
    ap = network.WLAN(network.AP_IF)
    ap_start_time = time.time()
    
    display_message("Kurulum Modu!", 0, clear_screen=True, show_now=False)
    display_message("SSID: %s" % AP_MODE_SSID, 1, show_now=False)
    
    try:
        ap.active(True)
        time.sleep_ms(300) # AP arayüzünün tam olarak başlaması için gecikme
        ap.config(ssid=AP_MODE_SSID)
        
        print("AP Modu başlatıldı (Şifresiz): SSID='%s'" % AP_MODE_SSID)
        display_message("Sifre: Yok", 2, show_now=False)
        
    except Exception as e:
        print("AP modu yapılandırma hatası: %s - %s" % (type(e).__name__, e))
        display_message("AP Modu Hata!", 0, clear_screen=True, show_now=False)
        display_message("Hata: %s" % e, 1, show_now=False)
        oled.show()
        time.sleep(5)
        reset()

    ap_ip = ap.ifconfig()[0]

    print("AP Modu başlatıldı. SSID: %s, IP: %s" % (AP_MODE_SSID, ap_ip))
    
    display_message("IP: %s" % ap_ip, 3, show_now=False)
    display_message("Tarayici ile baglanin", 5, show_now=False)
    oled.show()

    s = None # Soket değişkenini başlangıçta None olarak ayarla
    try:
        s = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        s.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
        s.bind(('', 80))
        s.listen(5)
        print("Web sunucusu dinlemede...")
    except OSError as e:
        print("KRİTİK HATA: Soket başlatma, bağlanma veya dinleme hatası: %s. Port meşgul veya kaynak sorunu." % e)
        display_message("Soket Hata: %s" % e.args[0], 6, show_now=True)
        if s: # Hata oluşursa soketi kapat
            s.close()
        ap.active(False) # AP modunu devre dışı bırak
        gc.collect()
        return # Fonksiyondan çık, web sunucusu başlayamadı

    while True:
        conn = None
        addr = None
        request_str = ""
        first_line = ""
        try:
            remaining_time = max(0, int(ap_mode_duration_seconds - (time.time() - ap_start_time)))
            display_message("Kalan: %ds" % remaining_time, 6, show_now=True)

            if remaining_time <= 0:
                print("AP modu süresi doldu. Web sunucusu kapatılıyor.")
                break # Döngüden çık

            s.settimeout(1) # Accept için kısa bir zaman aşımı
            conn, addr = s.accept()
            s.settimeout(None) # Bağlantı kurulduktan sonra zaman aşımını kaldır
            
            print("Bağlantı alındı: %s" % str(addr))
            
            request_bytes = conn.recv(2048)
            request_str = request_bytes.decode('utf-8', 'ignore') # UTF-8 ve hataları yoksay
            
            if request_str:
                lines = request_str.split('\r\n')
                if lines and lines[0]:
                    first_line = lines[0]
            print("Gelen İstek:\n%s" % first_line)

            show_form = True
            parsed_params = {}

            if "GET /?" in first_line:
                params_str = first_line.split("GET /?")[1].split(" HTTP/1.1")[0]
                for param in params_str.split("&"):
                    key_val = param.split("=")
                    if len(key_val) == 2:
                        parsed_params[key_val[0]] = unquote_plus_custom(key_val[1])
            elif "POST /" in first_line:
                show_form = False
                content_type_match = re.search(r"Content-Type: application/x-www-form-urlencoded", request_str, re.IGNORECASE)
                content_length_match = re.search(r"Content-Length: (\d+)", request_str)
                
                if content_type_match and content_length_match:
                    content_length = int(content_length_match.group(1))
                    post_data_start = request_str.find("\r\n\r\n") + 4
                    post_data = request_str[post_data_start : post_data_start + content_length]
                    
                    for param in post_data.split("&"):
                        key_val = param.split("=")
                        if len(key_val) == 2:
                            parsed_params[key_val[0]] = unquote_plus_custom(key_val[1])
                else:
                    print("Hata: POST isteğinde Content-Type veya Content-Length eksik.")
                    conn.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nMissing Content-Type or Content-Length for POST.\r\n')
                    conn.close()
                    gc.collect()
                    continue

            elif "GET / HTTP" in first_line:
                show_form = True
            else:
                # Bilinmeyen veya alakasız istekleri ele al (favicon.ico vs.)
                conn.sendall(b'HTTP/1.1 204 No Content\r\n\r\n') # 204 No Content
                conn.close()
                gc.collect()
                continue

            if show_form:
                current_config, _ = load_config()
                current_ssid_val = current_config.get("ssid", "")
                current_password_val = current_config.get("password", "")
                current_rss_url_val = current_config.get("rss_url", "")
                current_timezone_offset_val = str(current_config.get("timezone_offset", DEFAULT_CONFIG["timezone_offset"]))

                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Namaz Vakitleri Ayarları</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }}
                        div {{ background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 500px; margin: auto; }}
                        h2 {{ color: #333; text-align: center; margin-bottom: 20px; }}
                        label {{ display: block; margin-bottom: 5px; color: #555; font-weight: bold; }}
                        input[type="text"], input[type="password"], input[type="number"] {{
                            width: calc(100% - 22px); padding: 10px; margin: 8px 0 15px 0; display: inline-block;
                            border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 16px;
                        }}
                        input[type="submit"] {{
                            background-color: #4CAF50; color: white; padding: 14px 20px; margin: 8px 0;
                            border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 18px;
                            transition: background-color 0.3s ease;
                        }}
                        input[type="submit"]:hover {{ background-color: #45a049; }}
                        p.message {{ text-align: center; font-size: 1.1em; margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div>
                        <h2>Namaz Vakitleri Ayarları</h2>
                        <form action="/" method="post">
                            <label for="ssid">WiFi SSID:</label>
                            <input type="text" id="ssid" name="ssid" value="{}"/><br>
                            <label for="password">WiFi Şifresi:</label>
                            <input type="password" id="password" name="password" value="{}"/><br>
                            <label for="rss_url">RSS URL:</label>
                            <input type="text" id="rss_url" name="rss_url" value="{}"/><br>
                            <label for="timezone_offset">Zaman Dilimi Ofseti (GMT+-):</label>
                            <input type="number" id="timezone_offset" name="timezone_offset" value="{}"/><br>
                            <input type="submit" value="Kaydet ve Yeniden Başlat">
                        </form>
                    </div>
                </body>
                </html>
                """.format(
                    current_ssid_val,
                    current_password_val,
                    current_rss_url_val,
                    current_timezone_offset_val
                )

                conn.sendall(b'HTTP/1.1 200 OK\r\n')
                conn.sendall(b'Content-Type: text/html; charset=UTF-8\r\n') # <-- UTF-8 eklendi
                conn.sendall(b'Connection: close\r\n')
                conn.sendall('Content-Length: %d\r\n\r\n' % len(html))
                conn.sendall(html.encode('utf-8')) # <-- UTF-8 olarak kodlandı
                conn.close()

            else:
                new_ssid = parsed_params.get("ssid", "").strip()
                new_password = parsed_params.get("password", "").strip()
                new_rss_url = parsed_params.get("rss_url", "").strip()
                new_timezone_offset_str = parsed_params.get("timezone_offset", "").strip()
                
                new_timezone_offset = DEFAULT_CONFIG["timezone_offset"]
                if new_timezone_offset_str:
                    try:
                        new_timezone_offset = int(new_timezone_offset_str)
                    except ValueError:
                        print("Hata: Geçersiz zaman dilimi ofseti değeri. Varsayılan kullanılıyor.")

                if new_ssid and new_password and new_rss_url:
                    current_config, _ = load_config()
                    current_config["ssid"] = new_ssid
                    current_config["password"] = new_password
                    current_config["rss_url"] = new_rss_url
                    current_config["timezone_offset"] = new_timezone_offset
                    
                    if save_config(current_config):
                        response_html = """
                        <!DOCTYPE html>
                        <html>
                        <head><meta charset="UTF-8"><title>Ayarlar Kaydedildi</title></head>
                        <body>
                        <p class="message" style="color: green;">Ayarlar Kaydedildi! Cihaz yeniden başlatılıyor...</p>
                        <script>setTimeout(function(){{ window.location.href = '/'; }}, 3000);</script>
                        </body></html>
                        """
                        conn.sendall(b'HTTP/1.1 200 OK\r\n')
                        conn.sendall(b'Content-Type: text/html; charset=UTF-8\r\n') # <-- UTF-8 eklendi
                        conn.sendall(b'Connection: close\r\n')
                        conn.sendall('Content-Length: %d\r\n\r\n' % len(response_html))
                        conn.sendall(response_html.encode('utf-8')) # <-- UTF-8 olarak kodlandı
                        conn.close()
                        print("Yeni ayarlar kaydedildi, yeniden başlatılıyor...")
                        time.sleep(2)
                        reset()
                    else:
                        response_html = """
                        <!DOCTYPE html>
                        <html>
                        <head><meta charset="UTF-8"><title>Hata Oluştu</title></head>
                        <body>
                        <p class="message" style="color: red;">Hata! Ayarlar kaydedilemedi. Tekrar deneyin.</p>
                        <a href='/' style="display: block; text-align: center; margin-top: 20px;">Geri Dön</a>
                        </body></html>
                        """
                        conn.sendall(b'HTTP/1.1 500 Internal Server Error\r\n')
                        conn.sendall(b'Content-Type: text/html; charset=UTF-8\r\n') # <-- UTF-8 eklendi
                        conn.sendall(b'Connection: close\r\n')
                        conn.sendall('Content-Length: %d\r\n\r\n' % len(response_html))
                        conn.sendall(response_html.encode('utf-8')) # <-- UTF-8 olarak kodlandı
                        conn.close()
                else:
                    print("Gerekli Wi-Fi veya RSS URL parametreleri eksik.")
                    response_html = """
                    <!DOCTYPE html>
                    <html>
                    <head><meta charset="UTF-8"><title>Eksik Bilgi</title></head>
                    <body>
                    <p class="message" style="color: orange;">Hata! Tüm alanları doldurun.</p>
                    <a href='/' style="display: block; text-align: center; margin-top: 20px;">Geri Dön</a>
                    </body></html>
                    """
                    conn.sendall(b'HTTP/1.1 400 Bad Request\r\n')
                    conn.sendall(b'Content-Type: text/html; charset=UTF-8\r\n') # <-- UTF-8 eklendi
                    conn.sendall(b'Connection: close\r\n')
                    conn.sendall('Content-Length: %d\r\n\r\n' % len(response_html))
                    conn.sendall(response_html.encode('utf-8')) # <-- UTF-8 olarak kodlandı
                    conn.close()

        except OSError as e:
            if e.args[0] == errno.ETIMEDOUT:
                pass 
            elif e.args[0] == errno.ECONNRESET:
                print("Web sunucusu: Bağlantı sıfırlandı (İstemci kapattı).")
            elif e.args[0] == errno.EWOULDBLOCK:
                 pass
            else:
                print("Web sunucusu hatası (OSError): %s - Bağlantı adresi: %s" % (e, addr if 'addr' in locals() else 'Bilinmiyor'))
                display_message("Web Hata: %s" % e.args[0], 6, show_now=True)
                time.sleep(1)
        except Exception as e:
            print("Genel web sunucusu istisnası: %s - %s - Gelen İstek İlk Satırı: '%s'" % (type(e).__name__, e, first_line))
            display_message("Web Sunucu Hata!", 6, show_now=True)
            time.sleep(1)
        finally:
            if conn:
                try:
                    conn.close()
                except OSError as e:
                    print(f"Bağlantı kapatılırken hata: {e}")
            gc.collect()
    
    # Döngü bittiğinde (süre dolduğunda) soketi kapat
    if s: # Eğer soket başarıyla oluşturulduysa kapat
        try:
            s.close()
        except OSError as e:
            print(f"Ana soket kapatılırken hata: {e}")
    
    ap.active(False) # AP modunu devre dışı bırak
    gc.collect()


# --- Ana Döngü ---
def main_loop():
    WIFI_CONNECT_TIMEOUT = 20
    WIFI_RETRY_DELAY_SECONDS = 15
    MAX_WIFI_RECONNECT_ATTEMPTS = 3 

    failed_wifi_attempts = 0
    
    config, config_exists = load_config()

    if not config_exists:
        print("config.json bulunamadığı için varsayılan ayarlar kaydediliyor...")
        save_config(config)

    wlan = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)

    def attempt_wifi_connect(ssid, password):
        nonlocal failed_wifi_attempts
        try:
            # Önce AP ve STA arayüzlerini tamamen temizleyelim
            if ap.active():
                ap.active(False)
                time.sleep_ms(100)
            if wlan.active():
                wlan.active(False)
                time.sleep_ms(100)

            wlan.active(True)
            time.sleep_ms(100)
            
            display_message("WiFi Baglaniliyor", 0, clear_screen=True, show_now=False)
            display_message(ssid, 1, show_now=False)
            oled.show()
            print("Wi-Fi ağına bağlanılıyor: %s..." % ssid)
            
            wlan.connect(ssid, password)
            
            start_connect_time = time.time()
            while not wlan.isconnected() and (time.time() - start_connect_time) < WIFI_CONNECT_TIMEOUT:
                current_dots = "." * (int(time.time() - start_connect_time) % 4 + 1)
                display_message("Baglaniyor%s" % current_dots, 4, show_now=True)
                time.sleep(1)
            
            if wlan.isconnected():
                failed_wifi_attempts = 0
                print("Wi-Fi'ye bağlandı: %s" % wlan.ifconfig()[0])
                display_message("Baglandi: %s" % wlan.ifconfig()[0], 4, show_now=True)
                time.sleep(1)
                return True
            else:
                failed_wifi_attempts += 1
                print("Wi-Fi bağlantısı başarısız. Deneme %d/%d" % (failed_wifi_attempts, MAX_WIFI_RECONNECT_ATTEMPTS))
                display_message("Baglanti Hatasi!", 4, show_now=True)
                return False
        except Exception as e:
            print("Wi-Fi bağlantı girişimi sırasında beklenmeyen hata: %s - %s" % (type(e).__name__, e))
            display_message("WiFi Hata: %s" % type(e).__name__, 4, show_now=True)
            failed_wifi_attempts += 1
            return False

    wifi_connected = False
    
    while failed_wifi_attempts < MAX_WIFI_RECONNECT_ATTEMPTS:
        if attempt_wifi_connect(config["ssid"], config["password"]):
            wifi_connected = True
            break
        else:
            if failed_wifi_attempts < MAX_WIFI_RECONNECT_ATTEMPTS:
                print("AP moduna geçiş eşiğine ulaşılmadı. %d saniye sonra tekrar denenecek." % WIFI_RETRY_DELAY_SECONDS)
                display_message("Tekrar %ds" % WIFI_RETRY_DELAY_SECONDS, 4, show_now=True)
                time.sleep(WIFI_RETRY_DELAY_SECONDS)
    
    if not wifi_connected:
        print("%d ardışık Wi-Fi denemesi başarısız oldu. AP moduna geçiliyor." % MAX_WIFI_RECONNECT_ATTEMPTS)
        display_message("WiFi Baglanamadi!", 0, clear_screen=True, show_now=False)
        display_message("Kurulum Baslatiliyor", 2, show_now=True)
        time.sleep(2)
        
        # AP modunu başlatmadan önce STA arayüzünü tamamen kapat
        if wlan.active():
            wlan.disconnect()
            wlan.active(False)
            time.sleep_ms(100) # Gecikme ekle

        start_ap_mode_and_web_server(ap_mode_duration_seconds=300)
        
        print("AP modu sonlandı, Wi-Fi bağlantısını tekrar deneme.")
        failed_wifi_attempts = 0
        config, _ = load_config()
        return main_loop() # Ana döngüye geri dön ve tekrar bağlanmayı dene

    print("Normal çalışma moduna geçiliyor.")
    
    last_rss_update_time = 0
    last_ntp_update_time = 0
    vakitler_for_calc = []
    
    # NTP senkronizasyonunda timezone_offset kullanılıyor
    ntp_success = set_time_from_ntp(config["timezone_offset"]) 
    if ntp_success:
        last_ntp_update_time = time.time()
    
    rss_success, temp_vakitler = get_namaz_vakitleri(unquote_plus_custom(config["rss_url"]))
    if rss_success:
        vakitler_for_calc = temp_vakitler
        last_rss_update_time = time.time()
    else:
        print("İlk RSS veri çekimi başarısız. Boş vakitlerle başlanıyor.")
        display_message("RSS Yuklenemedi.", 6, show_now=True)

    while True:
        current_time = time.time()
        
        if not wlan.isconnected():
            print("Wi-Fi bağlantısı koptu! Yeniden bağlanma denemesi için main_loop'a dönülüyor.")
            display_message("WiFi Koptu!", 0, clear_screen=True, show_now=False)
            display_message("Tekrar Deniyor...", 2, show_now=True)
            # Wi-Fi bağlantısı koptuğunda, her iki arayüzü de kapatıp temiz bir başlangıç yapalım
            if wlan.active():
                wlan.disconnect()
                wlan.active(False)
            if ap.active():
                ap.active(False)
            time.sleep(2)
            gc.collect()
            return main_loop()

        if (current_time - last_ntp_update_time >= NTP_UPDATE_INTERVAL_SECONDS) or (last_ntp_update_time == 0):
            print("NTP zamanı güncelleniyor...")
            if set_time_from_ntp(config["timezone_offset"]):
                last_ntp_update_time = current_time
            else:
                print("NTP senkronizasyonu başarısız, bir sonraki döngüde tekrar denenecek.")
        
        if (current_time - last_rss_update_time >= RSS_UPDATE_INTERVAL_SECONDS) or not vakitler_for_calc:
            print("RSS verileri güncelleniyor...")
            decoded_rss_url = unquote_plus_custom(config["rss_url"])
            success, temp_vakitler = get_namaz_vakitleri(decoded_rss_url)
            if success:
                vakitler_for_calc = temp_vakitler
                last_rss_update_time = current_time
            else:
                print("RSS veri çekme başarısız. Mevcut vakitlerle devam ediliyor (varsa) veya bekleniyor.")
                display_message("RSS Cekilemedi.", 6, show_now=True)
                time.sleep(5)

        if not vakitler_for_calc:
            display_message("Vakit Bulunamiyor.", 6, show_now=True)
            time.sleep(10)
            continue

        calculate_and_display_next_prayer_time(vakitler_for_calc)
        
        gc.collect()
        time.sleep(1)

if __name__ == "__main__":
    main_loop()