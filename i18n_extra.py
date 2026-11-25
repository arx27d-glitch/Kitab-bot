"""Texts of the new features (movie info, trending, requests, premium plan).

English + Hindi are written here. Every other language automatically falls back to English
(see tr() in i18n.py), so nothing breaks. To translate, copy a T["xx"].update(...) block below.
"""
import logging

from i18n import T

log = logging.getLogger("bookbot.i18n")


class _English(dict):
    """Safety net: a missing English text must never crash a command.
    It is written to the log (so /logs shows it) and the key itself is shown instead of the text."""

    def __missing__(self, key):
        log.warning("Missing text key %r - add it to i18n.py / i18n_extra.py", key)
        return str(key)


T["en"] = _English(T["en"])

T["en"].update(
    dict(
        b_info="Movie Info", b_trailer="Trailer", b_findbot="Find in bot", b_trending="Trending",
        b_request="Request this movie", b_popmovies="Popular Movies", b_popseries="Popular Series",
        b_toprated="Top Rated", b_back="Back", b_getfile="Get File", b_buy="Buy Premium",
        f_info="Posters and Movie Info",
        cmds_title="Commands",
        help_cmds=(
            "/search name - search a file\n"
            "/info name - poster, rating, plot and cast\n"
            "/trending - popular movies and series\n"
            "/request name - ask for a movie we don't have\n"
            "/myplan - your plan and today's downloads\n"
            "/language - change the language"
        ),
        info_usage="Send a name: <code>/info Inception</code>",
        info_nf="No info found for this name.",
        trend_title="Trending Now", trend_pick="Pick a list",
        trend_tap="Tap a title to search it in the bot",
        trend_fail="The list is not available right now, please try again later.",
        trend_loading="Loading the list, please wait...",
        # trending sections (menu buttons + list headings)
        c_bm="Bollywood", c_hm="Hollywood", c_sm="South Indian", c_om="Other-wood",
        c_bs="Indian Series", c_hs="English Series", c_os="Other Series", c_nw="New Releases",
        c_pm="Popular Movies", c_ps="Popular Series", c_tm="Top Rated Movies", c_ts="Top Rated Series",
        c_gn="Genres",
        d_sm="Tamil, Telugu, Malayalam, Kannada",
        d_om="Korean, Japanese, Turkish, Punjabi, Bengali and more",
        d_os="K-drama, anime, Turkish series and more",
        nf_req="Not in the library yet? You can request it below.",
        req_usage="Send the name: <code>/request Movie Name</code>",
        req_sent="Request saved! I will message you as soon as it is available.",
        req_dup="You have already requested this one.",
        req_limit="You already have {n} pending requests. Please wait for them first.",
        req_exists="This is already available. Just send its name to search.",
        req_bad="Please send a longer movie name.",
        req_done="Your requested movie is now available!",
        a_limit="Daily limit reached ({n} files per day). Upgrade to Premium for unlimited downloads: /myplan",
        plan_title="My Plan", plan_type="Plan", plan_free="Free", plan_prem="Premium", plan_admin="Admin",
        plan_exp="Expires", plan_days="{d} days left", plan_today="Downloads today", plan_unl="unlimited",
        plan_perks="Premium perks",
    )
)

# genre buttons (keys like "g_Sci-Fi" are not valid keyword names, so a normal dict is used)
_GENRES = [
    "Action", "Comedy", "Horror", "Thriller", "Romance", "Sci-Fi", "Animation", "Crime",
    "Drama", "Adventure", "Fantasy", "Mystery", "Family", "War", "Biography", "Documentary",
]
T["en"].update({f"g_{g}": g for g in _GENRES})

