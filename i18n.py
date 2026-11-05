"""Bot ke saare user-facing messages 21 languages mein.

t(lang, key, **kw) -> translated text (English fallback).
Admin / owner commands ke messages English mein hi rehte hain.
"""
from collections import OrderedDict

# code -> (flag, name in its own language)  - same list and order as the language menu
UI_LANGS = OrderedDict(
    [
        ("fa", ("🇮🇷", "زبان فارسی")),
        ("en", ("🇬🇧", "English")),
        ("uz", ("🇺🇿", "O'zbek")),
        ("ru", ("🇷🇺", "Русский")),
        ("es", ("🇪🇸", "Español")),
        ("ar", ("🇸🇦", "اللغة العربية")),
        ("tr", ("🇹🇷", "Türkçe")),
        ("hi", ("🇮🇳", "हिंदी")),
        ("vi", ("🇻🇳", "Tiếng Việt")),
        ("uk", ("🇺🇦", "Українська")),
        ("id", ("🇮🇩", "Bahasa Indonesia")),
        ("ms", ("🇲🇾", "Melayu")),
        ("ko", ("🇰🇷", "한국인")),
        ("pt", ("🇧🇷", "Português")),
        ("zh", ("🇨🇳", "中國人")),
        ("fr", ("🇫🇷", "Français")),
        ("de", ("🇩🇪", "Deutsch")),
        ("it", ("🇮🇹", "Italiano")),
        ("he", ("🇮🇱", "עברית")),
        ("nl", ("🇳🇱", "Nederlands")),
        ("sv", ("🇸🇪", "Svenska")),
    ]
)

KEYS = (
    # A
    "welcome", "hello", "f_fast", "f_inst", "f_auto", "tip",
    # B
    "b_help", "b_about", "b_home", "b_owner", "b_updates", "b_support", "b_lang",
    # C
    "h_title", "h_1", "h_2", "h_3", "h_tips", "h_t1", "h_t2", "h_t3",
    # D
    "a_title", "a_files", "a_users", "a_bot",
    # E
    "j_title", "j_msg", "j_prog", "j_chan", "j_done", "j_not_all", "j_thanks", "j_first",
    # F
    "r_title", "r_query", "r_found", "r_page", "r_qual", "r_season", "r_fuzzy", "r_pick", "r_clear", "r_close",
    # G
    "r_expired", "r_gone", "r_sent", "r_fail",
    # H
    "n_title", "n_try", "n_1", "n_2", "n_3",
    # I
    "c_size", "c_save", "l_set", "r_mine",
)

