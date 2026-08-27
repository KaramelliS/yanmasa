"""Özel araç tanımları.

Computer araç seti fare ve klavye veriyor; bunlar onun yapamadığı ya da çok
pahalı yaptığı şeyler.

`launch_app` tek başına en büyük hız kazancı. Ajana Notepad'i Başlat
menüsünden açtırmak dört-beş tur sürüyor: ekran görüntüsü al, Başlat'a tıkla,
görüntü al, yaz, görüntü al, Enter, görüntü al. Her tur bir model çağrısı ve
~1500 token görsel. `launch_app("notepad")` bunu bir tura indiriyor.
"""

from __future__ import annotations

from typing import Any

# Hiçbir araçta `strict: True` yok ve bu bilinçli. Katı şemalar kısıtlı bir
# gramere derleniyor ve tüm araçların toplam gramer boyutunun bir sınırı var;
# 18 aracın hepsi katı olduğunda API isteği "Schema is too complex" ile 400
# dönüyor. Ölçüldü: 12 katı + 6 gevşek geçiyor, 18 katı geçmiyor.
#
# Kaybı küçük: her aracın girdisi zaten `dispatch.py` içinde doğrulanıyor ve
# eksik alan modele "Bu islem icin eksik alan: ref, values" gibi düzeltmesi
# kolay bir hata olarak dönüyor. Yeni araç eklerken katılığa geri dönme —
# sınır araç sayısıyla değil şema boyutuyla ilgili ve sessizce geri gelir.

SWITCH_DISPLAY = {
    "name": "switch_display",
    "description": (
        "Hangi ekranda çalışılacağını değiştirir. Bundan sonraki ekran "
        "görüntüleri ve koordinatlar o ekrana ait olur."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"index": {"type": "integer", "description": "Ekran indeksi"}},
        "required": ["index"],
        "additionalProperties": False,
    },
}

READ_UI_TREE = {
    "name": "read_ui_tree",
    "description": (
        "Ön plandaki pencerenin denetimlerini metin olarak, her birinin "
        "tıklama noktasıyla birlikte döndürür. Ekran görüntüsünden çok daha "
        "ucuz ve koordinatları tahmin değil ölçüm. Bir düğmeyi, menü ögesini "
        "ya da metin kutusunu arıyorsan ÖNCE bunu dene. Sonuç boş ya da "
        "yüzeysel gelirse (tuval, oyun, video, bazı web sayfaları) ekran "
        "görüntüsüne geç."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

LAUNCH_APP = {
    "name": "launch_app",
    "description": (
        "Bir uygulamayı doğrudan başlatır ve öne gelmesini bekler. Başlat "
        "menüsünde tıklamaktan çok daha hızlı — bir uygulama açman "
        "gerektiğinde her zaman bunu kullan. Kurulu her uygulamayı adıyla "
        "açabilirsin ('Discord', 'Spotify', 'Hesap Makinesi'); "
        "çalıştırılabilir adı, tam yol ya da URL de olur. Ad tutmazsa "
        "yakın adayları söyler; hangi uygulamaların kurulu olduğunu "
        "`list_apps` ile görebilirsin."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Uygulama adı, tam yol ya da URL",
            },
            "arguments": {
                "type": "string",
                "description": "İsteğe bağlı komut satırı argümanları",
            },
        },
        "required": ["target"],
        "additionalProperties": False,
    },
}

