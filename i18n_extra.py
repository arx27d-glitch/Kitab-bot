"""Texts of the new features (movie info, trending, requests, premium plan).

English + Hindi are written here. Every other language automatically falls back to English
(see tr() in i18n.py), so nothing breaks. To translate, copy a T["xx"].update(...) block below.
"""
from i18n import T

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