T["hi"].update(
    dict(
        b_info="मूवी जानकारी", b_trailer="ट्रेलर", b_findbot="बॉट में खोजें", b_trending="ट्रेंडिंग",
        b_request="यह मूवी रिक्वेस्ट करें", b_popmovies="पॉपुलर मूवीज़", b_popseries="पॉपुलर सीरीज़",
        b_toprated="टॉप रेटेड", b_back="वापस", b_getfile="फ़ाइल पाएँ", b_buy="प्रीमियम खरीदें",
        f_info="पोस्टर और मूवी जानकारी",
        cmds_title="कमांड्स",
        help_cmds=(
            "/search नाम - फ़ाइल खोजें\n"
            "/info नाम - पोस्टर, रेटिंग, कहानी और कास्ट\n"
            "/trending - पॉपुलर मूवीज़ और सीरीज़\n"
            "/request नाम - जो मूवी हमारे पास नहीं है उसकी माँग करें\n"
            "/myplan - आपका प्लान और आज के डाउनलोड\n"
            "/language - भाषा बदलें"
        ),
        info_usage="नाम भेजें: <code>/info Inception</code>",
        info_nf="इस नाम की जानकारी नहीं मिली।",
        trend_title="अभी ट्रेंडिंग", trend_pick="एक लिस्ट चुनें",
        trend_tap="बॉट में खोजने के लिए किसी टाइटल पर टैप करें",
        trend_fail="लिस्ट अभी उपलब्ध नहीं है, कृपया बाद में कोशिश करें।",
        trend_loading="लिस्ट लोड हो रही है, कृपया रुकें...",
        c_bm="बॉलीवुड", c_hm="हॉलीवुड", c_sm="साउथ इंडियन", c_om="अदर-वुड",
        c_bs="इंडियन सीरीज़", c_hs="इंग्लिश सीरीज़", c_os="अन्य सीरीज़", c_nw="नई रिलीज़",
        c_pm="पॉपुलर मूवीज़", c_ps="पॉपुलर सीरीज़", c_tm="टॉप रेटेड मूवीज़", c_ts="टॉप रेटेड सीरीज़",
        c_gn="जॉनर",
        d_sm="तमिल, तेलुगु, मलयालम, कन्नड़",
        d_om="कोरियन, जापानी, टर्किश, पंजाबी, बंगाली और भी",
        d_os="के-ड्रामा, एनीमे, टर्किश सीरीज़ और भी",
        nf_req="अभी लाइब्रेरी में नहीं है? नीचे से रिक्वेस्ट कर सकते हैं।",
        req_usage="नाम भेजें: <code>/request Movie Name</code>",
        req_sent="रिक्वेस्ट सेव हो गई! उपलब्ध होते ही मैं आपको मैसेज करूँगा।",
        req_dup="आप यह पहले ही रिक्वेस्ट कर चुके हैं।",
        req_limit="आपकी {n} रिक्वेस्ट पहले से पेंडिंग हैं। कृपया पहले उनका इंतज़ार करें।",
        req_exists="यह पहले से उपलब्ध है। बस इसका नाम भेजकर खोजें।",
        req_bad="कृपया मूवी का पूरा नाम भेजें।",
        req_done="आपकी माँगी हुई मूवी अब उपलब्ध है!",
        a_limit="आज की लिमिट पूरी हो गई (रोज़ {n} फ़ाइलें)। अनलिमिटेड डाउनलोड के लिए प्रीमियम लें: /myplan",
        plan_title="मेरा प्लान", plan_type="प्लान", plan_free="फ्री", plan_prem="प्रीमियम", plan_admin="एडमिन",
        plan_exp="खत्म होगा", plan_days="{d} दिन बाकी", plan_today="आज के डाउनलोड", plan_unl="अनलिमिटेड",
        plan_perks="प्रीमियम के फ़ायदे",
    )
)

T["hi"].update(
    {
        "g_Action": "एक्शन", "g_Comedy": "कॉमेडी", "g_Horror": "हॉरर", "g_Thriller": "थ्रिलर",
        "g_Romance": "रोमांस", "g_Sci-Fi": "साई-फ़ाई", "g_Animation": "एनिमेशन", "g_Crime": "क्राइम",
        "g_Drama": "ड्रामा", "g_Adventure": "एडवेंचर", "g_Fantasy": "फ़ैंटेसी", "g_Mystery": "मिस्ट्री",
        "g_Family": "फ़ैमिली", "g_War": "वॉर", "g_Biography": "बायोग्राफ़ी", "g_Documentary": "डॉक्यूमेंट्री",
    }
)