_RAW = {
    "en": [
        "Send me the <b>name</b> of any Movie or Series and I'll find the file and send it instantly.", "Hello", "Fast Search", "Instant Delivery", "Auto-delete", "Tip: type a short name, like",
        "Help", "About", "Home", "Owner", "Updates", "Support", "Language",
        "How To Use", "Send the <b>name</b> of a movie", "Pick your <b>file</b> from the result list", "Once you get the file, <b>save or forward</b> it (it gets deleted in {m} min)", "Tips", "Use a short and simple name", "Use the buttons to filter by quality, language and season", "You can type in any language or script (हिंदी, English, عربي ...)",
        "About", "Files", "Users", "Bot",
        "Access Locked", "Join the <b>{n}</b> channel(s) below to use this bot, then tap ✓.", "Progress", "Join Channel {n}", "I Have Joined", "You haven't joined all the channels yet!", "Thank you! Now send the name of a Movie/Series.", "Please join all the channels first!",
        "Search Results", "Query", "Found", "Page", "Quality", "Season", "No exact match found, showing similar results", "Choose filter / file", "Clear Filters", "Close",
        "This search has expired, please send the name again.", "This file is no longer available.", "File sent ✓", "Couldn't get the file, please try again later.",
        "Nothing Found", "Try this", "Check the spelling", "Use a shorter name (just the main word)", "Type in English letters or in your own language",
        "Size", "Save or forward it now", "Language changed ✓", "This search belongs to someone else. Please send your own.",
    ],
    "hi": [
        "मुझे किसी भी मूवी या सीरीज़ का <b>नाम</b> भेजें, मैं फ़ाइल ढूंढकर तुरंत भेज दूँगा।", "नमस्ते", "तेज़ सर्च", "तुरंत डिलीवरी", "ऑटो-डिलीट", "टिप: छोटा नाम लिखें, जैसे",
        "मदद", "जानकारी", "होम", "ओनर", "अपडेट्स", "सपोर्ट", "भाषा",
        "कैसे इस्तेमाल करें", "मूवी का <b>नाम</b> भेजें", "रिज़ल्ट लिस्ट से अपनी <b>फ़ाइल</b> चुनें", "फ़ाइल मिलते ही उसे <b>सेव या फ़ॉरवर्ड</b> कर लें ({m} मिनट में डिलीट हो जाएगी)", "टिप्स", "छोटा और आसान नाम लिखें", "क्वालिटी, भाषा और सीज़न से फ़िल्टर करने के लिए बटन दबाएँ", "आप किसी भी भाषा या लिपि में लिख सकते हैं (हिंदी, English, عربي ...)",
        "के बारे में", "फ़ाइलें", "यूज़र्स", "बॉट",
        "एक्सेस लॉक्ड", "इस बॉट का इस्तेमाल करने के लिए नीचे दिए <b>{n}</b> चैनल जॉइन करें, फिर ✓ दबाएँ।", "प्रगति", "चैनल {n} जॉइन करें", "मैंने जॉइन कर लिया", "आपने अभी सभी चैनल जॉइन नहीं किए हैं!", "धन्यवाद! अब मूवी/सीरीज़ का नाम भेजें।", "पहले सभी चैनल जॉइन करें!",
        "सर्च रिज़ल्ट", "सर्च", "मिले", "पेज", "क्वालिटी", "सीज़न", "सही मैच नहीं मिला, मिलते-जुलते रिज़ल्ट दिखा रहा हूँ", "फ़िल्टर / फ़ाइल चुनें", "फ़िल्टर हटाएँ", "बंद करें",
        "यह सर्च एक्सपायर हो गई, कृपया नाम फिर से भेजें।", "यह फ़ाइल अब उपलब्ध नहीं है।", "फ़ाइल भेज दी गई ✓", "फ़ाइल नहीं मिल सकी, कृपया बाद में कोशिश करें।",
        "कुछ नहीं मिला", "ये आज़माएँ", "स्पेलिंग जाँचें", "और छोटा नाम लिखें (सिर्फ़ मुख्य शब्द)", "अंग्रेज़ी अक्षरों में या अपनी भाषा में लिखें",
        "साइज़", "अभी सेव या फ़ॉरवर्ड कर लें", "भाषा बदल गई ✓", "यह सर्च किसी और की है। कृपया अपनी सर्च खुद भेजें।",
    ],
    "fa": [
        "نام هر فیلم یا سریالی را برای من بفرستید تا فایل را پیدا کنم و فوراً ارسال کنم.", "سلام", "جستجوی سریع", "ارسال فوری", "حذف خودکار", "نکته: نام کوتاه بنویسید، مثل",
        "راهنما", "درباره", "خانه", "مالک", "به‌روزرسانی‌ها", "پشتیبانی", "زبان",
        "طریقه استفاده", "<b>نام</b> فیلم را بفرستید", "<b>فایل</b> خود را از فهرست نتایج انتخاب کنید", "پس از دریافت فایل، آن را <b>ذخیره یا فوروارد</b> کنید (بعد از {m} دقیقه حذف می‌شود)", "نکات", "نام کوتاه و ساده بنویسید", "برای فیلتر کردن بر اساس کیفیت، زبان و فصل از دکمه‌ها استفاده کنید", "می‌توانید به هر زبان یا خطی بنویسید (हिंदी, English, عربي ...)",
        "درباره", "فایل‌ها", "کاربران", "ربات",
        "دسترسی قفل است", "برای استفاده از این ربات در <b>{n}</b> کانال زیر عضو شوید، سپس ✓ را بزنید.", "پیشرفت", "عضویت در کانال {n}", "عضو شدم", "هنوز در همه کانال‌ها عضو نشده‌اید!", "ممنون! حالا نام فیلم یا سریال را بفرستید.", "ابتدا در همه کانال‌ها عضو شوید!",
        "نتایج جستجو", "جستجو", "یافت شد", "صفحه", "کیفیت", "فصل", "تطابق دقیقی پیدا نشد، نتایج مشابه نمایش داده می‌شود", "فیلتر / فایل را انتخاب کنید", "حذف فیلترها", "بستن",
        "این جستجو منقضی شده، لطفاً دوباره نام را بفرستید.", "این فایل دیگر در دسترس نیست.", "فایل ارسال شد ✓", "فایل دریافت نشد، لطفاً بعداً دوباره تلاش کنید.",
        "چیزی پیدا نشد", "این را امتحان کنید", "املا را بررسی کنید", "نام کوتاه‌تری بنویسید (فقط کلمه اصلی)", "با حروف انگلیسی یا به زبان خودتان بنویسید",
        "حجم", "همین حالا ذخیره یا فوروارد کنید", "زبان تغییر کرد ✓", "این جستجو متعلق به شخص دیگری است. لطفاً جستجوی خودتان را بفرستید.",
    ],
    "uz": [
        "Menga istalgan film yoki serialning <b>nomini</b> yuboring, men faylni topib, darhol jo'nataman.", "Salom", "Tezkor qidiruv", "Zudlik bilan yetkazish", "Avto-o'chirish", "Maslahat: qisqa nom yozing, masalan",
        "Yordam", "Haqida", "Bosh sahifa", "Egasi", "Yangiliklar", "Qo'llab-quvvatlash", "Til",
        "Qanday foydalanish", "Film <b>nomini</b> yuboring", "Natijalar ro'yxatidan <b>faylni</b> tanlang", "Faylni olgach, uni <b>saqlang yoki yo'naltiring</b> ({m} daqiqada o'chadi)", "Maslahatlar", "Qisqa va oddiy nom yozing", "Sifat, til va fasl bo'yicha saralash uchun tugmalardan foydalaning", "Istalgan til yoki yozuvda yozishingiz mumkin (हिंदी, English, عربي ...)",
        "Bot haqida", "Fayllar", "Foydalanuvchilar", "Bot",
        "Kirish yopiq", "Botdan foydalanish uchun quyidagi <b>{n}</b> ta kanalga a'zo bo'ling, so'ng ✓ tugmasini bosing.", "Jarayon", "{n}-kanalga qo'shilish", "A'zo bo'ldim", "Siz hali barcha kanallarga a'zo bo'lmagansiz!", "Rahmat! Endi film/serial nomini yuboring.", "Avval barcha kanallarga a'zo bo'ling!",
        "Qidiruv natijalari", "So'rov", "Topildi", "Sahifa", "Sifat", "Fasl", "Aniq moslik topilmadi, o'xshash natijalar ko'rsatilmoqda", "Filtr / faylni tanlang", "Filtrlarni tozalash", "Yopish",
        "Bu qidiruv eskirgan, iltimos nomni qayta yuboring.", "Bu fayl endi mavjud emas.", "Fayl yuborildi ✓", "Faylni olib bo'lmadi, keyinroq urinib ko'ring.",
        "Hech narsa topilmadi", "Buni sinab ko'ring", "Imloni tekshiring", "Qisqaroq nom yozing (faqat asosiy so'z)", "Lotin harflarida yoki o'z tilingizda yozing",
        "Hajmi", "Hozir saqlang yoki yo'naltiring", "Til o'zgartirildi ✓", "Bu qidiruv boshqa foydalanuvchiniki. O'zingiznikini yuboring.",
    ],
    "ru": [
        "Отправьте мне <b>название</b> любого фильма или сериала, и я найду файл и сразу отправлю его.", "Привет", "Быстрый поиск", "Мгновенная отправка", "Автоудаление", "Совет: пишите короткое название, например",
        "Помощь", "О боте", "Главная", "Владелец", "Обновления", "Поддержка", "Язык",
        "Как пользоваться", "Отправьте <b>название</b> фильма", "Выберите <b>файл</b> из списка результатов", "Получив файл, <b>сохраните или перешлите</b> его (он удалится через {m} мин)", "Советы", "Пишите короткое и простое название", "Кнопки помогают фильтровать по качеству, языку и сезону", "Можно писать на любом языке и алфавите (हिंदी, English, عربي ...)",
        "О боте", "Файлы", "Пользователи", "Бот",
        "Доступ закрыт", "Чтобы пользоваться ботом, подпишитесь на <b>{n}</b> канал(ов) ниже, затем нажмите ✓.", "Прогресс", "Подписаться на канал {n}", "Я подписался", "Вы ещё не подписались на все каналы!", "Спасибо! Теперь отправьте название фильма или сериала.", "Сначала подпишитесь на все каналы!",
        "Результаты поиска", "Запрос", "Найдено", "Страница", "Качество", "Сезон", "Точных совпадений нет, показаны похожие результаты", "Выберите фильтр / файл", "Сбросить фильтры", "Закрыть",
        "Поиск устарел, отправьте название ещё раз.", "Этот файл больше недоступен.", "Файл отправлен ✓", "Не удалось получить файл, попробуйте позже.",
        "Ничего не найдено", "Попробуйте", "Проверьте написание", "Введите название короче (только главное слово)", "Пишите латиницей или на своём языке",
        "Размер", "Сохраните или перешлите сейчас", "Язык изменён ✓", "Этот поиск принадлежит другому пользователю. Отправьте свой запрос.",
    ],
    "es": [
        "Envíame el <b>nombre</b> de cualquier película o serie y encontraré el archivo y te lo enviaré al instante.", "Hola", "Búsqueda rápida", "Entrega instantánea", "Autoeliminación", "Consejo: escribe un nombre corto, como",
        "Ayuda", "Acerca de", "Inicio", "Propietario", "Novedades", "Soporte", "Idioma",
        "Cómo usar", "Envía el <b>nombre</b> de una película", "Elige tu <b>archivo</b> de la lista de resultados", "Cuando recibas el archivo, <b>guárdalo o reenvíalo</b> (se elimina en {m} min)", "Consejos", "Usa un nombre corto y sencillo", "Usa los botones para filtrar por calidad, idioma y temporada", "Puedes escribir en cualquier idioma o alfabeto (हिंदी, English, عربي ...)",
        "Acerca de", "Archivos", "Usuarios", "Bot",
        "Acceso bloqueado", "Únete a los <b>{n}</b> canal(es) de abajo para usar este bot y luego pulsa ✓.", "Progreso", "Unirse al canal {n}", "Ya me uní", "¡Aún no te has unido a todos los canales!", "¡Gracias! Ahora envía el nombre de una película o serie.", "¡Primero únete a todos los canales!",
        "Resultados de búsqueda", "Búsqueda", "Encontrados", "Página", "Calidad", "Temporada", "No hay coincidencia exacta, se muestran resultados similares", "Elige filtro / archivo", "Quitar filtros", "Cerrar",
        "Esta búsqueda caducó, envía el nombre otra vez.", "Este archivo ya no está disponible.", "Archivo enviado ✓", "No se pudo obtener el archivo, inténtalo más tarde.",
        "No se encontró nada", "Prueba esto", "Revisa la ortografía", "Usa un nombre más corto (solo la palabra principal)", "Escribe con letras latinas o en tu idioma",
        "Tamaño", "Guárdalo o reenvíalo ahora", "Idioma cambiado ✓", "Esta búsqueda es de otra persona. Envía la tuya.",
    ],
    "ar": [
        "أرسل لي <b>اسم</b> أي فيلم أو مسلسل وسأجد الملف وأرسله لك فوراً.", "مرحباً", "بحث سريع", "تسليم فوري", "حذف تلقائي", "نصيحة: اكتب اسماً قصيراً، مثل",
        "مساعدة", "حول", "الرئيسية", "المالك", "التحديثات", "الدعم", "اللغة",
        "طريقة الاستخدام", "أرسل <b>اسم</b> الفيلم", "اختر <b>ملفك</b> من قائمة النتائج", "بعد وصول الملف، <b>احفظه أو أعد توجيهه</b> (يُحذف بعد {m} دقيقة)", "نصائح", "اكتب اسماً قصيراً وبسيطاً", "استخدم الأزرار للتصفية حسب الجودة واللغة والموسم", "يمكنك الكتابة بأي لغة أو خط (हिंदी, English, عربي ...)",
        "حول", "الملفات", "المستخدمون", "البوت",
        "الوصول مقفل", "انضم إلى <b>{n}</b> قناة/قنوات أدناه لاستخدام البوت ثم اضغط ✓.", "التقدم", "الانضمام إلى القناة {n}", "لقد انضممت", "لم تنضم إلى جميع القنوات بعد!", "شكراً! الآن أرسل اسم الفيلم أو المسلسل.", "انضم إلى جميع القنوات أولاً!",
        "نتائج البحث", "البحث", "تم العثور", "صفحة", "الجودة", "الموسم", "لا توجد نتيجة مطابقة تماماً، تُعرض نتائج مشابهة", "اختر فلتراً / ملفاً", "مسح الفلاتر", "إغلاق",
        "انتهت صلاحية هذا البحث، أرسل الاسم مرة أخرى.", "هذا الملف لم يعد متاحاً.", "تم إرسال الملف ✓", "تعذر الحصول على الملف، حاول لاحقاً.",
        "لم يتم العثور على شيء", "جرّب هذا", "تحقق من الإملاء", "استخدم اسماً أقصر (الكلمة الرئيسية فقط)", "اكتب بالحروف الإنجليزية أو بلغتك",
        "الحجم", "احفظه أو أعد توجيهه الآن", "تم تغيير اللغة ✓", "هذا البحث يخص شخصاً آخر. أرسل بحثك الخاص.",
    ],
    "tr": [
        "Bana herhangi bir film veya dizinin <b>adını</b> gönder, dosyayı bulup hemen göndereyim.", "Merhaba", "Hızlı Arama", "Anında Teslimat", "Otomatik silme", "İpucu: kısa bir ad yaz, örneğin",
        "Yardım", "Hakkında", "Ana Sayfa", "Sahibi", "Güncellemeler", "Destek", "Dil",
        "Nasıl Kullanılır", "Bir filmin <b>adını</b> gönder", "Sonuç listesinden <b>dosyanı</b> seç", "Dosyayı alınca <b>kaydet veya ilet</b> ({m} dk sonra silinir)", "İpuçları", "Kısa ve basit bir ad kullan", "Kalite, dil ve sezona göre filtrelemek için düğmeleri kullan", "Herhangi bir dilde veya alfabede yazabilirsin (हिंदी, English, عربي ...)",
        "Hakkında", "Dosyalar", "Kullanıcılar", "Bot",
        "Erişim Kilitli", "Botu kullanmak için aşağıdaki <b>{n}</b> kanala katıl, sonra ✓ düğmesine bas.", "İlerleme", "{n}. Kanala Katıl", "Katıldım", "Henüz tüm kanallara katılmadın!", "Teşekkürler! Şimdi bir film/dizi adı gönder.", "Önce tüm kanallara katıl!",
        "Arama Sonuçları", "Sorgu", "Bulundu", "Sayfa", "Kalite", "Sezon", "Tam eşleşme yok, benzer sonuçlar gösteriliyor", "Filtre / dosya seç", "Filtreleri Temizle", "Kapat",
        "Bu aramanın süresi doldu, lütfen adı tekrar gönder.", "Bu dosya artık mevcut değil.", "Dosya gönderildi ✓", "Dosya alınamadı, lütfen sonra tekrar dene.",
        "Hiçbir şey bulunamadı", "Şunu dene", "Yazımı kontrol et", "Daha kısa bir ad kullan (sadece ana kelime)", "İngilizce harflerle veya kendi dilinde yaz",
        "Boyut", "Şimdi kaydet veya ilet", "Dil değiştirildi ✓", "Bu arama başkasına ait. Lütfen kendi aramanı gönder.",
    ],
    "vi": [
        "Hãy gửi cho tôi <b>tên</b> bất kỳ bộ phim hoặc series nào, tôi sẽ tìm tệp và gửi ngay.", "Xin chào", "Tìm kiếm nhanh", "Gửi tức thì", "Tự động xóa", "Mẹo: gõ tên ngắn, ví dụ",
        "Trợ giúp", "Giới thiệu", "Trang chủ", "Chủ sở hữu", "Cập nhật", "Hỗ trợ", "Ngôn ngữ",
        "Cách sử dụng", "Gửi <b>tên</b> bộ phim", "Chọn <b>tệp</b> từ danh sách kết quả", "Khi nhận được tệp, hãy <b>lưu hoặc chuyển tiếp</b> (sẽ bị xóa sau {m} phút)", "Mẹo", "Dùng tên ngắn và đơn giản", "Dùng các nút để lọc theo chất lượng, ngôn ngữ và mùa", "Bạn có thể gõ bằng mọi ngôn ngữ hoặc chữ viết (हिंदी, English, عربي ...)",
        "Giới thiệu", "Tệp", "Người dùng", "Bot",
        "Truy cập bị khóa", "Hãy tham gia <b>{n}</b> kênh bên dưới để dùng bot, rồi nhấn ✓.", "Tiến độ", "Tham gia kênh {n}", "Tôi đã tham gia", "Bạn chưa tham gia tất cả các kênh!", "Cảm ơn! Giờ hãy gửi tên phim/series.", "Hãy tham gia tất cả các kênh trước!",
        "Kết quả tìm kiếm", "Từ khóa", "Tìm thấy", "Trang", "Chất lượng", "Mùa", "Không có kết quả khớp chính xác, hiển thị kết quả tương tự", "Chọn bộ lọc / tệp", "Xóa bộ lọc", "Đóng",
        "Lượt tìm này đã hết hạn, vui lòng gửi lại tên.", "Tệp này không còn khả dụng.", "Đã gửi tệp ✓", "Không lấy được tệp, vui lòng thử lại sau.",
        "Không tìm thấy gì", "Hãy thử", "Kiểm tra chính tả", "Dùng tên ngắn hơn (chỉ từ chính)", "Gõ bằng chữ cái tiếng Anh hoặc ngôn ngữ của bạn",
        "Dung lượng", "Hãy lưu hoặc chuyển tiếp ngay", "Đã đổi ngôn ngữ ✓", "Lượt tìm này của người khác. Hãy gửi tìm kiếm của bạn.",
    ],
    "uk": [
        "Надішліть мені <b>назву</b> будь-якого фільму чи серіалу, і я знайду файл та одразу надішлю його.", "Привіт", "Швидкий пошук", "Миттєва доставка", "Автовидалення", "Порада: пишіть коротку назву, наприклад",
        "Допомога", "Про бота", "Головна", "Власник", "Оновлення", "Підтримка", "Мова",
        "Як користуватися", "Надішліть <b>назву</b> фільму", "Оберіть <b>файл</b> зі списку результатів", "Отримавши файл, <b>збережіть або перешліть</b> його (він видалиться через {m} хв)", "Поради", "Пишіть коротку й просту назву", "Кнопки допоможуть відфільтрувати за якістю, мовою та сезоном", "Можна писати будь-якою мовою чи абеткою (हिंदी, English, عربي ...)",
        "Про бота", "Файли", "Користувачі", "Бот",
        "Доступ закрито", "Щоб користуватися ботом, підпишіться на <b>{n}</b> канал(ів) нижче, потім натисніть ✓.", "Прогрес", "Підписатися на канал {n}", "Я підписався", "Ви ще не підписалися на всі канали!", "Дякуємо! Тепер надішліть назву фільму чи серіалу.", "Спершу підпишіться на всі канали!",
        "Результати пошуку", "Запит", "Знайдено", "Сторінка", "Якість", "Сезон", "Точних збігів немає, показано схожі результати", "Оберіть фільтр / файл", "Скинути фільтри", "Закрити",
        "Пошук застарів, надішліть назву ще раз.", "Цей файл більше недоступний.", "Файл надіслано ✓", "Не вдалося отримати файл, спробуйте пізніше.",
        "Нічого не знайдено", "Спробуйте", "Перевірте написання", "Введіть коротшу назву (лише головне слово)", "Пишіть латиницею або своєю мовою",
        "Розмір", "Збережіть або перешліть зараз", "Мову змінено ✓", "Цей пошук належить іншому користувачу. Надішліть свій запит.",
    ],
    "id": [
        "Kirim <b>nama</b> film atau serial apa pun, saya akan mencari file-nya dan langsung mengirimkannya.", "Halo", "Pencarian Cepat", "Pengiriman Instan", "Hapus otomatis", "Tips: ketik nama singkat, seperti",
        "Bantuan", "Tentang", "Beranda", "Pemilik", "Pembaruan", "Dukungan", "Bahasa",
        "Cara Menggunakan", "Kirim <b>nama</b> film", "Pilih <b>file</b> dari daftar hasil", "Setelah menerima file, <b>simpan atau teruskan</b> (akan dihapus dalam {m} menit)", "Tips", "Gunakan nama yang singkat dan sederhana", "Gunakan tombol untuk memfilter berdasarkan kualitas, bahasa, dan musim", "Anda bisa mengetik dalam bahasa atau aksara apa pun (हिंदी, English, عربي ...)",
        "Tentang", "File", "Pengguna", "Bot",
        "Akses Terkunci", "Gabung ke <b>{n}</b> channel di bawah untuk memakai bot ini, lalu tekan ✓.", "Kemajuan", "Gabung Channel {n}", "Saya Sudah Gabung", "Anda belum bergabung ke semua channel!", "Terima kasih! Sekarang kirim nama film/serial.", "Gabung ke semua channel dulu!",
        "Hasil Pencarian", "Kueri", "Ditemukan", "Halaman", "Kualitas", "Musim", "Tidak ada yang cocok persis, menampilkan hasil serupa", "Pilih filter / file", "Hapus Filter", "Tutup",
        "Pencarian ini sudah kedaluwarsa, kirim nama lagi.", "File ini sudah tidak tersedia.", "File terkirim ✓", "Gagal mengambil file, coba lagi nanti.",
        "Tidak ada hasil", "Coba ini", "Periksa ejaan", "Gunakan nama lebih singkat (kata utama saja)", "Ketik dengan huruf Latin atau bahasa Anda sendiri",
        "Ukuran", "Simpan atau teruskan sekarang", "Bahasa diubah ✓", "Pencarian ini milik orang lain. Kirim pencarian Anda sendiri.",
    ],
    "ms": [
        "Hantar <b>nama</b> mana-mana filem atau siri, saya akan cari fail itu dan hantar serta-merta.", "Helo", "Carian Pantas", "Penghantaran Segera", "Padam automatik", "Petua: taip nama pendek, seperti",
        "Bantuan", "Perihal", "Laman Utama", "Pemilik", "Kemas kini", "Sokongan", "Bahasa",
        "Cara Menggunakan", "Hantar <b>nama</b> filem", "Pilih <b>fail</b> anda daripada senarai hasil", "Selepas menerima fail, <b>simpan atau majukan</b> (akan dipadam dalam {m} minit)", "Petua", "Guna nama yang pendek dan mudah", "Guna butang untuk menapis mengikut kualiti, bahasa dan musim", "Anda boleh menaip dalam sebarang bahasa atau tulisan (हिंदी, English, عربي ...)",
        "Perihal", "Fail", "Pengguna", "Bot",
        "Akses Dikunci", "Sertai <b>{n}</b> saluran di bawah untuk guna bot ini, kemudian tekan ✓.", "Kemajuan", "Sertai Saluran {n}", "Saya Sudah Sertai", "Anda belum menyertai semua saluran!", "Terima kasih! Sekarang hantar nama filem/siri.", "Sertai semua saluran dahulu!",
        "Hasil Carian", "Pertanyaan", "Dijumpai", "Halaman", "Kualiti", "Musim", "Tiada padanan tepat, memaparkan hasil serupa", "Pilih penapis / fail", "Kosongkan Penapis", "Tutup",
        "Carian ini telah tamat tempoh, sila hantar nama semula.", "Fail ini tidak lagi tersedia.", "Fail dihantar ✓", "Gagal mendapatkan fail, sila cuba lagi nanti.",
        "Tiada hasil", "Cuba ini", "Semak ejaan", "Guna nama yang lebih pendek (perkataan utama sahaja)", "Taip dengan huruf Rumi atau bahasa anda sendiri",
        "Saiz", "Simpan atau majukan sekarang", "Bahasa ditukar ✓", "Carian ini milik orang lain. Sila hantar carian anda sendiri.",
    ],
    "ko": [
        "영화나 시리즈의 <b>이름</b>을 보내주시면 파일을 찾아 바로 보내드립니다.", "안녕하세요", "빠른 검색", "즉시 전송", "자동 삭제", "팁: 짧은 이름을 입력하세요, 예:",
        "도움말", "정보", "홈", "소유자", "업데이트", "지원", "언어",
        "사용 방법", "영화 <b>이름</b>을 보내세요", "결과 목록에서 <b>파일</b>을 선택하세요", "파일을 받으면 <b>저장하거나 전달</b>하세요 ({m}분 후 삭제됩니다)", "팁", "짧고 간단한 이름을 사용하세요", "버튼으로 화질, 언어, 시즌별로 필터링할 수 있어요", "어떤 언어나 문자로도 입력할 수 있어요 (हिंदी, English, عربي ...)",
        "정보", "파일", "사용자", "봇",
        "접근 잠김", "이 봇을 사용하려면 아래 <b>{n}</b>개 채널에 가입한 뒤 ✓ 를 누르세요.", "진행률", "채널 {n} 가입", "가입했어요", "아직 모든 채널에 가입하지 않았어요!", "감사합니다! 이제 영화/시리즈 이름을 보내세요.", "먼저 모든 채널에 가입하세요!",
        "검색 결과", "검색어", "찾음", "페이지", "화질", "시즌", "정확히 일치하는 결과가 없어 비슷한 결과를 보여드립니다", "필터 / 파일 선택", "필터 해제", "닫기",
        "이 검색은 만료되었습니다. 이름을 다시 보내주세요.", "이 파일은 더 이상 사용할 수 없습니다.", "파일 전송 완료 ✓", "파일을 가져오지 못했습니다. 나중에 다시 시도하세요.",
        "결과 없음", "이렇게 해보세요", "철자를 확인하세요", "더 짧은 이름을 사용하세요 (핵심 단어만)", "영어 알파벳이나 본인의 언어로 입력하세요",
        "크기", "지금 저장하거나 전달하세요", "언어가 변경되었습니다 ✓", "다른 사람의 검색입니다. 직접 검색해 주세요.",
    ],
    "pt": [
        "Envie-me o <b>nome</b> de qualquer filme ou série e eu encontro o arquivo e envio na hora.", "Olá", "Busca Rápida", "Entrega Instantânea", "Exclusão automática", "Dica: digite um nome curto, como",
        "Ajuda", "Sobre", "Início", "Dono", "Novidades", "Suporte", "Idioma",
        "Como Usar", "Envie o <b>nome</b> de um filme", "Escolha seu <b>arquivo</b> na lista de resultados", "Ao receber o arquivo, <b>salve ou encaminhe</b> (ele é excluído em {m} min)", "Dicas", "Use um nome curto e simples", "Use os botões para filtrar por qualidade, idioma e temporada", "Você pode escrever em qualquer idioma ou alfabeto (हिंदी, English, عربي ...)",
        "Sobre", "Arquivos", "Usuários", "Bot",
        "Acesso Bloqueado", "Entre nos <b>{n}</b> canal(is) abaixo para usar este bot e depois toque em ✓.", "Progresso", "Entrar no canal {n}", "Já entrei", "Você ainda não entrou em todos os canais!", "Obrigado! Agora envie o nome de um filme/série.", "Entre em todos os canais primeiro!",
        "Resultados da Busca", "Busca", "Encontrados", "Página", "Qualidade", "Temporada", "Nenhuma correspondência exata, mostrando resultados parecidos", "Escolha filtro / arquivo", "Limpar Filtros", "Fechar",
        "Esta busca expirou, envie o nome novamente.", "Este arquivo não está mais disponível.", "Arquivo enviado ✓", "Não foi possível obter o arquivo, tente mais tarde.",
        "Nada encontrado", "Tente isto", "Verifique a ortografia", "Use um nome mais curto (só a palavra principal)", "Escreva com letras latinas ou no seu idioma",
        "Tamanho", "Salve ou encaminhe agora", "Idioma alterado ✓", "Esta busca é de outra pessoa. Envie a sua.",
    ],
    "zh": [
        "請傳送任何電影或影集的<b>名稱</b>給我，我會找到檔案並立即傳送。", "你好", "快速搜尋", "即時傳送", "自動刪除", "提示：輸入簡短的名稱，例如",
        "說明", "關於", "首頁", "擁有者", "更新", "支援", "語言",
        "使用方法", "傳送電影<b>名稱</b>", "從結果列表中選擇你的<b>檔案</b>", "收到檔案後請<b>儲存或轉發</b>（{m} 分鐘後會被刪除）", "小提示", "使用簡短簡單的名稱", "可用按鈕依畫質、語言和季數篩選", "你可以用任何語言或文字輸入（हिंदी, English, عربي ...）",
        "關於", "檔案", "使用者", "機器人",
        "存取已鎖定", "請先加入下方 <b>{n}</b> 個頻道才能使用此機器人，然後點選 ✓。", "進度", "加入頻道 {n}", "我已加入", "你還沒有加入所有頻道！", "謝謝！現在請傳送電影／影集名稱。", "請先加入所有頻道！",
        "搜尋結果", "關鍵字", "找到", "頁", "畫質", "季", "沒有完全相符的結果，顯示相似結果", "選擇篩選 / 檔案", "清除篩選", "關閉",
        "此搜尋已過期，請重新傳送名稱。", "此檔案已無法使用。", "檔案已傳送 ✓", "無法取得檔案，請稍後再試。",
        "找不到任何結果", "試試看", "檢查拼寫", "使用更短的名稱（只輸入主要單字）", "用英文字母或你自己的語言輸入",
        "大小", "請立即儲存或轉發", "語言已更改 ✓", "這是別人的搜尋，請傳送你自己的搜尋。",
    ],
    "fr": [
        "Envoyez-moi le <b>nom</b> d'un film ou d'une série et je trouve le fichier pour vous l'envoyer aussitôt.", "Bonjour", "Recherche rapide", "Envoi instantané", "Suppression auto", "Astuce : tapez un nom court, comme",
        "Aide", "À propos", "Accueil", "Propriétaire", "Actualités", "Support", "Langue",
        "Mode d'emploi", "Envoyez le <b>nom</b> d'un film", "Choisissez votre <b>fichier</b> dans la liste", "Une fois le fichier reçu, <b>enregistrez-le ou transférez-le</b> (supprimé dans {m} min)", "Astuces", "Utilisez un nom court et simple", "Utilisez les boutons pour filtrer par qualité, langue et saison", "Vous pouvez écrire dans n'importe quelle langue ou écriture (हिंदी, English, عربي ...)",
        "À propos", "Fichiers", "Utilisateurs", "Bot",
        "Accès verrouillé", "Rejoignez les <b>{n}</b> canaux ci-dessous pour utiliser ce bot, puis appuyez sur ✓.", "Progression", "Rejoindre le canal {n}", "J'ai rejoint", "Vous n'avez pas encore rejoint tous les canaux !", "Merci ! Envoyez maintenant le nom d'un film ou d'une série.", "Rejoignez d'abord tous les canaux !",
        "Résultats de recherche", "Requête", "Trouvé", "Page", "Qualité", "Saison", "Aucune correspondance exacte, résultats similaires affichés", "Choisissez un filtre / fichier", "Effacer les filtres", "Fermer",
        "Cette recherche a expiré, renvoyez le nom.", "Ce fichier n'est plus disponible.", "Fichier envoyé ✓", "Impossible d'obtenir le fichier, réessayez plus tard.",
        "Aucun résultat", "Essayez ceci", "Vérifiez l'orthographe", "Utilisez un nom plus court (juste le mot principal)", "Écrivez en lettres latines ou dans votre langue",
        "Taille", "Enregistrez ou transférez maintenant", "Langue modifiée ✓", "Cette recherche appartient à quelqu'un d'autre. Envoyez la vôtre.",
    ],
    "de": [
        "Sende mir den <b>Namen</b> eines Films oder einer Serie, und ich finde die Datei und schicke sie sofort.", "Hallo", "Schnelle Suche", "Sofortige Lieferung", "Auto-Löschen", "Tipp: kurzen Namen eingeben, z. B.",
        "Hilfe", "Info", "Start", "Besitzer", "Neuigkeiten", "Support", "Sprache",
        "So funktioniert's", "Sende den <b>Namen</b> eines Films", "Wähle deine <b>Datei</b> aus der Ergebnisliste", "Sobald du die Datei hast, <b>speichere oder leite sie weiter</b> (wird nach {m} Min. gelöscht)", "Tipps", "Verwende einen kurzen, einfachen Namen", "Mit den Buttons nach Qualität, Sprache und Staffel filtern", "Du kannst in jeder Sprache oder Schrift tippen (हिंदी, English, عربي ...)",
        "Info", "Dateien", "Nutzer", "Bot",
        "Zugriff gesperrt", "Tritt den <b>{n}</b> Kanälen unten bei, um den Bot zu nutzen, und tippe dann auf ✓.", "Fortschritt", "Kanal {n} beitreten", "Ich bin beigetreten", "Du bist noch nicht allen Kanälen beigetreten!", "Danke! Sende jetzt den Namen eines Films/einer Serie.", "Tritt zuerst allen Kanälen bei!",
        "Suchergebnisse", "Suche", "Gefunden", "Seite", "Qualität", "Staffel", "Keine genaue Übereinstimmung, ähnliche Ergebnisse werden angezeigt", "Filter / Datei wählen", "Filter löschen", "Schließen",
        "Diese Suche ist abgelaufen, sende den Namen bitte erneut.", "Diese Datei ist nicht mehr verfügbar.", "Datei gesendet ✓", "Datei konnte nicht abgerufen werden, versuche es später erneut.",
        "Nichts gefunden", "Versuch Folgendes", "Prüfe die Schreibweise", "Nutze einen kürzeren Namen (nur das Hauptwort)", "Tippe mit lateinischen Buchstaben oder in deiner Sprache",
        "Größe", "Jetzt speichern oder weiterleiten", "Sprache geändert ✓", "Diese Suche gehört jemand anderem. Sende deine eigene.",
    ],
    "it": [
        "Inviami il <b>nome</b> di un film o di una serie e troverò il file e lo invierò subito.", "Ciao", "Ricerca veloce", "Consegna immediata", "Eliminazione automatica", "Suggerimento: scrivi un nome breve, come",
        "Aiuto", "Info", "Home", "Proprietario", "Aggiornamenti", "Supporto", "Lingua",
        "Come si usa", "Invia il <b>nome</b> di un film", "Scegli il tuo <b>file</b> dall'elenco dei risultati", "Quando ricevi il file, <b>salvalo o inoltralo</b> (viene eliminato dopo {m} min)", "Suggerimenti", "Usa un nome breve e semplice", "Usa i pulsanti per filtrare per qualità, lingua e stagione", "Puoi scrivere in qualsiasi lingua o alfabeto (हिंदी, English, عربي ...)",
        "Info", "File", "Utenti", "Bot",
        "Accesso bloccato", "Unisciti ai <b>{n}</b> canali qui sotto per usare il bot, poi tocca ✓.", "Avanzamento", "Unisciti al canale {n}", "Mi sono unito", "Non ti sei ancora unito a tutti i canali!", "Grazie! Ora invia il nome di un film/serie.", "Prima unisciti a tutti i canali!",
        "Risultati della ricerca", "Ricerca", "Trovati", "Pagina", "Qualità", "Stagione", "Nessuna corrispondenza esatta, mostro risultati simili", "Scegli filtro / file", "Rimuovi filtri", "Chiudi",
        "Questa ricerca è scaduta, invia di nuovo il nome.", "Questo file non è più disponibile.", "File inviato ✓", "Impossibile ottenere il file, riprova più tardi.",
        "Nessun risultato", "Prova questo", "Controlla l'ortografia", "Usa un nome più corto (solo la parola principale)", "Scrivi con lettere latine o nella tua lingua",
        "Dimensione", "Salvalo o inoltralo adesso", "Lingua cambiata ✓", "Questa ricerca è di un altro utente. Invia la tua.",
    ],
    "he": [
        "שלחו לי את <b>שם</b> הסרט או הסדרה ואמצא את הקובץ ואשלח אותו מיד.", "שלום", "חיפוש מהיר", "שליחה מיידית", "מחיקה אוטומטית", "טיפ: הקלידו שם קצר, כמו",
        "עזרה", "אודות", "בית", "בעלים", "עדכונים", "תמיכה", "שפה",
        "איך משתמשים", "שלחו את <b>שם</b> הסרט", "בחרו את ה<b>קובץ</b> מרשימת התוצאות", "לאחר קבלת הקובץ, <b>שמרו או העבירו</b> אותו (יימחק בעוד {m} דקות)", "טיפים", "השתמשו בשם קצר ופשוט", "השתמשו בכפתורים לסינון לפי איכות, שפה ועונה", "אפשר להקליד בכל שפה או כתב (हिंदी, English, عربي ...)",
        "אודות", "קבצים", "משתמשים", "בוט",
        "הגישה נעולה", "הצטרפו ל-<b>{n}</b> הערוצים למטה כדי להשתמש בבוט, ואז לחצו על ✓.", "התקדמות", "הצטרפות לערוץ {n}", "הצטרפתי", "עדיין לא הצטרפתם לכל הערוצים!", "תודה! עכשיו שלחו שם של סרט/סדרה.", "קודם הצטרפו לכל הערוצים!",
        "תוצאות חיפוש", "חיפוש", "נמצאו", "עמוד", "איכות", "עונה", "לא נמצאה התאמה מדויקת, מוצגות תוצאות דומות", "בחרו מסנן / קובץ", "נקה מסננים", "סגור",
        "החיפוש פג תוקף, שלחו את השם שוב.", "הקובץ כבר לא זמין.", "הקובץ נשלח ✓", "לא ניתן לקבל את הקובץ, נסו שוב מאוחר יותר.",
        "לא נמצא כלום", "נסו כך", "בדקו את האיות", "השתמשו בשם קצר יותר (המילה העיקרית בלבד)", "הקלידו באותיות לטיניות או בשפה שלכם",
        "גודל", "שמרו או העבירו עכשיו", "השפה שונתה ✓", "החיפוש הזה שייך למישהו אחר. שלחו חיפוש משלכם.",
    ],
    "nl": [
        "Stuur me de <b>naam</b> van een film of serie en ik zoek het bestand en stuur het meteen.", "Hallo", "Snel zoeken", "Directe levering", "Automatisch verwijderen", "Tip: typ een korte naam, zoals",
        "Help", "Over", "Home", "Eigenaar", "Updates", "Support", "Taal",
        "Hoe te gebruiken", "Stuur de <b>naam</b> van een film", "Kies je <b>bestand</b> uit de resultatenlijst", "Zodra je het bestand hebt, <b>sla het op of stuur het door</b> (wordt na {m} min verwijderd)", "Tips", "Gebruik een korte, eenvoudige naam", "Gebruik de knoppen om te filteren op kwaliteit, taal en seizoen", "Je kunt in elke taal of elk schrift typen (हिंदी, English, عربي ...)",
        "Over", "Bestanden", "Gebruikers", "Bot",
        "Toegang vergrendeld", "Word lid van de <b>{n}</b> kanalen hieronder om deze bot te gebruiken en tik dan op ✓.", "Voortgang", "Word lid van kanaal {n}", "Ik ben lid geworden", "Je bent nog niet lid van alle kanalen!", "Bedankt! Stuur nu de naam van een film/serie.", "Word eerst lid van alle kanalen!",
        "Zoekresultaten", "Zoekopdracht", "Gevonden", "Pagina", "Kwaliteit", "Seizoen", "Geen exacte match, vergelijkbare resultaten worden getoond", "Kies filter / bestand", "Filters wissen", "Sluiten",
        "Deze zoekopdracht is verlopen, stuur de naam opnieuw.", "Dit bestand is niet meer beschikbaar.", "Bestand verzonden ✓", "Bestand ophalen mislukt, probeer het later opnieuw.",
        "Niets gevonden", "Probeer dit", "Controleer de spelling", "Gebruik een kortere naam (alleen het hoofdwoord)", "Typ met Latijnse letters of in je eigen taal",
        "Grootte", "Sla het nu op of stuur het door", "Taal gewijzigd ✓", "Deze zoekopdracht is van iemand anders. Stuur je eigen zoekopdracht.",
    ],
    "sv": [
        "Skicka mig <b>namnet</b> på en film eller serie så hittar jag filen och skickar den direkt.", "Hej", "Snabbsökning", "Direktleverans", "Autoradering", "Tips: skriv ett kort namn, som",
        "Hjälp", "Om", "Hem", "Ägare", "Uppdateringar", "Support", "Språk",
        "Så här använder du", "Skicka <b>namnet</b> på en film", "Välj din <b>fil</b> i resultatlistan", "När du fått filen, <b>spara eller vidarebefordra</b> den (raderas efter {m} min)", "Tips", "Använd ett kort och enkelt namn", "Använd knapparna för att filtrera efter kvalitet, språk och säsong", "Du kan skriva på vilket språk eller skrift som helst (हिंदी, English, عربي ...)",
        "Om", "Filer", "Användare", "Bot",
        "Åtkomst låst", "Gå med i de <b>{n}</b> kanalerna nedan för att använda boten och tryck sedan på ✓.", "Framsteg", "Gå med i kanal {n}", "Jag har gått med", "Du har inte gått med i alla kanaler ännu!", "Tack! Skicka nu namnet på en film/serie.", "Gå med i alla kanaler först!",
        "Sökresultat", "Sökning", "Hittade", "Sida", "Kvalitet", "Säsong", "Ingen exakt träff, visar liknande resultat", "Välj filter / fil", "Rensa filter", "Stäng",
        "Sökningen har gått ut, skicka namnet igen.", "Filen är inte längre tillgänglig.", "Filen skickad ✓", "Kunde inte hämta filen, försök igen senare.",
        "Inget hittades", "Prova detta", "Kontrollera stavningen", "Använd ett kortare namn (bara huvudordet)", "Skriv med latinska bokstäver eller på ditt eget språk",
        "Storlek", "Spara eller vidarebefordra nu", "Språk ändrat ✓", "Den här sökningen tillhör någon annan. Skicka din egen.",
    ],
}

STR = {}
for _code, _vals in _RAW.items():
    assert len(_vals) == len(KEYS), f"{_code}: {len(_vals)} strings, expected {len(KEYS)}"
    STR[_code] = dict(zip(KEYS, _vals))
assert set(UI_LANGS) == set(STR), "UI_LANGS and strings do not match"


def guess_lang(tg_code) -> str:
    """Telegram app language code (e.g. 'pt-br', 'iw') -> one of our UI languages, else 'en'."""
    c = (tg_code or "").lower().replace("_", "-").split("-")[0]
    c = {"iw": "he", "in": "id"}.get(c, c)
    return c if c in UI_LANGS else "en"


def t(lang: str, key: str, **kw) -> str:
    text = STR.get(lang, STR["en"]).get(key) or STR["en"][key]
    return text.format(**kw) if kw else text