RUN_SHELL = {
    "name": "run_shell",
    "description": (
        "PowerShell komutu çalıştırır ve çıktısını döndürür. Toplu dosya "
        "işlemleri, sorgular ve arayüzde onlarca tıklama gerektiren işler "
        "için kullan. Geri alınamaz komutlar (silme, kapatma, kayıt defteri, "
        "üzerine yazma) Berkay'ın onayını ister — onay gelmezse komut "
        "çalışmaz. Etkileşimli komut çalıştırma, girdi bekleyen bir komut "
        "zaman aşımına uğrar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "PowerShell komutu"},
            "timeout": {
                "type": "integer",
                "description": "Saniye cinsinden zaman aşımı, varsayılan 30",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}

WRITE_FILE = {
    "name": "write_file",
    "description": (
        "Bir dosyaya UTF-8 metin yazar. Klasör yoksa oluşturulur. Var olan "
        "bir dosyanın üzerine yazmak Berkay'ın onayını ister; bir bölümünü "
        "değiştireceksen write_file yerine edit_file kullan, o onay istemez."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Dosya yolu"},
            "content": {"type": "string", "description": "Yazılacak içerik"},
            "append": {
                "type": "boolean",
                "description": "Üzerine yazmak yerine sona ekle",
            },
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
}

READ_FILE = {
    "name": "read_file",
    "description": "Bir dosyayı UTF-8 olarak okur. Uzun dosyalar kesilir.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
}

EDIT_FILE = {
    "name": "edit_file",
    "description": (
        "Bir dosyada birebir metin değişimi yapar. `old` dosyada tam olarak "
        "bir kez geçmeli; sıfır ya da birden fazla geçerse hiçbir şey "
        "yazılmaz ve hata döner. Düzenlemeden önce dosyayı oku."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string", "description": "Değiştirilecek birebir metin"},
            "new": {"type": "string", "description": "Yerine yazılacak metin"},
        },
        "required": ["path", "old", "new"],
        "additionalProperties": False,
    },
}

LIST_DIR = {
    "name": "list_dir",
    "description": "Bir klasörün içeriğini listeler.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
}

TERMINAL_OPEN = {
    "name": "terminal_open",
    "description": (
        "Kalıcı bir terminal oturumu açar ve ekranını döndürür. `run_shell`'in "
        "aksine oturum açık kalır, yani etkileşimli programlar çalışır: "
        "Claude Code, opencode, REPL'ler, `git rebase -i`, sunucular. "
        "Uzun süren ya da girdi bekleyen her şey için bunu kullan."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Oturuma vereceğin ad"},
            "command": {
                "type": "string",
                "description": "Çalıştırılacak komut; boşsa PowerShell açılır",
            },
            "cwd": {"type": "string", "description": "Çalışma klasörü"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TERMINAL_SEND = {
    "name": "terminal_send",
    "description": (
        "Açık bir terminale metin ya da tuş gönderir, ekran durulunca son "
        "halini döndürür. `text` yazılacak metin; `key` özel tuş "
        "(enter, tab, escape, up, down, left, right, ctrl+c, ctrl+d, "
        "page_up, page_down, backspace, shift+tab). Komut çalıştırmak için "
        "text ver ve submit'i true bırak. TUI'de gezinmek için key kullan."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "text": {"type": "string"},
            "key": {"type": "string"},
            "submit": {
                "type": "boolean",
                "description": "Metinden sonra Enter gönder, varsayılan true",
            },
            "wait": {
                "type": "number",
                "description": "Ekranın durulması için en fazla kaç saniye, varsayılan 15",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TERMINAL_READ = {
    "name": "terminal_read",
    "description": (
        "Bir terminalin şu anki ekranını döndürür. Uzun süren bir işin "
        "ilerlemesine bakmak için kullan — göndermeden sadece okur."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "wait": {
                "type": "number",
                "description": "Okumadan önce durulmayı bekle, saniye",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TERMINAL_CLOSE = {
    "name": "terminal_close",
    "description": "Bir terminal oturumunu kapatır ve içindeki süreci sonlandırır.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
}


# --- Ofis ---------------------------------------------------------------
#
# `why` her düzenleme aracında **zorunlu**. İsteğe bağlı olsaydı model çoğu
# zaman atlardı ve gerekçe defteri yarı dolu kalırdı; yarı dolu bir defter
# hiç olmamasından kötüdür, çünkü güvenilir sanılır.

OFFICE_OPEN = {
    "name": "office_open",
    "description": (
        "Bir tablo (.xlsx) ya da yazı belgesi (.docx) açar; dosya yoksa "
        "oluşturur. Microsoft Office gerekmez, dosyalar gerçek Office "
        "biçiminde ve Excel/Word'de açılır. Belgeye verdiğin adla erişirsin."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Belgeye vereceğin ad"},
            "path": {"type": "string", "description": "Dosya yolu (.xlsx ya da .docx)"},
        },
        "required": ["name", "path"],
        "additionalProperties": False,
    },
}

OFFICE_READ = {
    "name": "office_read",
    "description": (
        "Açık bir belgeyi okur. Tabloda `ref` hücre aralığı (A1, B2:D20) ve "
        "`sheet` sayfa adı; yazı belgesinde `start` paragraf numarası. "
        "Düzenlemeden önce her zaman oku — paragraf numaraları ve hücre "
        "içerikleri değişmiş olabilir."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "ref": {"type": "string", "description": "Tablo için hücre aralığı"},
            "sheet": {"type": "string", "description": "Tablo için sayfa adı"},
            "start": {"type": "integer", "description": "Yazı için başlangıç paragrafı"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

OFFICE_EDIT = {
    "name": "office_edit",
    "description": (
        "Belgeyi düzenler. `why` zorunlu — her değişiklik neden yapıldığını "
        "taşır ve bu kayıt Berkay'a gösterilir. "
        "Tablo işlemleri: `write` (ref + values, values satır listesi; "
        "'=SUM(B2:B4)' gibi formül yazabilirsin), `add_sheet` (sheet). "
        "Yazı işlemleri: `append` (text, isteğe bağlı style: Title, "
        "Heading 1, Heading 2, List Bullet, Quote), `replace` (index + text), "
        "`add_table` (values)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["write", "add_sheet", "append", "replace", "add_table"],
            },
            "why": {
                "type": "string",
                "description": "Bu değişiklik neden yapılıyor; değerin kaynağı nedir",
            },
            "ref": {"type": "string"},
            "sheet": {"type": "string"},
            "values": {
                "type": "array",
                "description": "Satır listesi; her satır hücre listesi",
                "items": {"type": "array", "items": {}},
            },
            "text": {"type": "string"},
            "style": {"type": "string"},
            "index": {"type": "integer"},
        },
        "required": ["name", "operation", "why"],
        "additionalProperties": False,
    },
}

OFFICE_SAVE = {
    "name": "office_save",
    "description": "Belgeyi diske kaydeder. `path` verirsen farklı kaydeder.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "path": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
}

OFFICE_HISTORY = {
    "name": "office_history",
    "description": (
        "Belgedeki değişikliklerin gerekçeli listesini döndürür. `undo` "
        "verirsen son o kadar değişikliği geri alır."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "undo": {"type": "integer", "description": "Geri alınacak değişiklik sayısı"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

OFFICE_CLOSE = {
    "name": "office_close",
    "description": (
        "Belgeyi kapatır. Kaydedilmemiş değişiklik varsa reddeder; bilerek "
        "atıyorsan discard=true ver."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "discard": {"type": "boolean"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

SKILL_LIST = {
    "name": "skill_list",
    "description": (
        "Yazılmış yetenekleri ve yüklenemeyen bozuk dosyaları listeler. "
        "Bir yeteneğin kodunu görmek için name ver."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Kodunu okumak istediğin yeteneğin adı",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
}

SKILL_WRITE = {
    "name": "skill_write",
    "description": (
        "Kendine yeni bir yetenek yazar ya da var olanı düzeltir. Yetenek bir "
        "Python dosyası: ARAC sözlüğü ile calistir(girdi, ortam) fonksiyonu. "
        "Yazıldığı anda yüklenir ve bir sonraki adımda çağırabilirsin. "
        "Var olan bir aracın adını kullanamazsın. Her yazma Berkay'ın onayını "
        "ister ve kodun tamamı ona gösterilir."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Dosya ve araç adı: küçük harf, rakam, alt çizgi",
            },
            "code": {"type": "string", "description": "Yeteneğin tam Python kodu"},
            "why": {
                "type": "string",
                "description": "Bu yeteneği neden yazıyorsun — Berkay onay ekranında görecek",
            },
        },
        "required": ["name", "code", "why"],
        "additionalProperties": False,
    },
}

SKILL_REMOVE = {
    "name": "skill_remove",
    "description": "Bir yeteneği siler.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "why": {"type": "string", "description": "Neden siliniyor"},
        },
        "required": ["name", "why"],
        "additionalProperties": False,
    },
}

BUTTON_WRITE = {
    "name": "button_write",
    "description": (
        "Berkay'ın çubuğundaki düğmelerden birini kurar ya da değiştirir. "
        "Düğmeye tıklayınca yazdığın talimat ajana gönderilir. Tekrar eden "
        "bir iş fark ettiğinde teklif et: 'bunu düğme yapayım mı'. "
        "Berkay bu düğmeleri kendisi de düzenleyip silebilir."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Kimlik: küçük harf, rakam, alt çizgi"},
            "label": {"type": "string", "description": "Düğmenin üstünde yazan, en fazla 22 karakter"},
            "instruction": {
                "type": "string",
                "description": "Tıklanınca sana gönderilecek talimat",
            },
            "glyph": {
                "type": "string",
                "description": (
                    "Çizim: goz, mercek, imlec, surukle, klavye, tus, kaydir, "
                    "pencere, kabuk, agac, sayfa, klasor, tablo, yazi, kaydet, "
                    "defter, yetenek, bekle"
                ),
            },
            "why": {"type": "string", "description": "Neden bu düğme"},
        },
        "required": ["name", "label", "instruction", "why"],
        "additionalProperties": False,
    },
}

BUTTON_REMOVE = {
    "name": "button_remove",
    "description": "Bir düğmeyi kaldırır.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "why": {"type": "string"},
        },
        "required": ["name", "why"],
        "additionalProperties": False,
    },
}

REMOTE_CONNECT = {
    "name": "remote_connect",
    "description": (
        "SSH ile bir sunucuya bağlanır. `alias` verilirse ~/.ssh/config "
        "içindeki ayar kullanılır (Berkay'ın sunucusu: brky). Bağlandıktan "
        "sonra remote_list, remote_read, remote_write, remote_run çalışır ve "
        "arayüzde sunucunun klasörleri açılır."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "alias": {"type": "string", "description": "~/.ssh/config takma adı"},
            "host": {"type": "string"},
            "user": {"type": "string"},
            "port": {"type": "integer"},
        },
        "required": [],
        "additionalProperties": False,
    },
}

REMOTE_LIST = {
    "name": "remote_list",
    "description": "Sunucudaki bir klasörü listeler. Boş bırakırsan bulunduğun yeri.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    },
}

REMOTE_READ = {
    "name": "remote_read",
    "description": "Sunucudaki bir dosyayı okur.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
}

REMOTE_WRITE = {
    "name": "remote_write",
    "description": (
        "Sunucudaki bir dosyaya yazar; varsa üzerine yazar. Her zaman onay "
        "ister. Üzerine yazmadan önce remote_read ile mevcut hâlini oku."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "why": {"type": "string", "description": "Neden bu değişiklik"},
        },
        "required": ["path", "content", "why"],
        "additionalProperties": False,
    },
}

REMOTE_RUN = {
    "name": "remote_run",
    "description": (
        "Sunucuda kabuk komutu çalıştırır. Okuyan komutlar (ls, cat, df, "
        "systemctl status, journalctl) doğrudan çalışır; değiştiren her "
        "komut Berkay'a sorulur."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": "Saniye, varsayılan 60"},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}

LIST_APPS = {
    "name": "list_apps",
    "description": (
        "Kurulu uygulamaları listeler. Bir uygulamanın adından emin "
        "değilsen önce buna bak; Başlat menüsünde ekran görüntüsüyle "
        "aramaktan çok daha ucuz."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Arama metni. Boş bırakırsan hepsi listelenir.",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
}

WRITE_FILES = {
    "name": "write_files",
    "description": (
        "Birden çok dosyayı TEK çağrıda yazar. Bir proje ya da betik "
        "kurarken bunu kullan: dosya başına ayrı çağrı, dosya başına ayrı "
        "model turu demek ve işi kat kat yavaşlatıyor. Klasörler "
        "kendiliğinden açılıyor. Var olan bir dosyanın üzerine yazmak onay "
        "ister; yeni dosya istemez."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "Yazılacak dosyalar",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            "why": {"type": "string", "description": "Ne kuruluyor"},
        },
        "required": ["files"],
        "additionalProperties": False,
    },
}

# --- yan çalışma alanı ------------------------------------------------------
#
# Bunlar `computer` araç setinin karşılığı değil, **paraleli**. Computer
# araçları fiziksel fareyi sürüyor ve çalıştıkları sürece Berkay'ın
# bilgisayarını işgal ediyorlar. Yan alan görünmez bir masaüstünde duruyor;
# ajan orada çalışırken Berkay kendi işine devam edebiliyor.

SIDE_LAUNCH = {
    "name": "side_launch",
    "description": (
        "Bir uygulamayı YAN ÇALIŞMA ALANINDA başlatır — görünmez bir "
        "masaüstünde. Berkay'ın ekranında hiçbir şey açılmaz, imleci ve "
        "odağı hiç kıpırdamaz, yani sen çalışırken o da çalışabilir. "
        "Uzun süren tarayıcı işleri için tercih et. Sınır: Microsoft Store "
        "uygulamaları (Win11 Not Defteri dahil) burada pencere açmıyor; "
        "klasik .exe ve Chrome çalışıyor."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Tam komut satırı. Yolu tırnak içine al, örn: "
                    '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                    "https://ornek.com"
                ),
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}

SIDE_WINDOWS = {
    "name": "side_windows",
    "description": (
        "Yan çalışma alanındaki pencereleri listeler: hwnd, başlık, sınıf ve "
        "konum. Tıklamadan ve görüntü almadan önce buradan hwnd al."
    ),
    "input_schema": {
        "type": "object", "properties": {}, "additionalProperties": False,
    },
}

SIDE_CAPTURE = {
    "name": "side_capture",
    "description": (
        "Yan alandaki bir pencerenin görüntüsünü alır. Koordinatlar "
        "pencerenin sol üst köşesine göre; side_act aynı uzayı kullanıyor."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"hwnd": {"type": "integer", "description": "Pencere tutamacı"}},
        "required": ["hwnd"],
        "additionalProperties": False,
    },
}

SIDE_ACT = {
    "name": "side_act",
    "description": (
        "Yan alanda tıklar, yazar, tuşa basar ya da kaydırır. Ajanın kendi "
        "imleci kullanılır; Berkay'ın faresi kıpırdamaz. Kısayol "
        "kombinasyonları (Ctrl+S gibi) BURADA ÇALIŞMAZ — menüye tıkla."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hwnd": {"type": "integer"},
            "action": {
                "type": "string",
                "enum": ["click", "right_click", "double_click", "type", "key", "scroll"],
            },
            "coordinate": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[x, y], pencerenin sol üstüne göre",
            },
            "text": {
                "type": "string",
                "description": "type icin metin, key icin tus adi (enter, tab, escape, f5...)",
            },
            "amount": {"type": "integer", "description": "scroll adimi; pozitif yukari"},
        },
        "required": ["hwnd", "action"],
        "additionalProperties": False,
    },
}

SIDE_CLOSE = {
    "name": "side_close",
    "description": (
        "Yan çalışma alanını kapatır ve orada başlattığın her uygulamayı "
        "sonlandırır. İşin bitince çağır; yoksa süreçler görünmez şekilde "
        "arkada yaşamaya devam eder."
    ),
    "input_schema": {
        "type": "object", "properties": {}, "additionalProperties": False,
    },
}

CUSTOM_TOOLS: list[dict[str, Any]] = [
    READ_UI_TREE,
    LAUNCH_APP,
    LIST_APPS,
    RUN_SHELL,
    SWITCH_DISPLAY,
    WRITE_FILE,
    WRITE_FILES,
    READ_FILE,
    EDIT_FILE,
    LIST_DIR,
    TERMINAL_OPEN,
    TERMINAL_SEND,
    TERMINAL_READ,
    TERMINAL_CLOSE,
    OFFICE_OPEN,
    OFFICE_READ,
    OFFICE_EDIT,
    OFFICE_SAVE,
    OFFICE_HISTORY,
    OFFICE_CLOSE,
    SKILL_LIST,
    SKILL_WRITE,
    SKILL_REMOVE,
    BUTTON_WRITE,
    BUTTON_REMOVE,
    REMOTE_CONNECT,
    REMOTE_LIST,
    REMOTE_READ,
    REMOTE_WRITE,
    REMOTE_RUN,
    SIDE_LAUNCH,
    SIDE_WINDOWS,
    SIDE_CAPTURE,
    SIDE_ACT,
    SIDE_CLOSE,
]

CUSTOM_TOOL_NAMES = {tool["name"] for tool in CUSTOM_TOOLS}
